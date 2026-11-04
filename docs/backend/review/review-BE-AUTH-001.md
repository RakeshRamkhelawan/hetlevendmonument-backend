# Review: BE-AUTH-001 -- trace:read + twin:read formaliseren in OAuth2Scope, rollen en PermissionGate

**Reviewer:** code-review agent (Gate 2, SP-FE-2G backlog)
**Status:** APPROVED
**Datum:** 2026-07-07

---

## A. EINDOORDEEL

APPROVED

---

## B. SAMENVATTING

De specificatie beschrijft correct de formalisering van `trace:read` en `twin:read` in de backend OAuth2Scope enum, de rol-scope toewijzing en de frontend PermissionGate voor `/trace/:executionId`. De broncode komt overeen met de spec. De ontbrekende trainingssamenvatting is toegevoegd tijdens deze review.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- Geen. Backend enum, rol-scope mapping en frontend route-gate zijn allemaal gedocumenteerd.

### 2. Functionele onduidelijkheden

- Geen. De verschillen tussen admin/user/developer en viewer zijn expliciet.

### 3. Technische onduidelijkheden

- Geen. De wijzigingen in `scopes.py`, `auth_service.py` en `App.tsx` zijn concreet.

### 4. Ontbrekende foutstatussen en edge cases

- Geen HTTP-endpoint is direct betrokken; fallback naar `/dashboard` is beschreven.

### 5. Acceptatiecriteria problemen

- Testbaar via type-check en rol-scope inspectie. Een directe unittest voor `_get_role_scopes` ontbreekt in de spec, maar is geen blocker.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is beperkt maar voldoende voor een scope-formalisering.

### 7. Trainingsdata problemen

- Opgelost: trainingssamenvatting toegevoegd met actor, voorwaarde, actie, systeemverwerking, succes-/foutrespons en uitzonderingen.

### 8. Structuur- en consistentieproblemen

- Geen.

### 9. Risico's voor implementatie, security of QA

- Laag risico: backend endpoints zijn nog niet afzonderlijk achter `require_scopes` geplaatst. Dit is bewust out of scope en expliciet benoemd.

---

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Trainingssamenvatting | Ontbrak in de oorspronkelijke spec | Vereist voor LLM-training en validatiescript | Toegevoegd in deze review |
| Low | Verificatie | Geen unittest voor rol-scope mapping vermeld | Scope mapping is kritisch voor toegangscontrole | Overweeg een unittest voor `_get_role_scopes` |

---

## E. ONTBREKENDE ITEMS

- Geen. Backend endpoint-afdwinging is bewust out of scope.

---

## F. VERBETERDE TEKSTVOORSTELLEN

- Niet van toepassing.

---

## G. RELEASE-OORDEEL

- Is dit document geschikt voor bouw / implementatie? Ja
- Is dit document geschikt voor QA en geautomatiseerd testen? Ja
- Is dit document geschikt voor LLM-training? Ja (na toevoeging trainingssamenvatting)
- Is dit document geschikt voor integratorhandleiding / API-documentatie? Ja
