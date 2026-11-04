# BE-TSK-003 — CVA Tasks User-ID Fix (B-015)

**ID:** BE-TSK-003
**Sprint:** SP-W02
**Datum:** 2026-05-30
**Status:** APPROVED

---

## Samenvatting

Verwijdert de hardcoded `user_id=1` uit `src/core/tasks/cva_tasks.py`. Alle CVA-berichten
worden nu geattribueerd aan de werkelijke zender in plaats van altijd aan user 1.

---

## Bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/tasks/cva_tasks.py` | `user_id=1` vervangen door dynamische lookup uit `request_data` |
| `src/core/services/messaging/telegram.py` | `"user_id": sender.get("id")` toegevoegd aan `agent_request` |
| `src/core/services/messaging/whatsapp.py` | `user_id = "unknown"` vervangen door `user_id = None` (explicieter) |

---

## Root Cause (B-015)

`cva_tasks.py:65` had `user_id=1` hardcoded in de `cva_service.chat()` aanroep.
Gevolg: elk CVA-bericht werd in de audit trail en conversatie-database geattribueerd aan user 1,
ongeacht wie het bericht daadwerkelijk stuurde.

---

## Implementatie

### cva_tasks.py

```python
user_id_raw = request_data.get("user_id")

if user_id_raw is not None:
    try:
        user_id_int = int(user_id_raw)
    except (ValueError, TypeError):
        logger.warning("Invalid user_id value, using external sentinel: %s", user_id_raw)
        user_id_int = _EXTERNAL_USER_SENTINEL
else:
    user_id_int = _EXTERNAL_USER_SENTINEL  # 0 = anonymous/external user

response_data = await cva_service.chat(
    message=text,
    user_id=user_id_int,
    tenant_id=int(tenant_id),
)
```

`_EXTERNAL_USER_SENTINEL = 0` is de veilige fallback voor externe gebruikers (Telegram,
WhatsApp) waarbij nog geen intern `user_id` beschikbaar is.

### telegram.py

Voegt `"user_id": sender.get("id")` toe aan het `agent_request` dict.
Telegram sender IDs zijn integers en identificeren de zender uniek.

### whatsapp.py

Verandert `user_id = "unknown"` naar `user_id = None`. De commented-out DB-lookup
(phone number -> User record) blijft als TODO staan voor een latere sprint.

---

## Aanvullende kwaliteitsfixes (in dezelfde commit)

- Alle f-string logger calls vervangen door `%s` stijl (CLAUDE.md §10)
- `raise e` vervangen door bare `raise` (preserveert originele traceback)
- Ongebruikte imports opgeschoond

---

## Trainingssamenvatting

**Flow: CVA-bericht via Telegram verwerken**

| Veld | Waarde |
|------|--------|
| **Actor** | Dramatiq worker (background) |
| **Voorwaarde** | Telegram webhook ontvangen; `process_cva_message.send()` aangeroepen door TelegramGateway |
| **Actie** | Worker leest `user_id` uit `request_data` (Telegram sender ID), verwerkt CVA-bericht |
| **Systeemreactie** | `CVAService.chat()` aanroepen met werkelijk `user_id` i.p.v. hardcoded 1 |
| **Succesrespons** | Conversatie opgeslagen met juiste `user_id`; Telegram-antwoord verzonden |
| **Foutrespons** | Bij ongeldige `user_id`: WARNING gelogd, fallback naar 0 (external sentinel) |
| **Uitzonderingen** | WhatsApp: `user_id=None` -> sentinel 0 (DB-lookup niet geimplementeerd) |

---

## DoD

- [x] `user_id=1` niet meer aanwezig in `cva_tasks.py`
- [x] `request_data.get("user_id")` aanwezig in `cva_tasks.py`
- [x] Telegram caller voorziet `user_id`
- [x] WhatsApp caller is expliciet over ontbrekende `user_id` (None)
- [x] Veilige `int()` conversie met fallback
- [x] 6 unit tests groen (`test_sp_w02_cva_workflow_tasks.py`)
- [x] 488 regressietests groen
