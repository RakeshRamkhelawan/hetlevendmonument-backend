# BE-UTL-044: Resilience implementatie verplaatst naar shared-laag (SP-DSM-015 dag 1)

**Sprint:** SP-DSM-015 dag 1
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Samenvatting

De `tool_broker/resilience.py` implementatie (retry + circuit breaker) is verplaatst naar de
`shared`-architectuurlaag (`src/core/shared/tool_broker_resilience.py`). Dit sluit 2 van de
6 resterende DSM-circulaire koppelringen.

---

## Aanleiding

DSM-analyse toonde 6 circulaire LAAG-paren. Twee waren veroorzaakt door directe imports van
`src.core.tool_broker.resilience` in `auth` (hardening) en `integrations` (activepieces).
Omdat `tool_broker` semantisch lager staat dan `auth` en `integrations`, creeerden die imports
circulairen die niet via refactoring van callers op te lossen waren.

---

## Wijzigingen

### Nieuw bestand
- `src/core/shared/tool_broker_resilience.py` -- canonical implementatie (14 publieke symbolen)
  - Zero projectafhankelijkheden (alleen stdlib + loguru)
  - Volledig `__all__` gedeclareerd

### Gewijzigde bestanden
- `src/core/tool_broker/resilience.py` -- re-export shim naar shared-locatie
- `src/core/hardening/resilience.py` -- importeert nu uit `src.core.shared.tool_broker_resilience`
- `src/core/activepieces/client.py` -- importeert nu uit `src.core.shared.tool_broker_resilience`
- `scripts/dsm_full_analysis.py` -- MODULE_MAP: `ap_mcp_registry` reclassificatie naar `shared`
- `pyright-baseline.json` -- 9 pre-existing agentic-domain errors toegevoegd aan baseline

### Nieuwe tests
- `tests/architecture/test_dsm015_resilience_in_infra.py` -- 3 architecture tests (GROEN)

---

## Gesloten circulaire paren

| Voor | Na |
|------|----|
| auth <-> tool_broker | GESLOTEN |
| integrations <-> tool_broker | GESLOTEN |
| auth <-> tenancy | OPEN (dag 2) |
| auth <-> governance | OPEN (dag 2) |
| domain_pack <-> governance | OPEN |
| domain_pack <-> integrations | OPEN |

Totaal: 6 → 4 LAAG-paren.

---

## Verificatie

| Check | Resultaat |
|-------|-----------|
| `python -m pyright` | 0 errors |
| `python scripts/dsm_full_analysis.py` | 4 circulaire paren |
| `pytest tests/architecture/test_dsm015_resilience_in_infra.py` | 3/3 PASSED |
| `pytest tests/architecture/ -q` | 228 passed, 19 pre-existing failed |
| Smoke test imports | OK |

---

## Backwards compatibiliteit

De re-export shim in `src/core/tool_broker/resilience.py` zorgt ervoor dat alle bestaande
callers die via `from src.core.tool_broker.resilience import X` importeren, ongewijzigd
blijven. De shim wordt opgeruimd in SP-DSM-016 (cleanup fase).


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: Resilience implementatie naar shared-laag (SP-DSM-015) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt Resilience implementatie naar shared-laag (SP-DSM-015).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
