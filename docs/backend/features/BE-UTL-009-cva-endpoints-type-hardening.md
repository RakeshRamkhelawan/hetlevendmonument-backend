# BE-UTL-009 — cva_endpoints.py Type Hardening

**ID:** BE-UTL-009
**Sprint:** SP-TYPE-01 Dag 3-4
**Type:** Utility (type refactoring)
**Status:** CLOSED — commits `c43a5493`, `520b713b`
**Bestand:** `src/core/api/cva_endpoints.py`

---

## Samenvatting

Vervanging van 13 `-> Any:` return-type annotaties door concrete types in de CVA agent endpoints. Bijkomend: verwijdering van ongebruikte legacy imports (`Dict, List, Optional, Union`) en verplaatsing van een inline `StreamingResponse` import naar module-niveau.

---

## Wijzigingen

| Functie | Voor | Na |
|---------|------|----|
| `create_managed_cva_agent` | `-> Any:` | `-> dict[str, Any]:` |
| `execute_managed_cva_agent` | `-> Any:` | `-> dict[str, Any]:` |
| `chat_endpoint` | `-> Any:` | `-> ChatResponse:` |
| `chat_with_cva` | `-> Any:` | `-> CVAChatResponse:` |
| `get_cva_status` | `-> Any:` | `-> CVAStatusResponse:` |
| `optimize_cva` | `-> Any:` | `-> dict[str, Any]:` |
| `get_cva_analytics` | `-> Any:` | `-> dict[str, Any]:` |
| `get_cva_health` | `-> Any:` | `-> dict[str, Any]:` |
| `get_cva_status_detail` | `-> Any:` | `-> dict[str, Any]:` |
| `shutdown_cva` | `-> Any:` | `-> dict[str, Any]:` |
| `list_conversations` | `-> Any:` | `-> dict[str, Any]:` |
| `get_conversation` | `-> Any:` | `-> dict[str, Any]:` |
| `chat_with_cva_streaming` | `-> Any:` | `-> StreamingResponse:` |

---

## Trainingssamenvatting

**Flow: Type-annotatie verbetering CVA endpoints**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Developer / type-safety sprint agent |
| Voorwaarde | CVA endpoints gebruiken `-> Any:` als return type |
| Actie | Return types vervangen door concrete Pydantic modellen of `dict[str, Any]` |
| Systeemverwerking | TDD: test schrijven (rood), type vervangen, test groen; ruff check |
| Succesrespons | 10/10 TDD tests groen, ruff 0 errors |
| Foutrespons | N.v.t. — type changes breken geen runtime gedrag |
| Uitzonderingen | `list_conversations`, `get_conversation` geven `dict[str, Any]` terug conform CVAService return type |
