# Backend Feature Review -- BE-DEB-001

## Metadata

- **Review ID:** review-BE-DEB-001
- **Feature ID:** BE-DEB-001
- **Feature naam:** Debiteurenagent dag 2 -- tools, goedkeuring, handmatige invoer
- **Reviewer:** code-reviewer + security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-05
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED

Beide reviewers: GO, geen P0/P1 of CRITICAL/HIGH.

## B. Bevindingen en wat ermee is gedaan

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| Geen pad zet `_requester_kind="agent"`; de A2A-tak beschermt vandaag niets | MEDIUM | Docstring rechtgezet; de tak staat klaar voor het eerste agent-tot-agentpad |
| `invoice_number`/`customer_name` zonder stuurteken-controle (header-injectie bij latere SMTP) | MEDIUM | Opgelost: patroon zonder stuurtekens in beide schema's |
| `hitl_ticket_ref` NULL bij ontbrekende ref, UNIQUE ontdubbelt dan niet | LOW/P2 | Opgelost: `_send` weigert zonder ticketref; test toegevoegd |
| Geen rijvergrendeling tussen `betaald`-controle en schrijven | LOW | Gelaten: race met een gelijktijdige PATCH is smal; dag 3/4 |
| Zelfgoedkeuring nu ook voor HR-tools zolang vier ogen uit staat | P2 | Gevolg van ADR-039; gemeld aan Rakesh (sjablonen met vier ogen aan) |
| `_requester_kind` overleeft de besluitprojectie niet | P2 | Gelaten: alleen nodig zolang het ticket open staat |
| CHECK-migratie faalt bij bestaande foute rijen | P2 | Aangekondigd in de brief; vooraf meten bij uitrol |
