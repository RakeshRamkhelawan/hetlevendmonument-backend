"""Een gecachet oordeel mag niet van de ene gebruiker naar de andere lekken (H1, OP-145).

Aanleiding, gemeten 2026-08-15 door beide Gate 2-reviewers, onafhankelijk van elkaar.
`OfficerVerdictCache.fingerprint()` bevatte `action_type`, `data_classification`, `user_role`,
`language`, `model_id` en `model_version` -- geen `user_id`. De sleutel is
`council:verdict:{tenant_id}:{officer}:{fp}`, dus per TENANT gedeeld. `user_role` was de enige
per-persoon-proxy en wordt nergens in de codebase gevuld; op het agent-pad is
`context_snapshot` bovendien leeg (`background_gate.py:113`), dus hij is voor iedereen `""`.

Tot SP-COUNCIL-GATE-001 was dat onschadelijk: het oordeel van de SecurityOfficer hing alleen
van de ACTIE af. Vanaf nu hangt het van de RECHTEN VAN DE AANVRAGER af
(`user_has_scope_for`). Daarmee wordt de gedeelde sleutel een rechtenverhoging: gebruiker A
(beheerder) laat `query_hr_database` goedkeuren, en gebruiker B zonder dat recht krijgt binnen
`cache_ttl_seconds = 60` een cache-hit waarbij de rechtencontrole nooit draait.

De cache is vandaag niet bedraad -- `build_council()` geeft geen `cache=` mee, dus
`_legacy_deliberate` draait -- maar hij WORDT bij opstart gebouwd en op
`app.state.council_cache` gezet (`app_lijfspan`-equivalent), inclusief een invalidator op
`rbac.role_changed`. De bedoeling is dus duidelijk dat hij ooit wordt aangesloten, en dan moet
deze eigenschap er al zijn.

**Mutatietest (2026-08-15), beide richtingen:**
- `"user_id": proposal.user_id` uit `fingerprint()` gehaald -> ROOD op
  `test_two_users_get_two_fingerprints`.
- Andere richting: `test_the_same_user_gets_one_fingerprint` blijft groen, dus "gooi er een
  willekeurige waarde in" is geen oplossing -- dan zou de cache nooit meer raken en was hij
  stilzwijgend uitgezet in plaats van veilig gemaakt.
"""

from __future__ import annotations

from typing import Any

import pytest


def _voorstel(user_id: int, **overrides: Any) -> Any:
    from src.core.copilot.council.types import DataClassification, Proposal, ProposalTrigger

    velden: dict[str, Any] = {
        "tenant_id": 1,
        "user_id": user_id,
        "trigger": ProposalTrigger.USER_REQUEST,
        "action_type": "query_hr_database",
        "action_params": {"tool": "query_hr_database"},
        "reasoning": "reden",
        "data_classification": DataClassification.INTERNAL,
        "confidence": 1.0,
        "model_id": "unknown",
        "model_version": "1.0",
        "context_snapshot": {},
    }
    velden.update(overrides)
    return Proposal(**velden)


@pytest.mark.unit
class TestTheFingerprintIsPerUser:
    def test_two_users_get_two_fingerprints(self) -> None:
        """De test die het punt draagt: zonder dit deelt een tenant zijn oordelen."""
        from src.core.copilot.council.cache import OfficerVerdictCache

        een = OfficerVerdictCache.fingerprint(_voorstel(user_id=101))
        twee = OfficerVerdictCache.fingerprint(_voorstel(user_id=202))

        assert een != twee, (
            "Twee verschillende gebruikers leveren dezelfde cachesleutel op. Het oordeel van "
            "de SecurityOfficer hangt sinds SP-COUNCIL-GATE-001 af van de rechten van de "
            "aanvrager, dus een gedeelde sleutel geeft de een de goedkeuring van de ander."
        )

    def test_the_same_user_gets_one_fingerprint(self) -> None:
        """De andere richting: de cache moet nog wel kunnen RAKEN.

        Zonder deze helft zou een willekeurige waarde in de vingerafdruk de eerste test halen
        en de cache stilzwijgend uitzetten -- dat lost niets op, het verbergt het alleen.
        """
        from src.core.copilot.council.cache import OfficerVerdictCache

        een = OfficerVerdictCache.fingerprint(_voorstel(user_id=101))
        twee = OfficerVerdictCache.fingerprint(_voorstel(user_id=101))

        assert een == twee, (
            "Twee identieke voorstellen van dezelfde gebruiker leveren verschillende sleutels "
            "op. De cache raakt dan nooit."
        )

    def test_the_action_still_separates_verdicts(self) -> None:
        """Vangnet: de bestaande velden mogen niet wegvallen bij deze wijziging."""
        from src.core.copilot.council.cache import OfficerVerdictCache

        een = OfficerVerdictCache.fingerprint(_voorstel(user_id=101))
        twee = OfficerVerdictCache.fingerprint(
            _voorstel(user_id=101, action_type="analyze_skill_gap")
        )

        assert een != twee, "Twee verschillende acties delen een cachesleutel."
