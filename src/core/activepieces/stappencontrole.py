"""Welke stappen een klantflow in ActivePieces mag bevatten (wfb-dag1 stap 1).

Een AP-flow voert zijn stappen zelf uit, buiten de ToolBroker, de HITL en ons logboek om. Tot er
per `piece.actie` een risicoregel met mens-in-de-lus bestaat (ADR-040 B12), mag een flow daarom
alleen stappen bevatten zonder gevolg naar buiten: een trigger of schema, logica en opmaak. De
lijst staat in `src/core/config/workflow_stappen_allowlist.yml`; alles wat daar niet staat wordt
geweigerd, ook een AP-actie die morgen nieuw is.

De controle ziet twee vormen:
- de platte vorm van `FlowTransformer` (`trigger` + `actions` per id) bij opslaan;
- de geneste vorm die ActivePieces teruggeeft (`version.trigger` met `nextAction`, takken en
  `children`) bij aanzetten en uitvoeren van een flow die al in AP staat.
Een definitie zonder herkenbare trigger is niet te controleren en wordt geweigerd (fail-closed).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path

import yaml

from src.core.activepieces.transformer import FlowTransformer

_ALLOWLIST_PAD = Path(__file__).resolve().parents[1] / "config" / "workflow_stappen_allowlist.yml"

#: Sleutels waaronder een AP-stap zijn vervolgstappen bewaart (geneste vorm).
_VERVOLG_SLEUTELS = ("nextAction", "firstLoopAction", "onSuccessAction", "onFailureAction")

_VERWIJZING = "Gebruik voor een debiteur het blok Debiteuren (volgt)."

#: Toegestane sleutels per soort schrijfopdracht (`type`; None = een gewone flowbody).
#: Een gesloten lijst (Gate 2 HIGH-2): een soort of sleutel die hier niet staat, is niet
#: te controleren en wordt geweigerd -- ook een veilige trigger naast een `ADD_ACTION`.
_SLEUTELS_PER_SOORT: dict[str | None, frozenset[str]] = {
    None: frozenset(
        {"displayName", "description", "projectId", "folderId", "status", "trigger",
         "actions", "valid"}
    ),
    "IMPORT_FLOW": frozenset({"type", "request"}),
    "LOCK_AND_PUBLISH": frozenset({"type", "request"}),
    "CHANGE_STATUS": frozenset({"type", "request"}),
}
_STATUSSEN = frozenset({"ENABLED", "DISABLED"})


class NietToegestaneStap(ValueError):
    """Een flow bevat een stap die (nog) niet mag: hij stuurt iets naar buiten of voert vrij uit."""


@lru_cache(maxsize=1)
def _allowlist() -> tuple[frozenset[str], frozenset[tuple[str, str]]]:
    """(toegestane staptypen, toegestane (pieceName, actie- of triggernaam))."""
    data = yaml.safe_load(_ALLOWLIST_PAD.read_text(encoding="utf-8"))
    staptypen = frozenset(str(t) for t in data["staptypen"])
    paren = {
        (str(piece), str(naam))
        for sectie in ("triggers", "acties")
        for piece, namen in data[sectie].items()
        for naam in namen
    }
    return staptypen, frozenset(paren)


def toegestane_stappen() -> frozenset[tuple[str, str]]:
    """De toegestane (pieceName, actie- of triggernaam)-paren."""
    return _allowlist()[1]


def controleer_graaf(react_flow_graph: Mapping[str, object]) -> None:
    """Controleer een React-Flow-graaf zoals de builder hem opslaat.

    Zet hem om met DEZELFDE transformer die hem naar AP stuurt, zodat er geen tweede vertaling
    van stapnaam naar piece is die uit de pas kan lopen.
    """
    controleer_flowdefinitie(FlowTransformer.react_flow_to_activepieces(dict(react_flow_graph)))


def beoordeel_schrijfopdracht(opdracht: Mapping[str, object]) -> tuple[bool, bool]:
    """(controleer de opdracht zelf, controleer wat AP nu heeft) voor een schrijfopdracht.

    - de opdracht draagt stappen (een flowbody met `trigger`, of `IMPORT_FLOW` met de definitie
      onder `request`): die worden gecontroleerd;
    - publiceren (`LOCK_AND_PUBLISH`) of aanzetten (`status` of `CHANGE_STATUS` ENABLED): wat AP
      nu heeft wordt gecontroleerd -- OOK als er een veilige definitie bij zit;
    - alleen naam, beschrijving, map of uitzetten: niets te controleren.
    Een andere soort, een vreemde sleutel of een andere status wordt geweigerd.
    """
    soort = opdracht.get("type")
    if not (soort is None or isinstance(soort, str)) or soort not in _SLEUTELS_PER_SOORT:
        raise _niet_te_controleren(str(soort))
    if not set(opdracht) <= _SLEUTELS_PER_SOORT[soort]:
        raise _niet_te_controleren(str(soort or "flow"))
    verzoek = opdracht.get("request")
    verzoek = verzoek if isinstance(verzoek, Mapping) else {}
    if soort == "IMPORT_FLOW":
        return True, False
    if soort == "LOCK_AND_PUBLISH":
        return False, True
    status = verzoek.get("status") if soort == "CHANGE_STATUS" else opdracht.get("status")
    if status is not None and status not in _STATUSSEN:
        raise _niet_te_controleren(f"status {status}")
    return "trigger" in opdracht, status == "ENABLED"


def _niet_te_controleren(wat: str) -> NietToegestaneStap:
    return NietToegestaneStap(
        f"Deze wijziging van de flow ({wat}) is niet te controleren en wordt daarom niet "
        f"doorgegeven. {_VERWIJZING}"
    )


def controleer_flowdefinitie(definitie: Mapping[str, object]) -> None:
    """Gooit `NietToegestaneStap` bij de eerste stap die niet op de allowlist staat."""
    # ELKE plek met een trigger telt: de flow zelf, `version` (AP) en `request` (IMPORT_FLOW).
    basissen = [
        basis
        for basis in (definitie, definitie.get("version"), definitie.get("request"))
        if isinstance(basis, Mapping) and isinstance(basis.get("trigger"), Mapping)
    ]
    if not basissen:
        raise NietToegestaneStap(
            "De flow is niet te controleren: er is geen trigger gevonden. Hij wordt daarom niet "
            "opgeslagen, aangezet of uitgevoerd."
        )
    for basis in basissen:
        trigger = basis.get("trigger")
        stappen = list(_genest(trigger)) if isinstance(trigger, Mapping) else []
        acties = basis.get("actions")
        if isinstance(acties, Mapping):
            stappen += [stap for stap in acties.values() if isinstance(stap, Mapping)]
        for stap in stappen:
            _controleer_stap(stap)


def _genest(stap: Mapping[str, object]) -> Iterator[Mapping[str, object]]:
    """De stap en alle stappen die eronder hangen, in de geneste AP-vorm."""
    yield stap
    for sleutel in _VERVOLG_SLEUTELS:
        volgende = stap.get(sleutel)
        if isinstance(volgende, Mapping):
            yield from _genest(volgende)
    kinderen = stap.get("children")
    if isinstance(kinderen, list):
        for kind in kinderen:
            if isinstance(kind, Mapping):
                yield from _genest(kind)


def _controleer_stap(stap: Mapping[str, object]) -> None:
    staptypen, paren = _allowlist()
    naam = str(stap.get("name") or stap.get("displayName") or "?")
    soort = str(stap.get("type") or "")
    if soort in staptypen:
        return
    if soort in ("PIECE", "PIECE_TRIGGER"):
        settings = stap.get("settings")
        settings = settings if isinstance(settings, Mapping) else {}
        piece = str(settings.get("pieceName") or "")
        actie = str(settings.get("actionName") or settings.get("triggerName") or "")
        if (piece, actie) in paren:
            return
        raise NietToegestaneStap(
            f"De stap '{naam}' ({piece} {actie}) stuurt mogelijk iets naar buiten en is nog niet "
            f"toegestaan. {_VERWIJZING}"
        )
    if soort == "CODE":
        raise NietToegestaneStap(
            f"De stap '{naam}' voert eigen code uit en is niet toegestaan. {_VERWIJZING}"
        )
    raise NietToegestaneStap(
        f"De stap '{naam}' heeft een onbekend staptype ({soort or 'leeg'}) en is daarom niet "
        f"toegestaan. {_VERWIJZING}"
    )
