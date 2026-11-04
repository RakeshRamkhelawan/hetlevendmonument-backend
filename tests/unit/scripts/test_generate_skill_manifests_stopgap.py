"""Regression test: manifest generator must respect tool permission profiles (IR-001).

Found by the mandatory independent review of ADR-036 Fase A dag 4 (AUDIT-008):
scripts/generate_skill_manifests.py embedded the system-prompt stopgap
("without attempting a TOOL_CALL") unconditionally in every generated manifest.
Regenerating the manifests would therefore silently restore the stopgap for
skillsgaptraining -- recreating the exact inconsistency (profile present +
stopgap present) that tests/architecture/test_als_skills_tool_permissions.py
guards against.

The generator now reads config/tool_permissions.yml: skills WITH a profile get
an honest TOOL_CALL instruction; skills WITHOUT a profile keep the stopgap.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

MARKER = "without attempting a TOOL_CALL"
GENERATOR_PATH = Path("scripts/generate_skill_manifests.py")


def _load_generator():  # type: ignore[no-untyped-def]
    """Load the generator module from its script path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("gen_skill_manifests", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_omits_stopgap_for_profiled_skill() -> None:
    """A skill with a tool permission profile gets the TOOL_CALL instruction."""
    mod = _load_generator()
    manifest = mod.build_manifest("skillsgaptraining", "SkillsGapTrainingSkill")

    assert MARKER not in manifest["system_prompt"]
    assert "TOOL_CALL: tool_name" in manifest["system_prompt"]
    assert "ADR-015" in manifest["system_prompt"]


@pytest.mark.security()
def test_generator_keeps_stopgap_for_profileless_skill() -> None:
    """A skill without a profile keeps the safe text-only stopgap (ADR-015)."""
    mod = _load_generator()
    manifest = mod.build_manifest("burnoutcoach", "BurnoutCoachSkill")

    assert MARKER in manifest["system_prompt"]


# ---------------------------------------------------------------------------
# BE-AGT-040: een profiel geeft TOESTEMMING, geen werkende tools
# ---------------------------------------------------------------------------
#
# De geprofileerde tak beweerde "You have working tools (see allowed_tools in your
# manifest)". Dat is onwaar: geen van de vijf tools van de piloot resolveert in
# ToolBrokerService.execute_tool (BE-AGT-039 F1). De aanname eronder was dat een
# permissieprofiel wiring impliceert -- een profiel geeft alleen toestemming.
#
# De formulering mag NIET terugvallen op de stopgap: dat herintroduceert precies de
# inconsistentie die onafhankelijke review IR-001 afdwong (profiel + stopgap), bewaakt
# door tests/architecture/test_als_skills_tool_permissions.py.

PILOT = "skillsgaptraining"
PILOT_CLASS = "SkillsGapTrainingSkill"
PILOT_MANIFEST = Path("src/core/als/agents/skills/manifests/skillsgaptraining.yml")

CLAIM = "working tools"


def _pilot_prompt() -> str:
    mod = _load_generator()
    return str(mod.build_manifest(PILOT, PILOT_CLASS)["system_prompt"])


def test_profiled_skill_does_not_claim_working_tools() -> None:
    """De prompt mag niet beweren dat er werkende tools zijn."""
    prompt = _pilot_prompt()

    assert CLAIM not in prompt, (
        "De system-prompt van een geprofileerde skill beweert 'working tools' te hebben. "
        "Een profiel geeft TOESTEMMING en geen wiring, dus die zin gaat over de verkeerde "
        "vraag -- ook nu de vier piloottools wel bestaan (2026-09-21). Wat de prompt mag "
        "zeggen, staat in `test_the_prompt_only_promises_working_tools_while_they_all_work`: "
        "een belofte die aan de gemeten werkelijkheid is gekoppeld."
    )


def _piloot_profieltools() -> list[str]:
    data = yaml.safe_load(Path("config/tool_permissions.yml").read_text(encoding="utf-8")) or {}
    for profiel in data.get("agent_profiles") or []:
        if profiel.get("agent_id") == PILOT:
            return [str(t) for t in profiel.get("allowed_tools") or []]
    raise AssertionError(f"geen profiel voor {PILOT} in config/tool_permissions.yml")


def _uitvoerbaar_voor_deze_skill() -> set[str]:
    """Wat de broker die DEZE skill gebruikt werkelijk kan uitvoeren.

    Niet de klasse-attributen van de drie registries, maar het OBJECT dat de skill in handen
    heeft. Dat onderscheid is het hele punt van de eerste versie van deze guard, die eraan
    kapotging: `BaseSpecialistAgent` bouwt zijn eigen `ToolBrokerService` en geeft daar GEEN
    `local_registry` aan mee (gemeten 2026-09-21: `local_registry = None`, en de `local__`-tak
    gooit "Local tool registry not initialized"). Een naam in `LocalToolRegistry._TOOL_NAMES`
    is dus geen aangesloten tool voor deze agent -- precies dezelfde fout als een controle op
    een AFGELEIDE NAAM in plaats van op een capaciteit.
    """
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    broker = SkillsGapTrainingSkill(tenant_id=1).tools
    namen: set[str] = set()
    for attribuut in ("business_registry", "hr_registry", "local_registry"):
        registry = getattr(broker, attribuut, None)
        if registry is not None:
            namen |= set(type(registry).known_tool_names())
    return namen


def test_the_prompt_only_promises_working_tools_while_they_all_work() -> None:
    """De prompt mag pas beweren dat elke tool draait als dat GEMETEN waar is.

    Hier stond tot 2026-09-21 het omgekeerde: de prompt MOEST zeggen "not connected yet". Dat
    was juist zolang geen van de piloottools bestond, en het is vandaag onwaar -- alle drie
    resolveren. Een waarschuwing die niet meer klopt is niet alleen verouderd: een model dat
    hoort dat zijn tools kunnen weigeren, kan niet meer bepalen of een opdracht uitvoerbaar is,
    en dat is de gemeten hoofdoorzaak van verzonnen toolresultaten.

    **Twee dingen die de eerste versie van deze test fout deed, beide in Gate 2 betrapt:**

    1. De belofte werd als SUBSTRING gezocht, met een `if` eromheen. Een herformulering zette
       de guard daarmee uit terwijl de belofte bleef staan (gemeten: belofte geherformuleerd +
       een niet-bestaande tool = GROEN). Nu komt de zin als constante uit de generator en wordt
       hij ONVOORWAARDELIJK geeist.
    2. De vergelijking liep tegen het PROFIEL en tegen klasse-attributen van de registries. De
       belofte gaat over `allowed_tools` in het MANIFEST, en "aangesloten" gaat over de broker
       die de skill echt heeft. Beide zijn nu de bron.
    """
    generator = _load_generator()
    # Het GECOMMITTE manifest en niet de uitvoer van de generator: dat is het bestand dat de
    # agent bij het draaien inleest. Gemeten 2026-09-21 met het mutatieharnas: met de generator
    # als bron bleef deze test GROEN toen er een niet-aangesloten tool aan het gecommitte
    # manifest werd toegevoegd. Dat generator en bestand niet uiteenlopen is een APARTE vraag,
    # en die staat in `test_the_generator_and_the_committed_manifest_do_not_drift`.
    manifest = yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))
    prompt = str(manifest["system_prompt"])

    assert generator.TOOL_PROMISE in prompt, (
        "De belofte uit de generator staat niet in de prompt. Is hij geherformuleerd, dan is "
        "deze guard de plek om dat te merken: TOOL_PROMISE is de enige bron van die zin."
    )

    ontbrekend = sorted(set(manifest["allowed_tools"]) - _uitvoerbaar_voor_deze_skill())
    assert not ontbrekend, (
        "De prompt belooft dat elke gedeclareerde tool draait, maar deze tools uit het "
        f"manifest kan de broker van deze skill NIET uitvoeren: {ontbrekend}. Bouw ze, wire "
        "de bijbehorende registry in `BaseSpecialistAgent`, of haal ze uit het manifest -- in "
        "die volgorde van voorkeur. De belofte weghalen is de laatste optie, want dan kan het "
        "model niet meer bepalen of een opdracht uitvoerbaar is."
    )

    assert "never invent a tool result" in prompt, (
        "Het echte risico van een geweigerde tool-aanroep is fabricatie. De prompt moet "
        "expliciet verbieden een tool-resultaat te verzinnen."
    )

    # "will really run" is meer dan "de naam zit in een registry". Twee dingen vielen ertussen,
    # beide gemeten in Gate 2 ronde 2:
    #
    # 1. Het PERMISSIEPROFIEL. `test_als_skills_tool_permissions.py` eist alleen dat het profiel
    #    een DEELVERZAMELING van het manifest is, dus een tool uit het profiel halen en in het
    #    manifest laten staan hield alles groen -- terwijl `execute_tool` hem bij stap 0 weigert
    #    met "Permission denied". Voor een geprofileerde skill hoort het GELIJK te zijn.
    # 2. De HITL-STORE. Zonder `hitl_store` gooit elke HIGH-tool onvoorwaardelijk "HITLStore is
    #    not configured" -- dezelfde vorm als `local_registry = None`, de fout waarvoor deze
    #    guard is herbouwd.
    profieltools = set(_piloot_profieltools())
    manifesttools = {str(t) for t in manifest["allowed_tools"]}
    assert profieltools == manifesttools, (
        "Profiel en manifest van de piloot lopen uiteen (profiel, manifest): "
        f"{sorted(profieltools)} vs {sorted(manifesttools)}. De prompt belooft dat elke "
        "gedeclareerde tool draait; een tool zonder permissie wordt bij stap 0 geweigerd."
    )

    from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

    classifier = ToolRiskClassifier()
    if any(classifier.classify(t) is ToolRiskLevel.HIGH for t in manifesttools):
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        assert SkillsGapTrainingSkill(tenant_id=1).tools.hitl_store is not None, (
            "Het manifest declareert een HIGH-tool, maar de broker van deze skill heeft geen "
            "`hitl_store`. Dan weigert die tool onvoorwaardelijk met 'HITLStore is not "
            "configured' en is de belofte in de prompt onwaar."
        )


