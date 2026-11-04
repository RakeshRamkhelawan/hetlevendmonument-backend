# BE-UTL-035 -- _NullComplianceGuardian Sentinel (CG-001)

**ID:** BE-UTL-035
**Sprint:** SP-WE-20
**Datum:** 2026-06-01
**ADR:** ADR-027
**Status:** DONE
**Type:** Utility / Null Object Pattern

---

## Samenvatting

Vervangt de bare `object()` injectie in `_get_compliance_officer()` door een
semantisch correcte `_NullComplianceGuardian` sentinel class. Dit verwijdert een
code smell (CG-001) die auditors en toekomstige engineers misleidde en mypy/pyright
type-warnings produceerde.

---

## Component

### `_NullComplianceGuardian`

**Bestand:** `src/core/copilot/council/factory.py`

Null object class die het lege `ComplianceGuardian` Protocol satisfait. Heeft geen
afhankelijkheden en geen methoden. Communiceert via naamgeving duidelijk dat er
bewust geen echte guardian is gewired (post-MVP beslissing).

**Definitie:**

```python
class _NullComplianceGuardian:
    """Null object satisfying the empty ComplianceGuardian Protocol.

    NOTE: ComplianceGuardian Protocol (compliance_officer.py:53) has zero required
    methods -- object() satisfies it at runtime but communicates wrong intent to
    auditors and future engineers who expect an active guardian.

    A real ComplianceGuardianAgent wiring requires 5 dependencies:
    signal_bus, alert_manager, policy_engine, audit_writer, redis.
    That integration is deferred to post-MVP (track in CG-001 follow-up).
    """

    pass
```

### `_get_compliance_officer()` update

**Voor:**
```python
return ComplianceOfficer(
    compliance_guardian=object(),
    ai_act_classifier=_AIActClassifierAdapter(),
)
```

**Na:**
```python
return ComplianceOfficer(
    compliance_guardian=_NullComplianceGuardian(),
    ai_act_classifier=_AIActClassifierAdapter(),
)
```

---

## Rationale

`ComplianceGuardian` is een `Protocol` met `pass` als body -- nul vereiste methoden.
Een `object()` satisfait het Protocol technisch maar:

1. Geeft een verkeerd signaal: codelezer verwacht een actieve guardian
2. Produceert mypy `unused-ignore` warnings als stubs worden bijgewerkt
3. SOC 2 auditeurs zien een onverklaard `object()` injection

De echte `ComplianceGuardianAgent` vereist 5 constructor-dependencies en is bewust
uitgesteld naar post-MVP.

---

## Gedragsimpact

**Geen.** `self._guardian` wordt opgeslagen in `ComplianceOfficer.__init__` maar
nooit aangeroepen in deliberatie-paden. Nul runtime wijziging.

---

## Tests

**Bestand:** `tests/unit/test_council_factory.py`

4 regression tests in `TestComplianceOfficerGuardian`:

| Test | Beschrijving |
|------|--------------|
| `test_compliance_officer_guardian_is_not_bare_object` | Guardian mag geen bare `object()` zijn |
| `test_compliance_officer_guardian_class_is_named_null_sentinel` | Klassenaam bevat "Null" of "Sentinel" |
| `test_compliance_officer_guardian_satisfies_protocol` | Guardian is een echte instantie, niet None |
| `test_compliance_officer_singleton_returns_same_instance` | lru_cache geeft dezelfde instantie terug |

Alle 4 PASS.

---

## Trainingssamenvatting

### Flow: ComplianceOfficer instantiatie via factory

| Veld             | Waarde |
|------------------|--------|
| Actor            | Startup-code / Council factory |
| Voorwaarde       | `_get_compliance_officer()` wordt voor het eerst aangeroepen |
| Actie            | Factory instantieert `ComplianceOfficer` met `_NullComplianceGuardian` |
| Systeemverwerking| `lru_cache(maxsize=1)` slaat de singleton op; Protocol-check slaagt (nul methoden) |
| Succesrespons    | `ComplianceOfficer` singleton teruggegeven; guardian is `_NullComplianceGuardian` |
| Foutrespons      | Geen verwachte fout -- null object heeft geen afhankelijkheden |
| Uitzonderingen   | Als `lru_cache` corrupt raakt: `cache_clear()` en opnieuw aanroepen |
