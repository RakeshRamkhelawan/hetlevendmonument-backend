# BE-DSM-031 -- SP-DSM-015 Dag 2: AuditService ThreatLevel-ontkoppeling

**Sprint:** SP-DSM-015 Dag 2 (AUDIT-DSM-002)
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Probleem

`src/core/governance/services/audit_service.py` had een functie-lokale runtime-import
op regel 169:

```python
from src.core.security.security_manager import ThreatLevel
```

Dit sloot het circulaire pair `auth <-> governance`:
```
auth/* -> governance/audit_service -> security/security_manager -> auth/*
```

6 auth-bestanden importeren `log_security_event` uit `audit_service`.
`security_manager` importeert terug naar `jwt_handler` (auth), waardoor de cirkel dicht ging.

---

## Oplossing

### Change 1 -- Signature verbreding

```python
# VOOR:
severity: "ThreatLevel",

# NA:
severity: "ThreatLevel | str",
```

Maakt `AuditService.log_event` accepteert zowel `ThreatLevel` enum-instanties
als gewone strings. Bestaande callers hoeven niet aangepast te worden.

### Change 2 -- Opslaan via .value ipv .name

```python
# VOOR (opgeslagen uppercase enum-naam "HIGH"):
threat_level=severity.name,

# NA (opgeslagen lowercase enum-waarde "high"):
threat_level=str(getattr(severity, "value", severity)).lower(),
```

`ThreatLevel` is een `str, Enum` met lowercase waarden (`"low"`, `"medium"`,
`"high"`, `"critical"`, `"info"`). `severity.name` gaf de Python-identifier
in uppercase (`"HIGH"`). `getattr(severity, "value", severity)` geeft de
enum-waarde voor enum-instanties en de string zelf als fallback voor string-callers.
`.lower()` zorgt voor consistente lowercase opslag in alle paden.

### Change 3 -- Verwijdering runtime-import + enum-mapping

```python
# VOOR:
from src.core.security.security_manager import ThreatLevel
threat_level_map = {"low": ThreatLevel.LOW, ...}
severity = threat_level_map.get(derived_level.lower(), ThreatLevel.MEDIUM)

# NA:
severity = derived_level   # al lowercase: "low", "medium", "high", "critical"
```

`derived_level` is het resultaat van de bestaande `event_severity_map`-lookup
in `log_security_event`. Het is altijd een lowercase string. Directe doorgeving
elimineert de `ThreatLevel`-afhankelijkheid volledig.

---

## Impact

### Positief
- `auth <-> governance` circulair pair gesloten (SP-DSM-015 DoD)
- `AuditLog.threat_level` slaat nu consistent lowercase op (was mixed)
- Bestaande callers (`ThreatLevel.HIGH` etc.) werken via `getattr` duck-typing

### Neutraal
- `TYPE_CHECKING`-import van `ThreatLevel` op regel 15-16 blijft staan (correct patroon)
- Bestaande DB-rijen met uppercase `threat_level` worden niet gemigreerd
  (backfill is een optionele opschoning, geen vereiste)

### Risico's gemitigeerd
- `getattr(severity, "value", severity)` werkt voor beide input-typen
- `test_log_event_creates_database_record` bijgewerkt: `severity.name` -> `severity.value`

---

## Gewijzigde bestanden

| Bestand | Type | Beschrijving |
|---------|------|--------------|
| `src/core/governance/services/audit_service.py` | fix | ThreatLevel runtime-import verwijderd |
| `tests/architecture/test_dsm015_audit_no_circular.py` | test | Rode arch-test voor AUDIT-DSM-002 |
| `tests/unit/test_audit_service_unit.py` | test fix | `.name` -> `.value` in assertion |

---

## Verificatie

- Arch-suite: 248 passed (was 247 + 1 nieuwe), 0 failed, 13 xfailed
- Gerichte unit-tests: 251 passed, 24 skipped, 9 xfailed
- Pyright: geen nieuwe errors in gewijzigde bestanden
- Rode test was ROOD voor de fix, GROEN na de fix


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DSM-015 Dag 2: ThreatLevel runtime-import uit audit_service verwijderd. auth<->governance circulair gesloten. getattr(.value) duck-typing. 248 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DSM-015 Dag 2: ThreatLevel runtime-import uit audit_service verwijderd. auth<->governance circulair gesloten. getattr(.value) duck-typing. 248 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
