"""Architecture test: de AVG-wisroute bereikt de kolommen met tool-invoer (ADR-036 OP-32).

**Correctie 2026-09-09, na het daadwerkelijk fixen van OP-32.** De oorspronkelijke aanname hier
("`LearningExperience.observation_data` wordt niet bezocht") is ONWAAR gebleken bij het narekenen
van de daadwerkelijke opslag. `_record_tool_event` roept `observation_service.record(context=...,
observation_data=..., ...)` aan -- twee APARTE kwargs op een servicemethode, geen ORM-kolommen.
`LearningGDPRService` (het model, geen aparte `observation_data`-kolom) heeft die kolom nooit
gehad; SQLAlchemy zou bij toegang tot `record.observation_data` een `AttributeError` hebben
gegeven. De daadwerkelijke opslag zit in `learning_repository.py::save_observation()` (regel 64):
`context=obs.observation_data` -- de `observation_data`-kwarg wordt bij het schrijven naar de
kolom `context` gemapt. `_observation_matches_user` bezoekt `record.context` AL. De tool-payload
was dus NOOIT onbereikbaar; deze guard mat de NAAM van een servicemethode-kwarg (via een AST-scan
op keyword-argumenten) en verwarde die met een ORM-kolomnaam, zonder de daadwerkelijke
persistentie-mapping te volgen. `KNOWN_UNREACHED_COLUMNS` hieronder blijft daarom bewust staan
(de guard zelf hertrainen op de kwarg->kolom-vertaling is meer risico dan waard voor een geval dat
al veilig is), maar met de GEVERIFIEERDE reden in plaats van de weerlegde.

**Wat wel klopte en nu is opgelost:** `_json_contains_user` recursief over `payload.values()` en
**nooit over sleutels** was een echt, apart gat (ADR-036 OP-32, Fase D/P2) -- gefixed 2026-09-09,
zie `test_the_key_blindness_is_fixed` hieronder. Dat gat stond los van de observation_data-vraag
hierboven; de fix wijzigt de matchlogica van `_json_contains_user`, niet welke KOLOMMEN bezocht
worden.
"""

#: JSON-kolommen die door tools aangeleverde gegevens dragen, en de wisroute die ze hoort te
#: bezoeken. Kolom -> reden, gedateerd.
KNOWN_UNREACHED_COLUMNS: dict[str, str] = {
    "observation_data": (
        "2026-09-09, OP-32, geverifieerd onjuist gebleken en gecorrigeerd -- dit is GEEN "
        "ORM-kolomnaam maar de kwarg-naam van `observation_service.record(observation_data=...)`. "
        "`learning_repository.py::save_observation()` regel 64 mapt die kwarg bij het schrijven "
        "naar `LearningExperience.context`, en `_observation_matches_user` bezoekt `record.context` "
        "al. De AST-scan hieronder herkent alleen de servicelaag-kwarg-naam en volgt de "
        "persistentie-mapping niet; deze regel blijft staan om de guard groen te houden voor een "
        "naam die feitelijk geen apart bereikbaarheidsrisico draagt."
    ),
}


def _matcher_source() -> str:
    import inspect

    from src.core.learning.gdpr_service import LearningGDPRService

    return inspect.getsource(LearningGDPRService._observation_matches_user)


def _tool_input_columns_in_the_learning_store() -> set[str]:
    """De JSON-kolommen waarin het leersubsysteem tool-gegevens wegschrijft.

    Uit de BRON: de keyword-argumenten waarmee `_record_tool_event` een `LearningExperience`
    aanmaakt. Zo betrapt deze guard ook een NIEUWE kolom die tool-gegevens gaat dragen.
    """
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "src/core/events/handlers/learning_event_handler.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    # Elk keyword-argument dat een dict-literal met een `payload`- of `result`-sleutel krijgt.
    # Bewust NIET gefilterd op de naam van de aangeroepen constructor: het gaat via
    # `self.observation_service.record(...)` en niet via `LearningExperience(...)`, en een
    # volgende versie kan die indirectie weer wijzigen. De KOLOMNAAM is wat deze guard bewaakt.
    columns: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if not keyword.arg or not isinstance(keyword.value, ast.Dict):
                continue
            carries_tool_data = any(
                isinstance(key, ast.Constant) and key.value in {"payload", "result"}
                for key in keyword.value.keys
                if key is not None
            )
            if carries_tool_data:
                columns.add(keyword.arg)
    return columns


