# Backend Feature Specification

## Metadata

- Feature ID: BE-GOV-002
- Feature naam: ARCH-004 governance test fix + GDPR-002 CVA portability export
- Status: APPROVED
- Auteur: SP-CVA-P1 Dag 2
- Reviewer: zie docs/backend/review/review-BE-GOV-002.md
- Datum: 2026-06-22
- Gerelateerde user story / ticket: AGENT-CVA-COUNCIL-AUDIT-2026-06-20 ARCH-004 + GDPR-002
- Gerelateerde router / module: src/core/services/cva_service.py, src/core/learning/gdpr_service.py
- Gerelateerde database tabellen: cva_conversations
- Versie: 1.0

---

## Doel en scope

### Doel

Twee audit bevindingen gesloten:

**ARCH-004**: De `test_cva_chat_uses_require_council_approval` test had een stale xfail marker
met kapotte import (`src.core.api.cva_chat` bestaat niet meer). `require_council_approval`
bestond al in `cva_service.py:210` + `cva_service.py:438`. Fix: xfail verwijderd, import
gerepareerd naar source-file text check.

**GDPR-002**: `export_user_data()` exporteerde alleen learning data. CVA conversaties
(persoonsdata, GDPR Art. 20 portability) ontbraken. Fix: `_load_cva_conversations()` methode
toegevoegd die `CVAConversation` ORM laadt met SEC-005 allowlist.

### In scope

- `test_gap_fixes.py::test_cva_chat_uses_require_council_approval` xfail verwijderd + import gerepareerd
- `LearningGDPRService._load_cva_conversations()`: selecteer CVAConversation op (tenant_id, user_id), limit 1000, order by created_at desc
- `LearningGDPRService._serialize_cva_conversation()`: allowlist-only fields (SEC-005 -- geen response_metadata, performance_data, attached_files, context_summary)
- `export_user_data()`: voegt `"conversations"` key toe aan data dict + telt mee in total_records

### Out of scope

- GDPR Art. 17 bulk delete van CVA conversaties (FE-005, Dag 3)
- Cursor-based paginering voor zware gebruikers (TODO(GDPR-002-LIMIT) in code)

---

## Build summary

- Nieuw gebouwd: `_load_cva_conversations()`, `_serialize_cva_conversation()` methodes
- Gewijzigd: `export_user_data()` data dict + total_records; test `test_gap_fixes.py`
- Beinvloede bestaande flows: GDPR portability export endpoint

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|---|---|---|---|---|
| 1 | _load_cva_conversations | async method | src/core/learning/gdpr_service.py | Nieuw |
| 2 | _serialize_cva_conversation | method | src/core/learning/gdpr_service.py | Nieuw |
| 3 | export_user_data | async method | src/core/learning/gdpr_service.py | Wijziging |
| 4 | test_cva_chat_uses_require_council_approval | test | tests/unit/ai_act_governance/test_gap_fixes.py | Wijziging |

---

## Technische details

### CVAConversation vs Conversation

CVAConversation (denormalized flat table) gebruikt in plaats van Conversation+ConversationMessage
vanwege drie blockers in de Conversation ORM:
- RC-005: `Conversation.user_id` is Integer nullable, CVAConversation.user_id is String NOT NULL
- RC-006: `ConversationMessage.timestamp` (niet `.created_at`)
- RC-008: geen `messages` relationship gedefinieerd op Conversation ORM

### SEC-005 Allowlist

Geexporteerde velden: id, session_id, conversation_turn, user_message, cva_response,
user_feedback, feedback_details, conversation_topic, conversation_category, keywords, created_at.

Uitgesloten (systeem-interne data, niet GDPR Art. 20 portability): response_metadata,
performance_data, attached_files, context_summary.

### Tests

- `tests/unit/learning/test_gdpr_portability_cva.py`: 3 tests GROEN
- `tests/unit/ai_act_governance/test_gap_fixes.py::test_cva_chat_uses_require_council_approval`: GROEN
- `tests/unit/learning/test_gdpr_service.py`: bijgewerkt (conversations key in expected dict)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-CVA-P1 Dag 2: ARCH-004 test fix (xfail verwijderd, require_council_approval al aanwezig in cva_service.py) + GDPR-002 CVA portability export (\_load_cva_conversations CVAConversation ORM, SEC-005 allowlist). 4 tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-CVA-P1 Dag 2: ARCH-004 test fix (xfail verwijderd, require_council_approval al aanwezig in cva_service.py) + GDPR-002 CVA portability export (\_load_cva_conversations CVAConversation ORM, SEC-005 allowlist). 4 tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