def test_the_generator_and_the_committed_manifest_do_not_drift() -> None:
    """De generator moet het gecommitte manifest van de piloot kunnen REPRODUCEREN.

    `main()` schrijft elk manifest onvoorwaardelijk. Liepen generator en artefact uit elkaar,
    dan zet EEN `python scripts/generate_skill_manifests.py` -- precies waarvoor het script
    bestaat -- het manifest terug naar iets anders dan wat er is gereviewd. Gemeten in Gate 2
    op 2026-09-21: de generator gaf nog de zes oude tools (drie ervan niet-bestaand) EN geen
    `manifest_version`, terwijl de prompt beloofde dat alles werkt. Alleen de prompt was
    meeveranderd.

    Drie velden, want dat zijn de drie die toen uit elkaar liepen.
    """
    committed = yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))
    generated = _load_generator().build_manifest(PILOT, PILOT_CLASS)

    afwijkend = {
        veld: (generated.get(veld), committed.get(veld))
        for veld in ("allowed_tools", "manifest_version", "system_prompt")
        if generated.get(veld) != committed.get(veld)
    }
    assert not afwijkend, (
        "Generator en gecommit manifest lopen uiteen op deze velden (generator, gecommit): "
        f"{afwijkend}. Werk beide bij met dezelfde inhoud; een generator die je niet kunt "
        "draaien zonder schade is geen generator."
    )


