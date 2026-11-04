# BE-TST-002 — Digital Twin Consent Test Correctie (opt-in)

## Status
APPROVED

## Sprint
SP-TST-001 (Integration test stabilisatie) — Dag 2

## Datum
2026-06-16

---

## Probleem

Twee tests in `tests/integration/test_digital_twin_user_journeys.py` faalden omdat
ze het opt-OUT model verwachtten (consent default = enabled), terwijl de productie-
implementatie correct het opt-IN model implementeert conform ADR-026 par. 2 en
GDPR Art. 7 (expliciete toestemming vereist).

**Test 1 failure:**
```
assert consent_response.json()["status"] == "enabled"
AssertionError: assert 'disabled' == 'enabled'
```

**Test 2 failure:**
```
assert struggle_body["needs_intervention"] is True
AssertionError: assert False is True
```
Log: `twin_ai_intervention_blocked_by_consent` — Joris had nooit expliciete consent
gegeven, dus de interventie werd correct geblokkeerd.

---

## Root Cause

De tests zijn geschreven op basis van een vroeg ontwerp dat opt-out gebruikte.
ADR-026 par. 2 stelt expliciet opt-in als default (GDPR Art. 7 — geen impliciete
toestemming voor profilering).

---

## Oplossing

**Bestand:** `tests/integration/test_digital_twin_user_journeys.py`

### Test 1 (Rookie — Maria)

1. Docstring gecorrigeerd: "opt-out model" → "opt-in model per ADR-026 GDPR Art. 7"
2. Assert 1 gecorrigeerd: `"enabled"` → `"disabled"`
3. Act 1b toegevoegd: expliciete PUT `/api/v1/learning/twin/consent` met `{"status": "enabled"}`
   zodat de rest van de test (tracking, DB-persistentie) geldig is

### Test 2 (Intermediate — Joris)

1. Consent-enable stap toegevoegd voor de 5x track-user-behavior calls:
   PUT `/api/v1/learning/twin/consent` met `{"status": "enabled"}`
2. Met actieve consent werken de tracking EN de struggle-interventie correct

---

## Verificatie

```bash
python -m pytest tests/integration/test_digital_twin_user_journeys.py -v --timeout=60
# Resultaat: 2 passed, 1 skipped

python -m pyright
# Resultaat: 0 errors
```

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `tests/integration/test_digital_twin_user_journeys.py` | Opt-in consent correctie (2 tests) |

---

## ADR-koppeling

- **ADR-026 par. 2:** Digital Twin privacy — opt-in als default, niet opt-out
- **GDPR Art. 7:** Expliciete toestemming vereist voor profilering


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: Digital twin consent test correctie: opt-in (disabled) als default per ADR-026 is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt Digital twin consent test correctie: opt-in (disabled) als default per ADR-026.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
