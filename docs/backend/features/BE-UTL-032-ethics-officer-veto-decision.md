# BE-UTL-032 -- EthicsOfficer can_veto MVP Beslissing (SP-WE-05)

**ID:** BE-UTL-032
**Sprint:** SP-WE-05
**Datum:** 2026-06-01
**ADR:** ADR-027 §5.2.5 v1.6

---

## Samenvatting

`EthicsOfficer.can_veto=False` is bevestigd als expliciete MVP-beslissing (WE-007).
Geen code-logica gewijzigd. Documentatie bijgewerkt: class docstring, ADR-027 Changelog
v1.6, CLAUDE.md valkuil.

## Rationale (Optie B gekozen)

Lexicon-based ethics checks hebben hoog false-positive risico voor zakelijke content
(bijv. "risk" of "dominant" in contractteksten). Het blokkeren op basis hiervan zou
onacceptabel veel false HITL-escalaties veroorzaken in MVP.

`ComplianceOfficer` en `SecurityOfficer` (beide `can_veto=True`) dekken de gevallen
waarbij echte blokkering noodzakelijk is.

Post-MVP roadmap: LLM-based ethics enforcement + `can_veto=True`.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/council/members/ethics_officer.py` | NOTE comment in docstring: MVP-beslissing + rationale + post-MVP roadmap |
| `docs/adr/027-copilot-agent-council.md` | Changelog v1.6 toegevoegd |
| `CLAUDE.md` | Valkuil toegevoegd: EthicsOfficer kan niet blokkeren |

## Trainingssamenvatting

### Flow 1: EthicsOfficer evalueert copilot-actie

- **Actor:** EthicsOfficer (council lid, systeem)
- **Voorwaarde:** Proposal ontvangen; lexicon geladen
- **Actie:** `_actual_deliberate(proposal, context)` aangeroepen; NL/EN/HI/SA lexicon check
- **Systeemreactie:** Bias/harm woorden gedetecteerd? Ja -> `APPROVE_WITH_MODIFICATION`; Nee -> `APPROVE`
- **Succesrespons:** Geen match -> `APPROVE` verdict; geen blokkering
- **Foutrespons:** Match gevonden -> `APPROVE_WITH_MODIFICATION` (niet `BLOCKED` -- `can_veto=False` MVP)
- **Uitzonderingen:** Exception in check -> `APPROVE` (fail-open, bewust MVP-keuze per ADR-027 §5.2.5 v1.6)

### Flow 2: Agent verwacht EthicsOfficer als blokkerende officer

- **Actor:** Developer of AI-agent die copilot council wiring debugt
- **Voorwaarde:** Agent raadpleegt CLAUDE.md valkuilen
- **Actie:** Agent zoekt naar "EthicsOfficer" in valkuilen
- **Systeemreactie:** CLAUDE.md waarschuwt dat `can_veto=False` bewust is
- **Succesrespons:** Agent gebruikt `ComplianceOfficer` of `SecurityOfficer` voor blokkering
- **Foutrespons:** Agent verwacht ten onrechte dat EthicsOfficer BLOCKED kan veroorzaken
- **Uitzonderingen:** Post-MVP: `can_veto=True` + LLM-based check gepland
