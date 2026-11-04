# Feature: BE-UTL-050 Foundation Datetime Guardrail Conformance

## Metadata
- **Feature ID:** `BE-UTL-050`
- **Titel:** Foundation Datetime Guardrail Conformance
- **Sprint:** ADR-029 Foundation Portal (Levend Monument)
- **Status:** IMPLEMENTATION
- **Auteur:** AI Agent (Senior Architect / Developer)
- **Datum:** 2026-09-12
- **Gerelateerde ADRs:** ADR-029 (Levend Monument Foundation Portal), CLAUDE.md / AGENTS.md Absolute Kwaliteitsregels (Regel 3: NOOIT datetime.now() of datetime.utcnow())
- **Frontend Tegenhanger:** `FE-SEC-008`

---

## 1. Doel & Context
In `CLAUDE.md` en `AGENTS.md` is een absolute projectregel vastgelegd:
`NOOIT datetime.now() of datetime.utcnow()`
Alle tijdsoperaties in het platform moeten uniform gebruikmaken van `src.core.shared.datetime_utils.utc_now()` en `to_utc()`. Dit voorkomt:
1. Subtiele runtime-bugs door naive datetimes versus timezone-aware datetimes.
2. Inconsistente microseconde-resolutie tussen verschillende operating systems (Windows vs Linux).
3. Breuken in audit-logketens en token-vervalberekeningen.

Tijdens de audit van de ADR-029 Foundation API zijn in `auth.py` en `content.py` nog directe aanroepen van `datetime.now(timezone.utc)` geïdentificeerd. `BE-UTL-050` elimineert deze afwijkingen en stelt 100% conformiteit veilig.

---

## 2. Technische Wijzigingen

### `src/core/api/v1/foundation/auth.py`
- Importeer `utc_now` uit `src.core.shared.datetime_utils`.
- Vervang `expires_at = datetime.now(timezone.utc) + timedelta(minutes=_MAGIC_LINK_EXPIRY_MINUTES)` door `expires_at = utc_now() + timedelta(minutes=_MAGIC_LINK_EXPIRY_MINUTES)`.
- Vervang `now = datetime.now(timezone.utc)` door `now = utc_now()`.

### `src/core/api/v1/foundation/content.py`
- Importeer `utc_now` uit `src.core.shared.datetime_utils`.
- In `update_content`: vervang `content.updated_at = datetime.now(timezone.utc)` door `content.updated_at = utc_now()`.
- In `delete_content`: vervang `content.updated_at = datetime.now(timezone.utc)` door `content.updated_at = utc_now()`.

---

## 3. Beveiliging & Guardrails
- **Timezone Safety:** `utc_now()` garandeert altijd `timezone.utc` awareness.
- **Fail-Secure Expiration:** Magic-link tokens en content updates worden op exact gecalibreerde UTC-tijd berekend.
- **Audit Integriteit:** Voldoet aan ISO 8601 UTC formaat vereisten.

---

## Trainingssamenvatting

- **Component**: Foundation Datetime Conformance (`BE-UTL-050`)
- **Doel**: Uniforme UTC-tijdshandhaving over de gehele Foundation API conform absolute projectregels.
- **Architectuurregel**: Geen enkele module mag `datetime.now()` of `datetime.utcnow()` aanroepen; altijd `src.core.shared.datetime_utils.utc_now()`.
- **Geverifieerd met**: `tests/unit/test_foundation_datetime_conformance.py` en bestaande auth & content unit tests.
- **Actor**: Systeem / Ontwikkelaar
  - **Flow**: API verwerkt authenticatie of contentmutatie -> Systeem roept `utc_now()` aan -> Tijdstempel wordt timezone-aware vastgelegd in UTC -> Token expires_at en model updated_at zijn consistent en audit-conform.
