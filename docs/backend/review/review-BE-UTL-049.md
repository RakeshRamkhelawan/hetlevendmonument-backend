STATUS: APPROVED

# Review BE-UTL-049 -- refuse_agent_control

**Scope:** `src/core/api/agent_control_unavailable.py`

**Reviewer:** onafhankelijke code-reviewer, zonder context en zonder aannames (Gate 2).

**Omgeving:** Python 3.13, FastAPI 0.121.1, Windows 11, project-venv.

---

## A. Eindoordeel

**APPROVED**

## B. Samenvatting

Een kleine module met een enkele verantwoordelijkheid, die precies zo klein blijft als hij hoort
te zijn: alleen `fastapi` en `logging` als afhankelijkheid, zodat beide mount-paden hem kunnen
gebruiken zonder importcyclus. Het `NoReturn`-returntype maakt het contract afdwingbaar in plaats
van beschrijvend. De docstring bevat een gemeten waarneming over de responsvorm die in de rest
van de codebase nergens stond en die een integrator anders niet had kunnen vinden.

## C. Bevindingen per categorie

### 1. Coverage gaps

Geen. Er is een pad en dat pad is getest, zowel rechtstreeks als via een `TestClient`.

### 2. Functionele onduidelijkheden

Geen.

### 3. Technische onduidelijkheden

Opgelost. De moduledocstring legde eerst wel de UITKOMST vast (de foutcode belandt op
`body.detail.error.code`) maar niet het MECHANISME. Nu staat de exacte plek erbij
(`src/core/exceptions/handlers.py:72-82`) en dat het bestaand platformgedrag is voor elke
`HTTPException` met een dict-detail, niet iets eigens van deze module.

### 4. Ontbrekende foutstatussen en edge cases

Niet van toepassing: de functie heeft geen invoer die tot een ander pad leidt.

### 5. Acceptatiecriteria-problemen

Geen.

### 6. Integratorhandleiding

Van toepassing op de endpoints, niet op de helper; zie `review-BE-EP-035.md`.

### 7. Trainingsdata

In orde.

### 8. Structuur- en consistentieproblemen

Opgelost: de OpenAPI-beschrijving die zes keer in twee routerbestanden stond, staat nu hier als
`UNAVAILABLE_RESPONSES`.

### 9. Risico's voor implementatie, security of QA

Geen. De module raakt geen database, cache of wachtrij, en logt geen persoonsgegevens.

---

## D. Issue register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Correctie | Status |
| --- | --- | --- | --- | --- | --- |
| Low | docstring, `requested_by` | Het veld heette in de eerste versie een "auditspoor" terwijl er geen audit-entry wordt geschreven. | Een verkeerde term in een docstring wordt door de volgende lezer als feit overgenomen. Iemand die een auditspoor zoekt, vindt het niet. | Expliciet benoemd dat dit uitsluitend naar de applicatielog gaat en GEEN audit-entry is, met de reden erbij: een 501 is geen autorisatiebesluit en geen gegevensmutatie. | Opgelost |
| Low | `_MESSAGE` en `UNAVAILABLE_RESPONSES` | Twee teksten die hetzelfde uitleggen, in twee talen. | Een gepubliceerde specificatie die half Nederlands en half Engels is, belast de clientontwikkelaar zonder reden. | Beide Engels, passend bij de bestaande OpenAPI-beschrijvingen in dezelfde routers. | Opgelost |

---

## E. Ontbrekende items

Geen.

## F. Verbeterde tekstvoorstellen

Verwerkt.

## G. Release-oordeel

- Geschikt voor implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding: n.v.t. (interne helper).

---

## Gemeten bewijs

| Meting | Uitkomst |
| --- | --- |
| `ruff check src/core/api/agent_control_unavailable.py` | All checks passed |
| `mypy` op de module | Success: no issues found |
| `pyright` met expliciet bestandsargument | 0 errors, 0 warnings |
| Byte-scan op non-ASCII en regels > 100 tekens | 0 en 0 |
| FastAPI-gedrag bij `-> NoReturn` zonder `response_model=None` | `FastAPIError` bij het laden van de route (gemeten, FastAPI 0.121.1) |
| FastAPI-gedrag bij `-> NoReturn` MET `response_model=None` | route laadt, 501 komt aan, OpenAPI bevat de 501 |

*Reviewer: onafhankelijke code-reviewer (Gate 2) | Datum: 2026-08-31*
