# Backend Feature Review -- BE-DEB-002

## Metadata

- **Review ID:** review-BE-DEB-002
- **Feature ID:** BE-DEB-002
- **Feature naam:** Debiteurenagent dag 3 -- agent starten, vier ogen als standaard en instelbaar
- **Reviewer:** code-reviewer + security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-05
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED

Beide reviewers: GO, geen CRITICAL of HIGH.

## B. Bevindingen en wat ermee is gedaan

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| Brief vergeleken met een voorbeeld van voor het rijslot | MEDIUM | Opgelost: opnieuw renderen uit de vergrendelde rij |
| Dubbele `receivable_ids` geven dubbele tickets | MEDIUM | Opgelost: ontdubbeld, test toegevoegd |
| Auditregel vier ogen na de commit, in best_effort | MEDIUM | Gelaten: projectregel (backend-patterns par. 3); gemeld |
| Beheerder kan vier ogen uitzetten en zelf goedkeuren | MEDIUM | Gevolg van ADR-039; auditregel legt het vast |
| Reden van de Council gaat naar het scherm | LOW | Gelaten: bevat geen brieftekst |
| 20 Council-oordelen per aanroep bij 10/min | LOW | Gelaten; later strakkere limiet per tenant |
| Oude tickets zonder `recipient_name` worden geweigerd | LOW | Bewust (fail-safe), in de spec genoemd |

## Review nazorg scenario 5 (2026-10-05)

Code-reviewer en security-reviewer (subagenten): beide GO, geen CRITICAL/HIGH.

| Bevinding | Ernst | Besluit |
|---|---|---|
| `websocket_auth` maakte van `tenant_id: true` tenant 1 | MEDIUM | Opgelost: gedeelde strikte lezer `tenant_from_claim`, tests |
| Superscript-cijfer gaf ValueError i.p.v. 1008 | MEDIUM | Opgelost: `isascii()`, ook tenant 0 en negatief geweigerd |
| Ticket in een teruggedraaid SAVEPOINT kan toch gemeld worden | LOW | Gelaten: alleen de ref, alleen de eigen tenant; client haalt op en vindt niets |
| Geen event loop bij commit: melding vervalt met waarschuwing | LOW | Gelaten: best_effort; alle huidige paden zijn async |
| `notify_new_ticket` heeft geen productie-aanroeper meer | LOW | Gelaten met docstring; guard verbiedt hergebruik bij aanmaken |
