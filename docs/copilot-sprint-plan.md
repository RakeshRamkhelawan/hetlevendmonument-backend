# Co-Pilot + Agent Council — 8 Weken Sprintplan

**Versie:** 1.3 | 2026-05-25
**Doel:** Van huidige versnipperde Co-Pilot naar productie-hardened Agent Council met fase-1 proactieve patronen, conform EU AI Act (deadline: 2 augustus 2026).
**Eigenaar:** Rakesh (solo developer, AI-assisted)
**ADR:** [027-copilot-agent-council.md](adr/027-copilot-agent-council.md)
**Ontwerpdocument:** [copilot-architecture.md](copilot-architecture.md)

---

## Planning op één pagina

| Week | Thema | Hoofdoplevering | Status |
|------|-------|-----------------|--------|
| 1 | Council foundation | Coordinator + 5 Officer wrappers (bestaande modules) | ✅ |
| 2 | Nieuwe Officers + Audit | EthicsOfficer + ResourceOfficer + audit-extensie | ✅ |
| 3 | Council integratie + tests | E2E Council met TDD, alle Officers in productie-ready staat | ✅ |
| 4 | Co-Pilot consolidatie | Drie endpoints → één service, JSON contract | ✅ |
| 5 | Proactieve patronen fase 1 | 9 monitors (platform + compliance) | ✅ |
| 6 | Frontend integratie | UI compleet (AuditViewer, Settings, Signals) | ✅ |
| 7 | Audit-prep + AI Act gereed | Reports, hash robustness, runbooks | ✅ |
| 8 | Productie-hardening + rollout | Canary, observability, rollout 100% | ✅ |
| 9 | Enterprise Hardening | Sanity Officer, HI/SA Ethics, Dynamic Policies, Execution Hardening | ✅ |

**Productie-go-live target:** week 8 vrijdag (2026-07-17)
**EU AI Act deadline:** 2 augustus 2026 — **GEREED**

---

## Sprint 9 — Enterprise Hardening (week 9, 5 werkdagen)

**Doel:** Toekomstbestendig maken van de Council met dynamische policies, hallucinatie-detectie en enterprise-grade executie.

### Maandag — Sanity Officer & Hash Integrity Hardening

| # | Taak | Bestand | Tijd | Status |
|---|------|---------|------|--------|
| 9.1 | Maak `SanityOfficer` (wrapt `HallucinationGuard`) | `council/members/sanity_officer.py` | 3u | ✅ |
| 9.2 | Integratie in `Coordinator` aggregatie flow | `council/coordinator.py` | 1u | ✅ |
| 9.3 | Hashing Beveiliging: Inclusie van params & reasoning | `council/audit_writer.py` | 2u | ✅ |

### Dinsdag — Cross-lingual Ethics (Hindi & Sanskrit)

| # | Taak | Bestand | Tijd | Status |
|---|------|---------|------|--------|
| 9.4 | Breid `EthicsOfficer` lexicons uit met Hindi (HI) en Sanskriet (SA) | `council/members/lexicons/` | 2u | ✅ |
| 9.5 | Implementeer cross-lingual bias check in `EthicsOfficer` | `council/members/ethics_officer.py` | 3u | ✅ |
| 9.6 | Integratietests met meertalige prompts (HI/SA) | `tests/.../test_multilingual_ethics.py` | 2u | ✅ |

### Woensdag — Dynamic Council Policies

| # | Taak | Bestand | Tijd | Status |
|---|------|---------|------|--------|
| 9.7 | Maak Council-aggregatie regels configureerbaar per tenant (YAML) | `council/policies/` | 3u | ✅ |
| 9.8 | Refactor `AgentCouncil.deliberate()` om tenant policies in te laden | `council/coordinator.py` | 3u | ✅ |
| 9.9 | Validatie-tests voor aangepaste aggregatie-regels | `tests/.../test_tenant_policies.py` | 2u | ✅ |

### Donderdag — Execution Guarding & Forensic Loops

| # | Taak | Bestand | Tijd | Status |
|---|------|---------|------|--------|
| 9.10 | Implementeer Idempotency Lock per `decision_id` (Redis) | `copilot/service.py` | 2u | ✅ |
| 9.11 | Scoped Tool Execution (injectie van `user_id` context) | `tool_broker/service.py` | 2u | ✅ |
| 9.12 | Async Promotion voor long-running tasks (>5s) | `copilot/service.py` | 3u | ✅ |
| 9.13 | Result-Hash Binding: koppel tool-output aan hash chain | `council/audit_writer.py` | 3u | ✅ |

### Vrijdag — Disaster Recovery CLI & Final Audit

| # | Taak | Bestand | Tijd | Status |
|---|------|---------|------|--------|
| 9.14 | Ontwikkel `copilot-admin` CLI tool voor forensics | `tools/copilot_admin.py` | 3u | ✅ |
| 9.15 | Implementeer `re-seal` functionaliteit voor herstel | `tools/copilot_admin.py` | 3u | ✅ |
| 9.16 | Finale AI Act compliance sign-off documentatie | docs/sprints/ | 2u | ✅ |

---

*Sprint 9 voltooid op 2026-05-25.*
