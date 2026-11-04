# BE-GOV-010: Art. 17 Forget-Me Cascade in DSARService

**ID:** BE-GOV-010
**Sprint:** SP-DLP-002 Dag 3
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Probleemstelling

`DSARService.delete_user_data()` verwijderde alleen `C7Workflow` en `User` records.
`CVAConversation` records (tabel `cva_conversations`) — die `user_message` en `cva_response`
bevatten — bleven intact na een GDPR Art. 17 Right to Erasure request. Dit terwijl
`export_user_data()` deze records WEL exporteert. Delete en export waren inconsistent.

Aanvullend ontbrak `await self._db.commit()` in het hard-delete pad (pre-existing bug).

---

## Oplossing

### Hard delete pad

1. Workflow delete `except Exception` block: silent swallow vervangen door `logger.error(..., exc_info=True)` (backend-patterns regel 10).
2. Nieuw blok: fysieke delete van `CVAConversation` via `begin_nested()` savepoint, consistent met het `export_user_data()` patroon (regel 387).
3. `records_affected["conversations"]` = rowcount.
4. `await self._db.commit()` toegevoegd na user delete (ontbrak voorheen).

### Soft delete pad

1. Workflow soft-delete `except Exception` block: zelfde silent-swallow fix.
2. Nieuw blok: fysieke delete van `CVAConversation` (`is_active` kolom bestaat niet op dit model — fysieke verwijdering is de enige optie voor Art. 17 compliance).
3. `records_affected["conversations_deleted"]` = rowcount.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/governance/dsar_service.py` | CVAConversation delete hard+soft pad, commit fix, logger.error fixes |
| `tests/unit/gdpr/test_forget_me_cascade.py` | TDD tests (3 stuks) |
| `tests/unit/gdpr/__init__.py` | Package init |

---

## Ontwerpkeuzes

- **CVAConversation, niet Conversation**: de export leest `cva_conversations`; delete moet dezelfde tabel targeten voor GDPR-consistentie (Art. 5(2) accountability).
- **Fysieke delete in soft-delete pad**: `CVAConversation` heeft geen `is_active` kolom. Fysieke verwijdering van chatkopieën tijdens de grace period is correct — de `User` record heeft een grace period, de bericht-inhoud niet.
- **begin_nested() savepoint**: spiegelt het export-patroon; voorkomt dat een gefailde conversation-delete de outer session in aborted state brengt.
- **Lazy import**: `from src.core.conversations.models import CVAConversation` binnen de try-block — consistent met het workflow model patroon op regel 612/644.

---

## Test Coverage

| Test | Resultaat |
|------|-----------|
| `test_delete_user_data_handles_conversations` | GREEN (ROOD voor implementatie) |
| `test_delete_user_data_records_conversation_counts_in_audit` | GREEN (ROOD voor implementatie) |
| `test_delete_user_data_has_audit_log` | GREEN (was al GREEN) |

---

## Gate 3 Verificatie

- `python -m pyright src/core/governance/dsar_service.py`: 0 errors
- `ruff check src/core/governance/dsar_service.py`: All checks passed


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DLP-002 Dag 3: Art. 17 forget-me cascade -- CVAConversation delete (hard+soft) in dsar\_service.py, begin\_nested() savepoint, commit fix hard-delete pad, logger.error workflow blocks. 3 TDD tests GROEN. pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DLP-002 Dag 3: Art. 17 forget-me cascade -- CVAConversation delete (hard+soft) in dsar\_service.py, begin\_nested() savepoint, commit fix hard-delete pad, logger.error workflow blocks. 3 TDD tests GROEN. pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
