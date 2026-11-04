# Backend Feature Specification

## Metadata

- Feature ID: BE-RTR-004
- Feature naam: Signal Router — Department Topic Resolution
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: AGNT-002 (SP-F)
- Gerelateerde router / module: `src/core/events/signal_router.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: Geen
- Versie: 1.0

---

## Doel en scope

### Doel

Bepaal welke event topics een agent moet ontvangen op basis van zijn departement, en resolve het Redis Pub/Sub kanaal voor een topic binnen een tenant.

### In scope

- `DEPARTMENT_TOPICS` mapping
- `resolve_topics()` functie
- `resolve_channel()` functie

### Out of scope

- SignalBus implementatie (bestaand)
- AgentRunner pacemaker (BE-SVC-006)
- WebSocket event delivery

---

## Build summary

- **Nieuw gebouwd:** `src/core/events/signal_router.py`
- **Gewijzigd:** Geen
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** AgentConfig creatie (topics worden hierdoor bepaald)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-RTR-004 | Signal Router | Utility module | `src/core/events/signal_router.py` | Nieuw | Agent signal subscription |

---

## API-flows

N.v.t. — Interne utility, geen HTTP API.

---

## Detaildocumentatie per artefact

---

## [BE-RTR-004] Signal Router

### 1. Type

Utility module / topic resolver

### 2. Locatie

- Bestandspad: `src/core/events/signal_router.py`
- Klasse / functie: `resolve_topics()`, `resolve_channel()`

### 3. Gerelateerde flow

Agent signal subscription

### 4. Doel

Mapping van departement namen naar standaard event topics, en naamgeving van Redis kanalen per tenant/topic combinatie.

### 5. Functionele beschrijving

- Bij activatie van een departement (via `DepartmentActivationHandler`) worden de default topics voor dat departement opgehaald.
- Een agent kan ook custom topics subscriben die samengevoegd worden met de departement defaults.
- Het kanaal voor een topic wordt opgebouwd als `organism:{tenant_id}:{topic}`.

### 6. Technische beschrijving

```python
_DEPARTMENT_TOPICS_RAW: dict[str, tuple[str, ...]] = {
    "hr": ("user.created", "user.updated", ...),
    "finance": ("invoice.received", "invoice.paid", ...),
    "it": ("alert.critical", "alert.warning", ...),
    "operations": ("task.created", "task.completed", ...),
    "sales": ("lead.created", "lead.converted", ...),
    "marketing": ("campaign.launched", "campaign.completed", ...),
}

DEPARTMENT_TOPICS: Final[MappingProxyType[str, tuple[str, ...]]]

async def resolve_topics(department: str | None, custom_topics: list[str] | None = None) -> list[str]:
    base = list(DEPARTMENT_TOPICS.get(department or "", ()))
    extra = custom_topics or []
    # Deduplicatie behoudt volgorde
    ...
    return result

async def resolve_channel(topic: str, tenant_id: int) -> str:
    return f"organism:{tenant_id}:{topic}"
```

### 7. Zichtbaarheids- en toegangsregels

- Geen auth; pure utility functie.
- `tenant_id` wordt doorgegeven vanuit caller context.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `department` is case-sensitive (lowercase verwacht).
- `custom_topics` wordt gedupliceerd met `base`; duplicaten verwijderd.
- `tenant_id` moet positief integer zijn.

### 11. Business rules

- BR-001: Onbekend departement retourneert lege topic lijst (geen exception).
- BR-002: Custom topics worden altijd samengevoegd met departement defaults.
- BR-003: Kanaal naam format is `organism:{tenant_id}:{topic}` (niet aanpasbaar).

### 12. Afhankelijkheden

- Geen externe dependencies.

### 13. Foutafhandeling

- Geen exceptions geraised.
- Onbekend departement -> lege lijst.
- `None` custom_topics -> ignored.

### 14. Transacties en data-integriteit

- Geen DB interactie.

### 15. Telemetry / logging / tracing

- Geen directe logging.
- Caller (DepartmentActivationHandler) logt resolved topics.

### 16. Caching

- `DEPARTMENT_TOPICS` is immutable `MappingProxyType`; veilig voor global access.

### 17. Acceptatiecriteria

- [ ] `resolve_topics("sales")` retourneert minstens 4 topics
- [ ] `resolve_topics("unknown")` retourneert `[]`
- [ ] `resolve_topics("sales", ["custom"])` bevat "custom"
- [ ] `resolve_channel("lead.created", 1)` == `"organism:1:lead.created"`
- [ ] Duplicaten in custom_topics worden verwijderd

### 18. Integratoruitleg

- Gebruik `resolve_topics(department)` om default topics op te halen.
- Gebruik `resolve_channel(topic, tenant_id)` voor Redis Pub/Sub kanaal naam.
- Nieuw departement toevoegen: update `_DEPARTMENT_TOPICS_RAW` dict.

### 19. Trainingssamenvatting

- **Actor:** DepartmentActivationHandler
- **Voorwaarde:** Departement naam bekend
- **Actie:** `resolve_topics(department)`
- **Systeemverwerking:** Lookup in DEPARTMENT_TOPICS mapping, merge met custom topics, deduplicatie
- **Succesrespons:** List van topic strings
- **Foutrespons:** Lege list bij onbekend departement
- **Uitzonderingen:** Geen

---

## Integratorhandleiding

N.v.t. — Interne utility.

---

## Open aannames

- Departement namen zijn lowercase.
- Topic strings bevatten geen `:` (kanaal naam scheidingsteken).

## Open vragen

- Moeten topics uit een database tabel komen i.p.v. hardcoded dict?
- Moet er een `resolve_topics_bulk()` functie komen voor meerdere departementen?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Hardcoded topics = code deploy nodig bij wijziging | Medium | Medium | Overweeg database-gedreven topics post-MVP |

---

## QA-checks

- [x] Happy path getest
- [x] Onbekend departement getest
- [x] Custom topics merge getest
- [x] Deduplicatie getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Review door reviewer-prompt: APPROVED