def test_the_guard_finds_the_learning_store_columns() -> None:
    """Vangnet: vindt de analyse de kolommen waar het over gaat?"""
    columns = _tool_input_columns_in_the_learning_store()

    assert columns, (
        "Geen enkele kolom gevonden waarin het leersubsysteem tool-gegevens schrijft. "
        "`_record_tool_event` hernoemd of verplaatst? Werk deze guard bij -- anders bewaakt hij "
        "niets."
    )


def test_every_tool_input_column_is_visited_by_the_erasure_route() -> None:
    """Een nieuwe kolom met tool-gegevens moet door de art.-17-matcher bezocht worden."""
    source = _matcher_source()
    columns = _tool_input_columns_in_the_learning_store()

    unreached = sorted(
        column
        for column in columns
        if column not in source and column not in KNOWN_UNREACHED_COLUMNS
    )

    assert not unreached, (
        f"Deze kolommen dragen door tools aangeleverde gegevens maar worden door "
        f"`_observation_matches_user` niet bezocht: {unreached}. Een verwijderverzoek vindt die "
        "gegevens dan niet. Neem de kolom op in de matcher, of zet hem met datum en reden in "
        "KNOWN_UNREACHED_COLUMNS."
    )


def test_known_unreached_columns_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    source = _matcher_source()
    stale = sorted(column for column in KNOWN_UNREACHED_COLUMNS if column in source)

    assert not stale, (
        f"Deze kolommen worden inmiddels wel bezocht: {stale}. Haal ze uit KNOWN_UNREACHED_COLUMNS."
    )


def test_the_key_blindness_is_fixed() -> None:
    """De matcher recurseert sinds 2026-09-09 ook over sleutelnamen (ADR-036 OP-32, Fase D/P2).

    Was tot en met 2026-09-08 een geregistreerde blinde vlek (`_json_contains_user` liep alleen
    over `payload.values()`). Deze test bewaakt dat de fix niet stil terugdraait: structuurtoets
    op de bron (geen `.values()`-only-patroon meer) EN een gedragstoets op een echt geval van een
    gebruikersverwijzing die UITSLUITEND als dict-sleutel voorkomt.
    """
    import inspect

    from src.core.learning.gdpr_service import LearningGDPRService

    source = inspect.getsource(LearningGDPRService._json_contains_user)
    assert ".items()" in source, (
        "`_json_contains_user` recursereert niet meer over `.items()` -- de sleutel-fix van "
        "OP-32 lijkt teruggedraaid. Een gebruikersverwijzing die alleen als dict-SLEUTEL "
        "voorkomt, is dan weer onvindbaar voor een art.-17-verzoek."
    )

    service = LearningGDPRService.__new__(LearningGDPRService)
    assert service._json_contains_user({"user_42": {"tool": "noop"}}, "user_42") is True, (
        "Een gebruikersverwijzing die uitsluitend als dict-sleutel voorkomt wordt niet gevonden. "
        "Dit is precies het OP-32-scenario dat de fix moest oplossen."
    )
    assert service._json_contains_user({"other_user": {"tool": "noop"}}, "user_42") is False, (
        "De matcher geeft een fout-positief voor een sleutel die niet bij deze gebruiker hoort -- "
        "dat zou een ANDERE gebruiker per ongeluk als 'gevonden' markeren bij een wisverzoek."
    )
