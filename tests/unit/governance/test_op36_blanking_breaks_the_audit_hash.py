"""OP-36 fase 1 ("blanken bij een wisverzoek") is NIET uitvoerbaar zoals beschreven.

**De aanname die is verlopen.** ADR-036 OP-36 stelt als goedkoopste uitweg voor: bij een
art.-17-wisverzoek de kolommen `tool_audit_logs.tool_input` en `council_decisions.action_params`
leegmaken. De onderbouwing daarbij luidt letterlijk: "breekt de hash vandaag niet, want OP-28
stelt vast dat `tool_input` buiten `compute_audit_hash` valt".

Die onderbouwing was waar toen OP-36 werd geschreven (2026-08-04) en is het NIET MEER. OP-28 is
op 2026-08-26 gesloten door de vijf kolommen juist WEL in de hash op te nemen -- dat was de fix.
De remedie van OP-28 heeft de aanname van OP-36 ongeldig gemaakt, en dat is bij het sluiten van
OP-28 niet doorgetrokken naar OP-36.

**Wat hier gemeten is** (deze tests, geen redenering):

1. `tool_input` zit in de preimage van `compute_audit_hash`. Blanken maakt de OPGESLAGEN
   `audit_hash` onreproduceerbaar.
2. `action_params` zit in de canonieke JSON van de raadsketen EN wordt door
   `ChainVerifier._compute_canonical_json` daadwerkelijk HERBEREKEND. Blanken daar breekt de
   verificatie onmiddellijk en zichtbaar.
3. De enige verifier van de tool-keten (`ToolAuditRepository.verify_chain_integrity`) controleert
   uitsluitend de SCHAKELS (`previous_hash == vorige audit_hash`), niet de inhoud. Blanken van
   `tool_input` wordt daar dus NIET opgemerkt.

Punt 3 maakt het gevaarlijker, niet veiliger: blanken zou vandaag stilletjes de bewijswaarde van
elke geraakte rij vernietigen, en de eerste hercompute-verifier die ooit wordt toegevoegd meldt
dan manipulatie op precies de rijen die netjes zijn gewist. Daarom is de uitkomst van deze meting
STOP -- er wordt niets geblankt -- en niet "het kan want niemand kijkt".

**Waarom dit bestand GROEN is en niet rood.** Het legt een gemeten eigenschap van de huidige code
vast, geen gewenste-maar-ontbrekende fix. De bijbehorende blokkade tegen een toekomstige naieve
implementatie staat in
`tests/architecture/test_erasure_never_blanks_hash_covered_columns.py`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.copilot.audit.chain_verifier import ChainVerifier
from src.core.governance.models import CouncilDecisionRow, ToolAuditLog
from src.core.tool_broker.audit_utils import compute_audit_hash

#: De twee kolommen die ADR-036 OP-36 fase 1 wil leegmaken bij een wisverzoek.
#: Een regel per element; beide worden hieronder afzonderlijk gemeten.
ERASURE_TARGET_COLUMNS = {
    "tool_audit_logs.tool_input": "OP-36 fase 1 wil deze kolom blanken bij een wisverzoek",
    "council_decisions.action_params": "OP-36 fase 1 wil deze kolom blanken bij een wisverzoek",
}


def _tool_audit_chain(lengte: int) -> list[dict[str, Any]]:
    """Bouw een ECHTE keten, exact zoals `ToolAuditRepository.log_execution` dat doet.

    Geen nagebouwde hash: dit roept dezelfde `compute_audit_hash` aan als het schrijfpad, met
    `previous_hash` doorgeketend van rij naar rij.
    """
    rijen: list[dict[str, Any]] = []
    vorige: str | None = None
    for i in range(lengte):
        velden: dict[str, Any] = {
            "tenant_id": 1,
            "agent_id": f"agent-{i}",
            "tool_name": "local__read_file",
            "timestamp": datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            "status": "success",
            "output_hash": f"outputhash-{i}",
            "previous_hash": vorige,
            "tool_input": {"pad": "/home/betrokkene/cv.pdf", "digest": f"pseudonym-{i}"},
            "task_id": f"task-{i}",
            "error_detail": None,
            "hitl_ticket_ref": None,
            "hitl_approved_by": None,
        }
        rij = dict(velden)
        rij["audit_hash"] = compute_audit_hash(**velden)
        vorige = str(rij["audit_hash"])
        rijen.append(rij)
    return rijen


def _hercompute(rij: dict[str, Any]) -> str:
    """Herbereken de hash van een opgeslagen rij uit zijn eigen velden."""
    return compute_audit_hash(**{k: v for k, v in rij.items() if k != "audit_hash"})


class TestBlankingBreaksTheToolAuditChain:
    def test_an_untouched_chain_reproduces_its_own_hashes(self) -> None:
        """Vangnet. Zonder deze toets bewijst een mismatch hieronder niets."""
        rijen = _tool_audit_chain(3)

        for index, rij in enumerate(rijen):
            assert _hercompute(rij) == rij["audit_hash"], (
                f"Rij {index} reproduceert zijn eigen hash niet, terwijl er niets is gewijzigd. "
                "De meting hieronder zou dan niets aantonen."
            )

    def test_blanking_tool_input_makes_the_stored_hash_unreproducible(self) -> None:
        """DE KERNMETING. OP-36 beweert dat dit de keten niet raakt; dat is niet meer waar."""
        rijen = _tool_audit_chain(3)
        opgeslagen = rijen[1]["audit_hash"]

        rijen[1]["tool_input"] = None  # exact wat een blankende wisroute zou doen

        assert _hercompute(rijen[1]) != opgeslagen, (
            "Blanken van `tool_input` laat de hash ONGEWIJZIGD. Dan zou OP-36 fase 1 alsnog "
            "veilig zijn -- maar OP-28 heeft deze kolom juist IN de hash gebracht, dus deze "
            "uitkomst zou betekenen dat de OP-28-fix is teruggedraaid."
        )

    def test_the_only_verifier_of_this_chain_would_not_notice(self) -> None:
        """Waarom STOP, en niet "het kan want niemand kijkt".

        `ToolAuditRepository.verify_chain_integrity` toetst uitsluitend de schakels. Blanken
        blijft daar onzichtbaar terwijl de bewijswaarde van de rij wel weg is -- en de eerste
        hercompute-verifier die ooit wordt toegevoegd meldt manipulatie op elke gewiste rij.
        """
        rijen = _tool_audit_chain(3)
        rijen[1]["tool_input"] = None

        schakels_kloppen = all(
            rijen[i]["previous_hash"] == rijen[i - 1]["audit_hash"] for i in range(1, len(rijen))
        )

        assert schakels_kloppen is True, (
            "De schakelcontrole valt om na het blanken. Dat is niet wat hier wordt gemeten: het "
            "punt is juist dat de ENIGE verifier van deze keten het NIET merkt."
        )
        assert _hercompute(rijen[1]) != rijen[1]["audit_hash"], (
            "De inhoud is wel degelijk onreproduceerbaar geworden, ook al klopt de schakel nog."
        )


class TestBlankingBreaksTheCouncilChain:
    """De raadsketen, waar WEL een hercompute-verifier bestaat.

    Hier wordt een ECHTE `CouncilDecisionRow` gebouwd, geen `SimpleNamespace`. Een stub met de
    juiste attributen zou dezelfde hash opleveren, maar hij verbergt precies wat deze meting
    relevant maakt: `action_params` is in het schema `JSONB NOT NULL`. Een stub kan `None`
    aannemen zonder dat iets protesteert; de echte kolom niet.
    """

    @staticmethod
    def _rij(action_params: dict[str, Any] | None) -> CouncilDecisionRow:
        return CouncilDecisionRow(
            decision_id=uuid.UUID(int=2),
            proposal_id=uuid.UUID(int=1),
            tenant_id=1,
            user_id=7,
            timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
            verdict="APPROVED",
            trigger="USER_REQUEST",
            confidence=0.9,
            action_type="hire_candidate",
            action_params=action_params,
            message="bericht",
            data_classification="INTERNAL",
            model_id="model-a",
            model_version="v1",
            reasoning="onderbouwing",
            explanation_for_user="uitleg",
            deliberation_ms=12,
            officer_verdicts_hash="ovh",
            decision_hash="dh",
        )

    def test_blanking_action_params_breaks_the_recomputed_decision_hash(self) -> None:
        """Hier kijkt er WEL iemand: `ChainVerifier` herberekent deze canonieke JSON per rij."""
        verifier = ChainVerifier.__new__(ChainVerifier)  # de helper is puur, geen sessie nodig
        origineel = self._rij({"kandidaat": "pseudonym-abc", "salaris": 70000})

        canoniek = verifier._compute_canonical_json(origineel, "vorigehash", "USER_REQUEST")
        opgeslagen = hashlib.sha256(canoniek.encode("utf-8")).hexdigest()

        assert "action_params" in canoniek, (
            "`action_params` zit niet in de canonieke JSON. Dan zou blanken hier wel veilig "
            "zijn en klopt de ADR-036-tekst juist wel voor deze kolom."
        )

        geblankte_waarden: tuple[dict[str, Any] | None, ...] = (None, {})
        for geblankte_waarde in geblankte_waarden:
            geblankt = self._rij(geblankte_waarde)
            na = hashlib.sha256(
                verifier._compute_canonical_json(
                    geblankt, "vorigehash", "USER_REQUEST"
                ).encode("utf-8")
            ).hexdigest()

            assert na != opgeslagen, (
                f"Blanken van `action_params` naar {geblankte_waarde!r} laat de beslissingshash "
                "ongewijzigd. Dat zou betekenen dat de kolom niet meegehasht wordt, in strijd "
                "met `compute_canonical_json`."
            )

    def test_the_council_column_cannot_even_be_set_to_null_in_the_schema(self) -> None:
        """Tweede, onafhankelijke blokkade voor OP-36 fase 1 op de raadskolom.

        Zelfs als de hash geen bezwaar was, is `NULL` hier geen toegestane waarde. "Blanken"
        zou dus `{}` moeten zijn -- en dat verandert de hash net zo goed (hierboven gemeten).
        """
        assert CouncilDecisionRow.__table__.c["action_params"].nullable is False, (
            "`council_decisions.action_params` is nullable geworden. Dan is de tweede blokkade "
            "voor blanken weg en verandert de afweging in OP-36."
        )

    def test_the_tool_audit_column_is_nullable_which_is_why_this_is_a_silent_trap(self) -> None:
        """Waarom de tool-keten het gevaarlijkere geval is.

        `tool_input` MAG wel NULL zijn en de enige verifier van die keten controleert alleen de
        schakels. Blanken slaagt daar dus zonder enige weerstand -- en vernietigt stil de
        reproduceerbaarheid van de opgeslagen hash.
        """
        assert ToolAuditLog.__table__.c["tool_input"].nullable is True
