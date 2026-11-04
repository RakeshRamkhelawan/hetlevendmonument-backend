# AI Act Risk Assessment - SanskritiSetu Copilot

## 1. Systeem Classificatie
**Systeem:** SanskritiSetu AI Copilot
**Toepassingsgebied:** Enterprise workflow automatisering en beslissingsondersteuning.
**Kwalificatie:** Het systeem kwalificeert als **Low/Minimal Risk** onder de EU AI Act.

## 2. Rechtvaardiging van de Kwalificatie
De AI Copilot is ontworpen met deterministische veiligheidsmechanismen die de autonomie van het onderliggende Large Language Model inperken:

1. **Deterministische Council (ADR-027):** De uitkomst van het LLM (de "Proposal") is slechts een suggestie en wordt altijd getoetst door een rule-based Council van 7 onafhankelijke Officers.
2. **Human-in-the-Loop (HITL):** Zodra een voorstel risicovol wordt geacht (bijv. door de SecurityOfficer of RiskOfficer), wordt de executie gepauzeerd en vereist het systeem een expliciete handmatige goedkeuring van de gebruiker (`REQUIRE_HITL`).
3. **Transparantie-eis (Art. 52):** De UI-componenten (zoals het AI Copilot Panel) zijn voorzien van de expliciete waarschuwing: *"Dit is een AI-assistent"*. De gebruiker wordt nooit misleid over de aard van de interactie.
4. **Verklaarbaarheid (Right-to-Explanation):** Elke beslissing, inclusief weigeringen (BLOCKED), is cryptografisch gehasht opgeslagen. Via de `AuditViewer` kan een gebruiker direct inzien *waarom* een bepaalde AI-actie is goedgekeurd of afgewezen.

## 3. High-Risk Beoordeling
Hoewel het systeem binnen enterprise omgevingen wordt gebruikt, neemt het geen automatische beslissingen over werkgelegenheid, kredietwaardigheid of vitale infrastructuur zonder menselijke validatie (HITL). Daardoor ontsnapt het aan de High-Risk categorie (Bijlage III van de AI Act).

## 4. Monitoring en Logging
Via een SHA-256 hash-chain en sinds 2026-08-10 een DAGELIJKSE integriteitscontrole (`AuditTrailVerificationJob`, ingepland in `src/workers/scheduler.py`) wordt wijziging en verwijdering van de audit-trail aantoonbaar gemaakt. Afwijkingen verhogen `audit_chain_tampering_total` en vuren de alertregel `AuditChainTamperingDetected`.

~~wordt verzekerd dat de audit-trail onweerlegbaar en tamper-proof is~~ -- **die formulering was te sterk en is ingetrokken.** De keten is *tamper-evident* voor een aanvaller zonder schrijfrechten op de database, niet tamper-proof: de hash is ongesleuteld, dus wie de tabel kan schrijven kan hem herberekenen (ADR-036 OP-120, in behandeling). "Onweerlegbaar" vraagt een externe, onafhankelijk beheerde bestemming, en die is er niet.

Tot 2026-08-10 was ook "periodieke integriteitscontroles" onjuist: de actor bestond, maar niets plande hem in (OP-109). Dat is nu wel zo.

> **Gecorrigeerd 2026-08-11 (ADR-036 OP-118 t/m OP-121).** De volledige afweging, met wat de keten wel en niet detecteert, staat in ADR-019 onder "Wat tamper-evident hier WEL en NIET betekent". Correcties zijn doorgehaald in plaats van verwijderd, zodat zichtbaar blijft dat een claim is bijgesteld.
