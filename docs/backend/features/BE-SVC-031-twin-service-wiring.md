# BE-SVC-031 -- twin_service Wiring in CopilotService (SP-WE-03)

**ID:** BE-SVC-031
**Sprint:** SP-WE-03
**Datum:** 2026-05-31
**ADR:** ADR-025, ADR-026

---

## Samenvatting

Digital Twin was nooit actief in productie: `dependencies.py` instantieerde `CopilotService`
zonder `twin_service=` parameter (WE-016). De branch `if self._twin_service:` in
`service.py:178` vuurde NOOIT. Dit is nu gecorrigeerd.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/dependencies.py` | `_create_twin_service(db, redis)` aangeroepen; resultaat doorgegeven als `twin_service=` aan `CopilotService` |
| `src/core/copilot/council/coordinator.py` | `_build_context()` leest `twin_profile` uit `proposal.context_snapshot.get("twin_profile")` ipv hardcoded `None` |
| `src/core/learning/observers/ooda_loop_observer.py` | OODA stub subscriber aangemaakt (post-MVP TODO per ADR-025 §3.4) |

## Architectuurbeslissing

twin_profile wordt via `proposal.context_snapshot` doorgegeven aan `DeliberationContext`,
niet via een eigen `twin_service` parameter op `AgentCouncil`. Dit houdt de `AgentCouncil`
interface ongewijzigd en volgt de bestaande data-flow: `CopilotService` haalt het profiel op,
`ProposalBuilder` zet het in `context_snapshot`, `coordinator._build_context()` leest het.

## Trainingssamenvatting

### Flow 1: Digital Twin context injecteren in Copilot-beslissing

- **Actor:** CopilotService.handle_turn() (systeem)
- **Voorwaarde:** twin_service geinjectioneerd via dependencies.py; gebruiker heeft consent gegeven
- **Actie:** handle_turn() roept twin_service.get_profile(user_id, tenant_id) aan; resultaat in context_snapshot
- **Systeemreactie:** PracticalTwinService.get_profile() controleert consent via TwinConsentManager; bij consent=True retourneert twin profiel; bij consent=False retourneert {}
- **Succesrespons:** DeliberationContext.twin_profile bevat gebruikerscontext; PrivacyOfficer kan consent valideren
- **Foutrespons:** twin_service.get_profile() faalt -> twin_profile=None (best_effort via except in handle_turn); geen crash
- **Uitzonderingen:** twin_service=None (niet geinjectioneerd) -> twin_profile altijd None (backward compatible)