def test_profiled_skill_keeps_tool_call_contract() -> None:
    """Regressiebescherming: het mechanisme blijft ongewijzigd.

    De evaluatieset van dag 1 (test_skillsgaptraining_evaluation_set.py) eist deze
    onderdelen in de prompt die de LLM krijgt. Ze mogen niet sneuvelen bij het
    herformuleren van de bewering.
    """
    prompt = _pilot_prompt()

    assert "TOOL_CALL: tool_name" in prompt
    assert "allowed_tools" in prompt
    assert "ADR-015" in prompt
    assert "Never invent data" in prompt


@pytest.mark.security()
def test_profiled_skill_has_no_stopgap_marker() -> None:
    """IR-001-invariant, hier expliciet en niet alleen in de architectuurtest."""
    assert MARKER not in _pilot_prompt(), (
        "Een geprofileerde skill mag de tekst-only stopgap niet krijgen -- dat is de "
        "inconsistentie die IR-001 afdwong te voorkomen."
    )


def test_generated_pilot_prompt_matches_committed_manifest() -> None:
    """Drift-guard: generator en gecommit manifest moeten letterlijk gelijk zijn.

    Dit gat bestond nog niet als test en is precies waardoor IR-001 kon ontstaan:
    het manifest handmatig bijwerken zonder de generator laat een latere regeneratie
    stilletjes andere tekst opleveren. LET OP dat `main()` alle 135 manifesten EN alle
    135 skill-bronbestanden herschrijft -- die draai je dus niet even.
    """
    committed = yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8")) or {}

    assert str(committed.get("system_prompt") or "") == _pilot_prompt(), (
        "De system-prompt in skillsgaptraining.yml wijkt af van wat de generator "
        "produceert. Werk beide bij met dezelfde tekst."
    )


def test_the_generator_does_not_overwrite_a_manifest_with_an_agent_card(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Agentkaart dag 1: een handmatig onderhouden manifest met `agentkaart` wordt niet opnieuw gegenereerd.

    Mutatiebewijs (2026-10-24): `heeft_agentkaart` altijd onwaar -> deze test ROOD; de tegenrichting (een manifest zonder
    kaart wordt WEL gegenereerd) staat in `test_the_generator_still_regenerates_a_manifest_without_a_card`.
    """
    manifest = tmp_path / "x.yml"
    manifest.write_text("skill_id: x\nagentkaart:\n  eigenaar: iemand\n", encoding="utf-8")

    assert _load_generator().heeft_agentkaart(manifest) is True


def test_the_generator_still_regenerates_a_manifest_without_a_card(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = tmp_path / "y.yml"
    manifest.write_text("skill_id: y\n", encoding="utf-8")

    gen = _load_generator()
    assert (gen.heeft_agentkaart(manifest), gen.heeft_agentkaart(tmp_path / "bestaat_niet.yml")) == (False, False)
