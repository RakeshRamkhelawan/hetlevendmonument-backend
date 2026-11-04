# SanskritiSetu UI/UX Design Document: Company Orchestration Platform

**Versie:** 1.1
**Datum:** 11 maart 2026
**Status:** Design Foundation voor Paperclip AI Integratie
**Prioriteit:** P0 — Strategic Platform Evolution
**Gerelateerd:** [ARCHITECTURE_PAPERCLIP_INTEGRATION.md](./ARCHITECTURE_PAPERCLIP_INTEGRATION.md)

> **Changelog v1.1:** Toegevoegd — §4.6 Goal Tree Multi-View, §15 Real-time Collaboration (Yjs/CRDT), §16 ReactFlow Performance Guide; verbeterd — §4.2 minimap/search, §4.3 multi-view/search, §4.4 delegate/escalate/bulk, §4.5 SLA-indicator, §5.2 AI-personalisatie + auto-save, §7.2 CRDT-conflict UI, §9.2 `?` help panel, §12.1 "No Departments" empty state, §14.1 virtualisatie.

---

## Inhoudsopgave

1. [Design Visie & Principes](#1-design-visie--principes)
2. [User Personas](#2-user-personas)
3. [User Flows](#3-user-flows)
4. [Pagina-specificaties](#4-pagina-specificaties)
5. [Component Library](#5-component-library)
6. [Design System Integratie](#6-design-system-integratie)
7. [Interactie Patronen](#7-interactie-patronen)
8. [Responsive Design](#8-responsive-design)
9. [Toegankelijkheid (A11y)](#9-toegankelijkheid-a11y)
10. [Micro-interacties & Animaties](#10-micro-interacties--animaties)
11. [Error Handling & Feedback](#11-error-handling--feedback)
12. [Empty States & Onboarding](#12-empty-states--onboarding)
13. [Dark Mode](#13-dark-mode)
14. [Performance & Perceived Performance](#14-performance--perceived-performance)
15. [Real-time Collaboration Architecture](#15-real-time-collaboration-architecture)
16. [ReactFlow & Rendering Performance Guide](#16-reactflow--rendering-performance-guide)

---

## 1. Design Visie & Principes

### 1.1 Core Design Visie

> **"Van technisch complex naar menselijk simpel"**

De Paperclip integratie transformeert SanskritiSetu van een "agent orchestration tool" naar een "virtual company platform". Het UI/UX design moet deze transformatie weerspiegelen:

- **Voorheen**: Technische configuratie (packs, agents, procedures)
- **Na**: Bedrijfsmodellering (departments, goals, board governance)

### 1.2 Design Principes

| Principe | Beschrijving | Toepassing |
|----------|--------------|------------|
| **Context First** | Elke taak toont het bedrijfsdoel ("het waarom") | Goal ancestry breadcrumb bovenaan elke pagina |
| **Progressive Disclosure** | Complexiteit in lagen tonen | Org chart: eerst 1 niveau, dan expand |
| **Actionable Clarity** | Elke actie heeft duidelijke context | Pack activatie toont altijd "waarom" (confidence score) |
| **Human Metaphor** | Governance in bedrijfstaal, niet technisch | "Board approval" vs "PolicyEngine validation" |
| **Graceful Degradation** | Werkt ook zonder Company Layer | Degraded mode indicator, niet blokkerend |

### 1.3 Design Doelen (KPIs)

| Metric | Huidig | Doel | Meetmethode |
|--------|--------|------|-------------|
| Onboarding time (template → operational) | 45 min | < 5 min | Time-on-task testing |
| Task completion rate (goal assignment) | - | > 90% | Funnel analysis |
| Feature adoption (Company Layer) | 0% | 40% | Analytics |
| User error rate (pack activation) | - | < 5% | Error tracking |
| Time to approve (board decisions) | - | < 2 min | Workflow analytics |

---

## 2. User Personas

### 2.1 Persona: ZZP Freelancer ("Solo-preneur")

**Demografie:** Zelfstandige, 25-40 jaar, technisch vaardig maar geen enterprise IT ervaring

**Doelen:**
- Snel operationeel zijn zonder complexe setup
- Eigen AI-assistent hebben die "gewoon werkt"
- Minimale configuratie, maximale waarde

**Pijnpunten:**
- Te veel opties, keuzestress
- Technische taal ("procedures", "packs")
- Tijdgebrek voor uitgebreide configuratie

**UI/UX Implicaties:**
- Snelle 3-staps onboarding
- "ZZP Freelancer" template als default
- Minimalistische interface (geen org chart nodig)
- Grote, duidelijke CTA's

### 2.2 Persona: MKB Ondernemer ("Growth Focus")

**Demografie:** Eigenaar van groeiend bedrijf (5-50 medewerkers), 35-55 jaar, business focus

**Doelen:**
- Bedrijfstructuur modelleren
- Afdelingen efficiënt inrichten
- Groei sturen met AI-ondersteuning

**Pijnpunten:**
- Overzicht verliezen bij groei
- Compliance en governance lastig
- Tijd tekort voor micromanagement

**UI/UX Implicaties:**
- Visuele org chart builder
- Board governance in begrijpelijke taal
- Template marketplace met MKB-focus
- ROI dashboards per afdeling

### 2.3 Persona: Enterprise Admin ("Governance Guardian")

**Demografie:** IT/Compliance manager, 30-50 jaar, risk-averse, detail-oriented

**Doelen:**
- Strict governance en compliance
- Audit trails en goedkeuringen
- Enterprise-grade security

**Pijnpunten:**
- Shadow IT door losse tools
- Oncontroleerbare AI-acties
- Compliance rapportage

**UI/UX Implicaties:**
- Gedetailleerde audit views
- Board approval queues
- Policy configuratie
- Export/audit logs

### 2.4 Persona: Developer ("Integrator")

**Demografie:** Software engineer, 25-45 jaar, wil eigen agents bouwen

**Doelen:**
- Eigen agents integreren via heartbeat
- API gebruiken voor automatisering
- Flexibele configuratie

**Pijnpunten:**
- Gesloten ecosystemen
- Beperkte integratie opties
- Slechte documentatie

**UI/UX Implicaties:**
- External Agent Hub met code voorbeelden
- API explorer
- Webhook configuratie UI
- SDK documentatie

---

## 3. User Flows

### 3.1 Flow 1: First-Time Onboarding (3-Step Wizard)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: "Wat voor bedrijf heb je?"                                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │   [👤 ZZP/Freelancer]    [🏢 MKB]    [🏭 Enterprise]               │   │
│  │                                                                     │   │
│  │   ─────────────────────────────────────────────────────────────     │   │
│  │                                                                     │   │
│  │   Sector: [🔽 Selecteer...]                                         │   │
│  │                                                                     │   │
│  │   Of: "Beschrijf je bedrijf in 1 zin"                              │   │
│  │   [________________________________] [🤖 AI Match]                │   │
│  │                                                                     │   │
│  │                                           [Volgende →]              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  AI Matching: "Je beschrijving lijkt op 'Tech Startup' template"           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: "Klopt dit organigram?"                                             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │              ┌─────────────┐                                       │   │
│  │              │   CEO/Jij   │                                       │   │
│  │              └──────┬──────┘                                       │   │
│  │         ┌──────────┼──────────┐                                   │   │
│  │    ┌────▼────┐ ┌───▼───┐ ┌───▼───┐                              │   │
│  │    │  Sales  │ │Finance│ │Operations│  [+ Afdeling toevoegen]   │   │
│  │    └────┬────┘ └───┬───┘ └───┬───┘                              │   │
│  │         │          │         │                                   │   │
│  │    🔧 Configureer  🔧 Configureer  🔧 Configureer                │   │
│  │                                                                     │   │
│  │   Packs preview:                                                    │   │
│  │   ┌────────────────────────────────────────────────────────────┐   │   │
│  │   │ 🤖 Auto-geactiveerd: mkb.sales_pack (85% match)           │   │   │
│  │   │ 💡 Suggestie: mkb.crm_integration (65% match)             │   │   │
│  │   └────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │                                           [Volgende →]              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: "Definieer je belangrijkste doel"                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │   🎯 Company Mission                                                │   │
│  │   [Word de meest duurzame retailer in Nederland]                    │   │
│  │                                                                     │   │
│  │   ─────────────────────────────────────────────────────────────     │   │
│  │                                                                     │   │
│  │   Strategic Goals:                                                  │   │
│  │   ┌────────────────────────────────────────────────────────────┐   │   │
│  │   │ ☐ Online omzet verdubbelen binnen 12 maanden              │   │   │
│  │   │ ☐ Operationele kosten verlagen met 15%                    │   │   │
│  │   │ ☐ Klanttevredenheid naar 95%                              │   │   │
│  │   └────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │   AI suggesties:                                                    │   │
│  │   "Op basis van je sector (retail) zijn dit gebruikelijke goals:"  │   │
│  │   [+ Snel toevoegen: "Voorraad optimalisatie"]                      │   │
│  │                                                                     │   │
│  │                                           [✅ Company Aanmaken]     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  🎉 Resultaat: Company aangemaakt met auto-geactiveerde packs              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Flow 2: Goal-Centered Task Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MISSION CONTROL MET GOAL CONTEXT                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  🎯 Goal Ancestry Breadcrumb (sticky bovenaan)                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Mission: Duurzame marktleider  →  Strategic: Omzet ×2  →  Project: │   │
│  │ Webshop optimalisatie  →  Task: Analyseer conversie funnel         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │                             │  │                                     │  │
│  │  🤖 Agent Execution         │  │  📊 Context Panel                   │  │
│  │                             │  │                                     │  │
│  │  ┌───────────────────────┐  │  │  Doel alignment: 87% ✅            │  │
│  │  │ Analyzing funnel...   │  │  │  ━━━━━━━━━━━━━━━━━━━━━━━━         │  │
│  │  │                       │  │  │                                     │  │
│  │  │ [████████████░░░░░░░░]│  │  │  Related goals:                    │  │
│  │  │ Step 3 of 5           │  │  │  • Verbeter checkout (sibling)     │  │
│  │  └───────────────────────┘  │  │  • Reduceer cart abandonment       │  │
│  │                             │  │                                     │  │
│  │  [⏹ Stop] [⏸ Pause]        │  │  Pack: mkb.digital_storefront      │  │
│  │                             │  │  Department: Sales                  │  │
│  └─────────────────────────────┘  └─────────────────────────────────────┘  │
│                                                                             │
│  💡 "Deze taak draagt bij aan: 'Omzet verdubbelen' (Strategic Goal)"       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Flow 3: Board Approval Queue

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ BOARD APPROVAL QUEUE                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Inbox: 3 pending    [Filter: 🔽]    [Sort: 🔽]                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ⚠️  URGENT    Budget overschrijding vereist goedkeuring             │   │
│  │                                                                     │   │
│  │     🏢 Company: TechStart BV                                        │   │
│  │     🎯 Goal: Omzet verdubbelen                                      │   │
│  │     💰 Impact: +€500/maand (budget: €1000, huidig: €800)            │   │
│  │     🤖 Agent: Marketing Automation                                  │   │
│  │                                                                     │   │
│  │     Context: "Auto-scaling triggered vanwege Black Friday campagne" │   │
│  │                                                                     │   │
│  │     [✅ Goedkeuren]  [❌ Afwijzen]  [📄 Details]                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🆕  NEW       Externe agent registratie wacht op goedkeuring        │   │
│  │                                                                     │   │
│  │     🤖 Agent: data-analyzer-prod                                    │   │
│  │     🔧 Runtime: Python                                              │   │
│  │     📋 Capabilities: data_analysis, report_generation               │   │
│  │                                                                     │   │
│  │     [✅ Goedkeuren]  [❌ Afwijzen]                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [↻ Refresh]  [📊 Historie]                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Flow 4: External Agent Registration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL AGENT HUB                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [+ Nieuwe Agent Registreren]                                               │
│                                                                             │
│  Jouw Agents:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │  🟢 data-analyzer-prod                                              │   │
│  │     Status: Online (last heartbeat: 2s ago)                        │   │
│  │     Tasks completed: 42    Avg duration: 12.5s                     │   │
│  │     [📊 Stats] [⚙️ Config] [🗑️ Verwijderen]                        │   │
│  │                                                                     │   │
│  │  🟡 webhook-processor                                               │   │
│  │     Status: Idle (last heartbeat: 45s ago)                         │   │
│  │     [📊 Stats] [⚙️ Config] [🔄 Restart]                            │   │
│  │                                                                     │   │
│  │  🔴 legacy-script                                                   │   │
│  │     Status: Offline (3 heartbeats missed)                          │   │
│  │     [📊 Stats] [🔍 Diagnose] [🗑️ Verwijderen]                      │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Quick Start: Python SDK                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ```python                                                           │   │
│  │ from sanskritisetu import ExternalAgent                             │   │
│  │                                                                     │   │
│  │ agent = ExternalAgent.register(                                     │   │
│  │     name="my-analyzer",                                             │   │
│  │     capabilities=["analyze", "report"],                             │   │
│  │     api_key="sk-..."  # Van registratie formulier                   │   │
│  │ )                                                                   │   │
│  │                                                                     │   │
│  │ @agent.task_handler                                                  │   │
│  │ def handle_task(task):                                               │   │
│  │     return {"result": analyze(task.input)}                          │   │
│  │                                                                     │   │
│  │ agent.start_heartbeat()                                             │   │
│  │ ```                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [📚 Volledige Documentatie]  [💻 Code Voorbeelden]                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Pagina-specificaties

### 4.1 Company Dashboard (`/company`)

**Doel:** Centraal overzicht van het virtuele bedrijf

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Header (sticky)                                                             │
│ [Logo]  Company: TechStart BV  [🔽 Switch]    [🔔] [👤 Profiel]            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ 🎯 Mission Statement                                                    ││
│ │ "Word de meest duurzame retailer in Nederland"                         ││
│ │ [Bewerken]                                                              ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│ ┌──────────────────────────────┐  ┌───────────────────────────────────────┐│
│ │ 📊 Company Health            │  │ 🎯 Active Goals                       ││
│ │                              │  │                                       ││
│ │  ┌─────────┐ ┌─────────┐    │  │  🟢 Omzet verdubbelen      [75%]     ││
│ │  │ Agents  │ │ Packs   │    │  │  🟡 Kosten verlagen        [45%]     ││
│ │  │   12    │ │   8     │    │  │  🔴 Klanttevredenheid      [30%]     ││
│ │  └─────────┘ └─────────┘    │  │                                       ││
│ │                              │  │  [+ Nieuw Goal]                       ││
│ │  ┌─────────┐ ┌─────────┐    │  │                                       ││
│ │  │ Tasks   │ │ Board   │    │  └───────────────────────────────────────┘│
│ │  │  145    │ │  3 ⏳   │    │                                         │
│ │  └─────────┘ └─────────┘    │                                         │
│ │                              │                                         │
│ └──────────────────────────────┘                                         │
│                                                                           │
│ ┌───────────────────────────────────────────────────────────────────────┐│
│ │ 🏢 Organisatie                                                        ││
│ │                                                                       ││
│ │   [Org Chart Preview - 2 niveaus]                                    ││
│ │                                                                       ││
│ │        ┌───────────┐                                                 ││
│ │        │    CEO    │                                                 ││
│ │        └─────┬─────┘                                                 ││
│ │    ┌─────────┼─────────┐                                             ││
│ │ ┌──▼──┐  ┌───▼───┐ ┌──▼──┐                                           ││
│ │ │Sales│  │Finance│ │ Ops │                                           ││
│ │ └──┬──┘  └───┬───┘ └──┬──┘                                           ││
│ │    │         │        │                                              ││
│ │ [3👤]      [2👤]    [4👤]   ← Team grootte                           ││
│ │                                                                       ││
│ │   [🔍 Uitgebreide Org Chart]                                          ││
│ └───────────────────────────────────────────────────────────────────────┘│
│                                                                           │
│ ┌───────────────────────────────────────────────────────────────────────┐│
│ │ 📦 Active Domain Packs                                                ││
│ │                                                                       ││
│ │ ┌─────────────────────────────────────────────────────────────────┐  ││
│ │ │ mkb.digital_storefront    🟢 Actief    Confidence: 85%         │  ││
│ │ │ mkb.customer_pulse        🟢 Actief    Confidence: 75%         │  ││
│ │ │ sales.lead_enrichment     💡 Suggestie Confidence: 60%         │  ││
│ │ └─────────────────────────────────────────────────────────────────┘  ││
│ │                                                                       ││
│ │   [🔧 Beheren]  [+ Pack Toevoegen]                                    ││
│ └───────────────────────────────────────────────────────────────────────┘│
│                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Componenten:**
- **Mission Card**: Bewerkbare missie statement met karakter limiet (2000)
- **Health Widgets**: 4 KPI cards (Agents, Packs, Tasks, Board)
- **Goals List**: Progress bars met kleurcodering (groen >70%, geel 30-70%, rood <30%)
- **Org Chart Preview**: 2 niveaus diep, click naar volledige builder
- **Pack List**: Auto-geactiveerd vs suggesties, confidence badges

### 4.2 Org Chart Builder (`/company/org-chart`)

**Doel:** Visuele organisatiestructuur beheren

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [← Terug]  Org Chart Builder                                    [💾 Opslaan]│
├─────────────────────────────────────────────────────────────────────────────┤
│ Toolbar:                                                                    │
│ [👤+ Dept] [🔧 Edit] [🗑️ Delete] [🔗 Connect] [🔍 Zoom: 100%] [🖐 Pan]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │                    ReactFlow Canvas Area                           │   │
│  │                                                                     │   │
│  │         ┌─────────────────┐                                       │   │
│  │         │   ┌─────────┐   │                                       │   │
│  │         │   │   CEO   │   │  ← Click to edit                     │   │
│  │         │   │  (Jij)  │   │                                       │   │
│  │         │   └────┬────┘   │                                       │   │
│  │         └────────┼────────┘                                       │   │
│  │                  │                                                │   │
│  │      ┌───────────┼───────────┐                                   │   │
│  │   ┌──▼──┐     ┌──▼──┐     ┌──▼──┐                                │   │
│  │   │Sales│     │Finance│   │ Ops │  ← Right-click for menu        │   │
│  │   │[3👤]│     │ [2👤] │   │[4👤]│                                │   │
│  │   └──┬──┘     └──┬───┘   └──┬──┘                                │   │
│  │      │           │          │                                   │   │
│  │   [+Add]      [+Add]    [+Add]  ← Quick add sub-department      │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Department Details (Sidebar - verschijnt bij selectie)              │   │
│  │                                                                     │   │
│  │  Naam: [Sales                      ]                               │   │
│  │                                                                     │   │
│  │  Head: [🔽 Jan van Dijk]                                          │   │
│  │                                                                     │   │
│  │  Board Role: [🔽 CEO]                                             │   │
│  │                                                                     │   │
│  │  Budget: [100000] tokens/maand                                    │   │
│  │                                                                     │   │
│  │  Actieve Packs:                                                     │   │
│  │  [🟢 mkb.sales_pack] [🟢 mkb.crm_pack] [❌]                        │   │
│  │                                                                     │   │
│  │  [+ Pack Toevoegen]                                                 │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Interacties:**

- **Drag & Drop**: Nodes verplaatsen (ghost preview + snap-to-grid)
- **Zoom**: Ctrl+Scroll of pinch gesture
- **Node Click**: Open details sidebar
- **Node Right-click**: Context menu (add child, delete, edit)
- **Connect Mode**: Drag van handle naar andere node
- **Auto-layout**: [Magic Wand] button voor automatische layout via **Dagre** (aanbevolen layout-algoritme voor tree-hiërarchieën; ondersteunt horizontal/vertical richting en berekent node-posities automatisch)
- **Search**: `[🔍 Zoek department...]` filtert nodes + highlights matching pad
- **Minimap**: ReactFlow minimap (rechtsonder) voor navigatie bij >30 nodes
- **Collaboration cursors**: Andere actieve gebruikers zichtbaar als gekleurde cursor-avatar (zie §15)

> **Performance:** Wrap alle custom node- en edge-componenten in `React.memo()`. Gebruik `useCallback` voor alle props-functies. Zie §16 voor volledige ReactFlow optimalisatie-gids.

### 4.3 Goal Tree (`/company/goals`)

**Doel:** Hiërarchische doelen visualiseren en beheren

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [← Terug]  Goal Tree                                            [+ Nieuw]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  View: [🔘 Tree] [⚪ List]  Filter: [🔽 Alle]  Sort: [🔽 Progress ▼]        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │  🎯 Mission: Duurzame marktleider                                   │   │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │   │
│  │  Progress: 45%                               [⚙️ Edit] [📊 Details] │   │
│  │                                                                     │   │
│  │  ├── 🎯 Strategic: Omzet verdubbelen                                │   │
│  │  │   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━               │   │
│  │  │   Progress: 75% [████████████░░░░░░░░]  Deadline: 3 maanden      │   │
│  │  │                                                                     │   │
│  │  │   ├── 🎯 Project: Webshop optimalisatie                          │   │
│  │  │   │   Progress: 90% [████████████████░░]                         │   │
│  │  │   │   ├── ✅ Task: SEO audit                                     │   │
│  │  │   │   ├── 🔄 Task: Conversie optimalisatie  [Running]            │   │
│  │  │   │   └── ⏳ Task: A/B testing                                   │   │
│  │  │   │                                                             │   │
│  │  │   └── 🎯 Project: Marketing automatisering                      │   │
│  │  │       Progress: 60% [████████████░░░░░░░░]                      │   │
│  │  │       └── 🔄 Task: Email flows setup  [Pending approval]        │   │
│  │  │                                                                 │   │
│  │  └── 🎯 Strategic: Kosten verlagen                                  │   │
│  │      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━               │   │
│  │      Progress: 30% [██████░░░░░░░░░░░░░░░░]                        │   │
│  │      └── 🎯 Project: Supply chain optimalisatie                    │   │
│  │          └── ⏳ Task: Leveranciers audit                           │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Legend: ✅ Completed  🔄 In Progress  ⏳ Not Started  ⚠️ Blocked           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Componenten:**

- **Multi-view Toggle**: Schakel tussen Tree / Platte Lijst / Timeline (zie §4.6)
- **Search Bar**: Filter goals op naam, eigenaar of status (debounce 300ms)
- **Tree View**: Uitklapbare hiërarchie met lazy-load per niveau
- **Progress Bars**: Visuele voortgang per niveau
- **Confidence Badges**: Geschatte haalbaarheidspercentage per goal (🟢 ≥70% / 🟡 40-70% / 🔴 <40%)
- **Status Icons**: Snelle status herkenning
- **Inline Actions**: Edit/details per goal
- **Drag & Drop**: Goals herstructureren (parent wijzigen)

> **Virtualisatie:** Bij >200 goals `react-virtual` (TanStack Virtual) gebruiken — alleen zichtbare rijen renderen. Lazy-load child goals on expand.

### 4.4 Board Approval Queue (`/board`)

**Doel:** Governance beslissingen reviewen en goedkeuren

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [← Terug]  Board Approval Queue                                 [📊 Stats]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Filters: [🔽 Alle Types] [🔽 Alle Risico's] [🔽 Alle Departments]          │
│                                                                             │
│  Tabs: [⏳ Pending (3)] [🔄 Changes Requested (1)] [✅ Approved] [❌ Rejected] [🕐 All]                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ⚠️  HIGH PRIORITY                                                   │   │
│  │                                                                     │   │
│  │  🏢 Company: TechStart BV                                           │   │
│  │  🎯 Goal: Omzet verdubbelen  →  Project: Marketing automatisering  │   │
│  │  💰 Budget Impact: +€500/maand (limiet: €1000, huidig: €800)        │   │
│  │  ⚡ Risk Level: MEDIUM                                              │   │
│  │                                                                     │   │
│  │  ┌───────────────────────────────────────────────────────────────┐ │   │
│  │  │ Action Required: Marketing automation pack upgrade            │ │   │
│  │  │                                                               │ │   │
│  │  │ Trigger: Auto-scaling activated due to campaign "Black Friday"│ │   │
│  │  │                                                               │ │   │
│  │  │ Requested by: sales_automation_agent                          │ │   │
│  │  │ Requested at: 14:32, 11 maart 2026                            │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  │                                                                     │   │
│  │  [✅ Goedkeuren]  [❌ Afwijzen]  [🔄 Aanpassing]  [📄 Details]      │   │
│  │                                                                     │   │
│  │  Quick Approve: ["Goedkeuren voor deze campagne" ▼]               │   │
│  │  [👤 Delegeren aan... ▼]  [⬆️ Escaleren naar Board ▼]             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🆕  NEW                                                             │   │
│  │                                                                     │   │
│  │  🤖 External Agent Registration: data-analyzer-prod                 │   │
│  │  🔧 Runtime: Python 3.11                                            │   │
│  │  📋 Capabilities: data_analysis, report_generation, ml_prediction   │   │
│  │  🔗 Webhook: https://api.example.com/agent-webhook                  │   │
│  │                                                                     │   │
│  │  ⚠️  Security Check: Webhook domain verified                        │   │
│  │                                                                     │   │
│  │  [✅ Goedkeuren]  [❌ Afwijzen]  [📄 Security Report]               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ⏳  PENDING                                                         │   │
│  │                                                                     │   │
│  │  🎯 Goal Creation: "Internationale expansie Duitsland"              │   │
│  │  📊 Estimated Impact: +€50k omzet, +15% kosten                      │   │
│  │  ⏰ Deadline: Review binnen 24u (SLA)                               │   │
│  │                                                                     │   │
│  │  [✅ Goedkeuren]  [❌ Afwijzen]  [📝 Opmerking toevoegen]           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Interacties:**

- **Swipe (mobile)**: Links = approve, Rechts = reject
- **Bulk Actions**: Meerdere items selecteren (checkbox bovenaan) + "Alles goedkeuren <€500" shortcut
- **Quick Approve**: Vooraf gedefinieerde redenen
- **Details Panel**: Uitgebreide context tonen (audit trail, bijlagen, voorgaande beslissingen als precedent)
- **Delegeren**: Doorsturen naar collega met optionele toelichting
- **Escaleren**: Verhogen naar hogere autoriteit in Board hiërarchie
- **Aanpassing vragen**: Terugsturen naar aanvrager met specifieke feedback; kaart verschijnt in tab "🔄 Changes Requested"
- **SLA timer**: Deadline countdown badge wordt rood bij <2 uur resterend; automatische escalatie na overschrijding (zie Architecture §8.3)

### 4.5 External Agent Hub (`/agents/external`)

**Doel:** Externe agents registreren, monitoren en beheren

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [← Terug]  External Agent Hub                                   [+ Nieuwe]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🟢 ONLINE (2)                                                       │   │
│  │                                                                     │   │
│  │  ┌───────────────────────────────────────────────────────────────┐ │   │
│  │  │ 🤖 data-analyzer-prod                                         │ │   │
│  │  │                                                               │ │   │
│  │  │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │ │   │
│  │  │ │   🟢 Live   │  │   42 Tasks  │  │  12.5s Avg  │            │ │   │
│  │  │ │   2s ago    │  │   completed │  │   duration  │            │ │   │
│  │  │ └─────────────┘  └─────────────┘  └─────────────┘            │ │   │
│  │  │                                                               │ │   │
│  │  │ Status: Idle (waiting for tasks)                              │ │   │
│  │  │ Department: Sales    Runtime: Python 3.11                     │ │   │
│  │  │                                                               │ │   │
│  │  │ Capabilities: data_analysis, report_generation, visualization │ │   │
│  │  │                                                               │ │   │
│  │  │ SLA: [████████░░] 80%  ← 🟡 warning zone (>80% = alert)     │ │   │
│  │  │                                                               │ │   │
│  │  │ [📊 Stats] [⚙️ Config] [🔍 Logs] [🗑️ Verwijderen]            │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  │                                                                     │   │
│  │  ┌───────────────────────────────────────────────────────────────┐ │   │
│  │  │ 🔵 webhook-processor                                          │ │   │
│  │  │                                                               │ │   │
│  │  │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │ │   │
│  │  │ │   🟡 Idle   │  │   128 Tasks │  │   0.3s Avg  │            │ │   │
│  │  │ │   45s ago   │  │   completed │  │   duration  │            │ │   │
│  │  │ └─────────────┘  └─────────────┘  └─────────────┘            │ │   │
│  │  │                                                               │ │   │
│  │  │ Status: Processing webhook batch...                           │ │   │
│  │  │ Runtime: Node.js 18                                           │ │   │
│  │  │                                                               │ │   │
│  │  │ [📊 Stats] [⚙️ Config] [🔍 Logs] [🔄 Restart]                 │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🔴 OFFLINE (1)                                                      │   │
│  │                                                                     │   │
│  │  ┌───────────────────────────────────────────────────────────────┐ │   │
│  │  │ 🔴 legacy-script                                              │ │   │
│  │  │                                                               │ │   │
│  │  │ ⚠️  Last heartbeat: 5 min ago (3 heartbeats missed)          │ │   │
│  │  │                                                               │ │   │
│  │  │ Possible causes:                                              │ │   │
│  │  │ • Script crashed                                              │ │   │
│  │  │ • Network connectivity issues                                 │ │   │
│  │  │ • API key expired                                             │ │   │
│  │  │                                                               │ │   │
│  │  │ [🔍 Diagnose] [🔄 Herstarten] [🗑️ Verwijderen]               │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Quick Start SDK:                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  [🔘 Python]  [⚪ Node.js]  [⚪ Shell]  [⚪ Webhook]                 │   │
│  │                                                                     │   │
│  │  ```python                                                          │   │
│  │  from sanskritisetu import ExternalAgent                            │   │
│  │                                                                     │   │
│  │  agent = ExternalAgent.register(                                    │   │
│  │      name="my-agent",                                               │   │
│  │      api_key="sk-...",  # From registration                       │   │
│  │      capabilities=["analyze", "report"]                             │   │
│  │  )                                                                  │   │
│  │  agent.start_heartbeat()                                            │   │
│  │  ```                                                                │   │
│  │                                                                     │   │
│  │  [📋 Kopiëren]  [📚 Documentatie]                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.6 Goal Tree Multi-View (`/company/goals?view=...`)

**Doel:** Flexibele weergave van goals voor verschillende use-cases (hiërarchie, planning, status-overzicht)

**View Toggle (toolbar):**
```
[🌳 Tree] [📋 Lijst] [📅 Timeline] [📊 Kanban]
```

**Tree View** (standaard — zie §4.3)

**Platte Lijst View:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [🌳 Tree] [📋 Lijst] [📅 Timeline] [📊 Kanban]   [🔍 Zoeken...]  [🔽 Filter] │
├──────────────────┬────────────┬──────────┬───────────┬───────────────────────┤
│ Goal             │ Niveau     │ Progress │ Status    │ Deadline              │
├──────────────────┼────────────┼──────────┼───────────┼───────────────────────┤
│ Duurzame         │ 🎯 Mission │ 60%      │ 🔄 Active │ Dec 2026              │
│ marktleider...   │            │          │           │                       │
├──────────────────┼────────────┼──────────┼───────────┼───────────────────────┤
│ Omzet ×2         │ 📊 Strategic│ 75%     │ 🔄 Active │ Jun 2026              │
├──────────────────┼────────────┼──────────┼───────────┼───────────────────────┤
│ Webshop optim.   │ 📁 Project │ 45%      │ ⚠️ At Risk│ Apr 2026              │
└──────────────────┴────────────┴──────────┴───────────┴───────────────────────┘
```

**Timeline View:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Jan] [Feb] [Mrt] [Apr] [Mei] [Jun] [Jul] [Aug] [Sep] [Okt] [Nov] [Dec]     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🎯 Duurzame marktleider   ████████████████████████████████████████████████  │
│ 📊 Omzet ×2               ██████████████████████████                        │
│ 📁 Webshop optimalisatie  ██████████████                                    │
│ ✅ Leveranciers audit      █████                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Kanban View:**
```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ ⏳ Not Started│ 🔄 In Progress│ ⚠️ At Risk   │ ✅ Completed │
│    (2)       │    (4)       │    (1)       │    (3)       │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │
│ │Expansie  │ │ │Omzet ×2  │ │ │Webshop   │ │ │Audit Q1  │ │
│ │Duitsland │ │ │75% ▓▓▓▓▓ │ │ │45% ▓▓▓   │ │ │100% ████ │ │
│ └──────────┘ │ └──────────┘ │ └──────────┘ │ └──────────┘ │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**Componenten:**

- **GoalTreeViewToggle**: Segment control (Tree / Lijst / Timeline / Kanban); slaat voorkeur op in `localStorage`
- **GoalSearchBar**: Debounced (300ms) text filter; highlight matching goals in tree; clear button
- **GoalFilterPanel**: Filter op status, niveau, eigenaar, deadline-range; badge toont actieve filters
- **GoalListTable**: Sorteerbare kolommen (klik header); sticky first column; klik rij = detail drawer
- **GoalGanttBar**: Horizontale balk op basis van `start_date` / `deadline`; kleurcode = status
- **GoalKanbanColumn**: Drag-and-drop tussen kolommen = status wijzigen (optimistic update)

---

## 5. Component Library

### 5.1 Company Layer Componenten

#### GoalAncestryBreadcrumb
```typescript
interface GoalAncestryBreadcrumbProps {
  mission: GoalNode;
  strategicGoal?: GoalNode;
  projectGoal?: GoalNode;
  currentTask?: TaskNode;
  onNavigate?: (goalId: string) => void;
  variant?: 'full' | 'compact' | 'minimal';
}
```

**States:**
- Full: Toont alle niveaus met titels
- Compact: Missie + huidig niveau
- Minimal: Alleen missie icoon

**Interactie:**
- Click op niveau = navigate naar goal detail
- Hover = tooltip met volledige titel
- Truncation bij lange titels (ellipsis)

#### OrgChartNode
```typescript
interface OrgChartNodeProps {
  department: Department;
  isSelected: boolean;
  isExpanded: boolean;
  hasChildren: boolean;
  packCount: number;
  agentCount: number;
  budgetStatus: 'healthy' | 'warning' | 'critical';
  onClick: () => void;
  onExpand: () => void;
  onAddChild: () => void;
}
```

**Visual States:**
```
┌─────────────────────────┐
│ ┌─────┐ Department Name │
│ │ 👤  │ ─────────────── │
│ └─────┘ Head: Jan van D │
│                         │
│ ┌─────┐ ┌─────┐ ┌─────┐ │
│ │ 📦 8│ │ 🤖 5│ │ 💰 🟢│ │
│ └─────┘ └─────┘ └─────┘ │
│                         │
│ [+] Add Sub             │
└─────────────────────────┘

Selected: Blue border (2px), shadow-lg
Hover: Light blue background, cursor pointer
Budget Warning: Yellow budget icon
Budget Critical: Red budget icon + pulse animation
```

#### GoalCard
```typescript
interface GoalCardProps {
  goal: Goal;
  progress: number;
  status: 'not_started' | 'in_progress' | 'completed' | 'blocked';
  deadline?: Date;
  childCount?: number;
  isExpanded?: boolean;
  onToggle?: () => void;
  onEdit?: () => void;
}
```

**Visual:**
```
┌─────────────────────────────────────────┐
│ 🎯 Goal Title                    [▲▼] │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 75% [████████████████████░░░░░░░░░░░░] │
│                                         │
│ Status: 🔄 In Progress                  │
│ Deadline: 15 apr 2026 (23 dagen)       │
│                                         │
│ 3 sub-goals: [2 ✅] [1 🔄] [0 ⏳]       │
│                                         │
│ [⚙️ Edit] [📊 Details]                  │
└─────────────────────────────────────────┘
```

#### PackActivationCard
```typescript
interface PackActivationCardProps {
  pack: DomainPack;
  confidence: number;
  confidenceLabel: 'EXACT' | 'HIGH' | 'MEDIUM' | 'LOW';
  matchReasons: string[];
  isAutoActivated: boolean;
  isSuggested: boolean;
  isActive: boolean;
  onActivate: () => void;
  onDeactivate: () => void;
  onDismiss: () => void;
}
```

**Visual States:**

**Auto-Activated:**
```
┌─────────────────────────────────────────┐
│ 🟢 mkb.digital_storefront       [✅]   │
│    Auto-geactiveerd                     │
│                                         │
│ Confidence: 85% (HIGH)                  │
│                                         │
│ Match redenen:                          │
│ ✓ Department exact match: Sales         │
│ ✓ Pack prefix matches company type: mkb │
│ ✓ Sector tag overlap: retail            │
│                                         │
│ [ℹ️ Details]  [🚫 Deactiveren]          │
└─────────────────────────────────────────┘
```

**Suggested:**
```
┌─────────────────────────────────────────┐
│ 💡 sales.lead_enrichment              │
│    Suggestie                            │
│                                         │
│ Confidence: 60% (MEDIUM)                │
│                                         │
│ [✅ Activeren]  [🗑️ Negeren]           │
└─────────────────────────────────────────┘
```

#### BoardDecisionCard
```typescript
interface BoardDecisionCardProps {
  decision: BoardDecision;
  priority: 'urgent' | 'high' | 'normal' | 'low';
  onApprove: (reason?: string) => void;
  onReject: (reason: string) => void;
  onDefer: () => void;
}
```

**Visual:**
```
┌─────────────────────────────────────────┐
│ ⚠️  HIGH PRIORITY                2m ago │
│ ─────────────────────────────────────── │
│ Budget overschrijding vereist           │
│ goedkeuring                             │
│                                         │
│ 🏢 TechStart BV  |  🎯 Omzet ×2        │
│ 💰 +€500/maand   |  ⚡ Risk: MEDIUM    │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ Context: Auto-scaling triggered...  │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [✅ Goedkeuren]  [❌ Afwijzen]         │
│                                         │
│ Quick reason: [🔽 "Goedkeuren voor..."] │
└─────────────────────────────────────────┘
```

#### ExternalAgentCard
```typescript
interface ExternalAgentCardProps {
  agent: ExternalAgent;
  healthStatus: 'online' | 'idle' | 'error' | 'offline';
  lastHeartbeat: Date;
  metrics: {
    tasksCompleted: number;
    avgDuration: number;
    errorRate: number;
  };
  onViewLogs: () => void;
  onConfigure: () => void;
  onDelete: () => void;
}
```

**Health Indicators:**
- **Online (🟢)**: Heartbeat < 30s ago, groene pulse
- **Idle (🟡)**: Heartbeat 30-60s ago, gele glow
- **Error (🟠)**: Agent zelf rapporteert error, oranje border
- **Offline (🔴)**: Heartbeat > 60s ago, rode pulse + grijze overlay

### 5.2 Form Components

#### CompanySetupWizard (Multi-step)
```typescript
interface WizardStep {
  id: string;
  title: string;
  description: string;
  component: React.ComponentType<WizardStepProps>;
  isValid: () => boolean;
  canSkip?: boolean;
}

interface CompanySetupWizardProps {
  steps: WizardStep[];
  onComplete: (data: CompanySetupData) => void;
  onSkip?: () => void;
  templates: CompanyTemplate[];
}
```

**Navigation:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1 of 3                                          💾 Auto-saved 14:32   │
│ [●──────○──────○]                                                          │
│ Company Type    Org Chart    Goals                                          │
│                                                                             │
│ [← Vorige]              [Stap overslaan]  [Volgende →]  [✅ Voltooien]    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**AI-personalisatie:**

- **Role-based routing**: Bij selectie van bedrijfstype (ZZP / MKB / Enterprise) worden irrelevante stappen overgeslagen of aangepast. Enterprise-gebruikers zien extra stap "Compliance & Governance"; ZZP-gebruikers slaan "Bulk user import" over.
- **Smart defaults**: Bedrijfsnaam en sector pre-populeren velden in Org Chart (stap 2) en Goals (stap 3).
- **Template aanbeveling**: Na stap 1 suggereert het systeem 3 relevante Company Templates op basis van branche + bedrijfstype (confidence badges).
- **Auto-save**: Wizardstatus wordt elke 30 seconden opgeslagen in `localStorage`. Bij terugkeer ("Je hebt een onvoltooide setup — doorgaan?") kan de gebruiker hervaten.
- **Skip individual fields**: Optionele velden tonen `(optioneel)` label; "Stap overslaan" slaat de volledige stap over en is altijd later bereikbaar via `/company/settings`.
- **Voortgangsbehoud**: Wizard is op elk moment toegankelijk via `/onboarding` — niet éénmalig.

---

## 6. Design System Integratie

### 6.1 Token Uitbreidingen

```css
/* Company Layer Tokens */
:root {
  /* Goal Colors */
  --color-goal-mission: #7c3aed;        /* Purple */
  --color-goal-strategic: #2563eb;      /* Blue */
  --color-goal-project: #0891b2;        /* Cyan */
  --color-goal-task: #059669;           /* Green */

  /* Status Colors */
  --color-status-online: #22c55e;
  --color-status-idle: #eab308;
  --color-status-error: #f97316;
  --color-status-offline: #ef4444;

  /* Confidence Levels */
  --color-confidence-exact: #22c55e;
  --color-confidence-high: #84cc16;
  --color-confidence-medium: #eab308;
  --color-confidence-low: #f97316;
  --color-confidence-none: #6b7280;

  /* Board Priority */
  --color-priority-urgent: #dc2626;
  --color-priority-high: #ea580c;
  --color-priority-normal: #3b82f6;
  --color-priority-low: #6b7280;

  /* Budget Health */
  --color-budget-healthy: #22c55e;
  --color-budget-warning: #eab308;
  --color-budget-critical: #ef4444;
}
```

### 6.2 Typography Schaling

```css
/* Goal Hierarchy Typography */
.text-goal-mission {
  font-size: 1.5rem;      /* 24px */
  font-weight: 700;
  line-height: 1.2;
}

.text-goal-strategic {
  font-size: 1.25rem;     /* 20px */
  font-weight: 600;
  line-height: 1.3;
}

.text-goal-project {
  font-size: 1rem;        /* 16px */
  font-weight: 600;
  line-height: 1.4;
}

.text-goal-task {
  font-size: 0.875rem;    /* 14px */
  font-weight: 500;
  line-height: 1.5;
}
```

### 6.3 Spacing voor Hiërarchie

```css
/* Goal Tree Indentation */
.goal-indent-mission { margin-left: 0; }
.goal-indent-strategic { margin-left: 1.5rem; }
.goal-indent-project { margin-left: 3rem; }
.goal-indent-task { margin-left: 4.5rem; }
```

---

## 7. Interactie Patronen

### 7.1 Goal Alignment Feedback

Wanneer een taak wordt gestart:

```
1. User klikt "Start Task"
   ↓
2. Goal Alignment Validator checkt
   ├─ ALIGNED (>= 0.6):
   │   → Groene toast: "✅ Taak is aligned met 'Omzet verdubbelen'"
   │   → Execution start
   │
   ├─ DRIFT_WARNING (0.3-0.6):
   │   → Gele toast: "⚠️ Taak is tangentieel aan doel. Doorgaan?"
   │   → [Doorgaan] [Details] [Annuleren]
   │
   └─ MISALIGNED (< 0.3):
       → Rode modal: "❌ Taak conflicteert met doel"
       → Escalatie naar Board Queue
       → [Escaleren] [Annuleren]
```

### 7.2 Real-time Updates

**Heartbeat Status:**
```
User viewing External Agent Hub
    ↓
WebSocket receives heartbeat update
    ↓
Agent card updates without page refresh:
  - Status indicator pulse
  - Metrics update (smooth number transition)
  - Last heartbeat timestamp refresh
    ↓
If status changes (online → offline):
  - Toast notification
  - Card border color change (animation)
  - Sound notification (optional)
```

**Board Queue:**
```
New decision arrives
    ↓
Notification badge increment (bounce animation)
    ↓
If user on Board page:
  - New card slides in from top (stagger animation)
  - Play subtle notification sound
    ↓
If user elsewhere:
  - Browser notification (if permitted)
  - Badge on navigation icon
```

**Org Chart Concurrent Editing (Conflict Resolution UI):**
```
User A: sleept "Sales" node naar nieuwe positie
    ↓
Optimistic update: node beweegt direct (lokaal)
    ↓
Backend: controleert version field (optimistic lock)
    ↓
GEEN conflict (version match):
  - Server confirmeert → WebSocket broadcast naar User B
  - User B: node beweegt soepel zonder interruptie

WEL conflict (version mismatch → 409):
  - Node reverteert naar vorige positie (animated)
  - Toast: "⚠️ Wijziging geannuleerd — [Naam] heeft dit
    department tegelijk aangepast. Probeer opnieuw."
  - [Probeer opnieuw]  [Annuleren]
```

> **Technologie:** Gebruik **Yjs CRDT** voor org chart en goal tree collaborative editing (zie §15). Yjs convergeert automatisch zonder server-side conflict resolution. Voor cursors en presence: Yjs Awareness API.

### 7.3 Drag & Drop Patronen

**Org Chart:**
- **Drag node**: Ghost preview, snap-to-grid
- **Drop on canvas**: Free positioning
- **Drop on node**: Becomes child (auto-connect line)
- **Drop in trash**: Delete confirmation

**Goal Tree:**
- **Drag goal**: Indentation preview (ghost line)
- **Drop on goal**: Becomes child
- **Drop between goals**: Reorder
- **Visual feedback**: Drop zone highlight

---

## 8. Responsive Design

### 8.1 Breakpoints

| Breakpoint | Width | Aangepaste Layout |
|------------|-------|-------------------|
| Mobile | < 640px | Single column, stacked views |
| Tablet | 640-1024px | 2-column grid, collapsible sidebar |
| Desktop | 1024-1440px | Full layout, 3-column grid |
| Wide | > 1440px | Centered content, max-width container |

### 8.2 Mobile Adaptaties

**Company Dashboard (Mobile):**
```
┌─────────────────────────────────────────┐
│ [☰] TechStart BV        [🔔] [👤]     │
├─────────────────────────────────────────┤
│                                         │
│ 🎯 Mission                              │
│ "Duurzame marktleider..."               │
│ [Meer lezen]                            │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📊 Health Metrics    [→]           │ │
│ │                                     │ │
│ │ Agents: 12  |  Packs: 8             │ │
│ │ Tasks: 145  |  Board: 3 ⏳          │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 🎯 Active Goals      [→]           │ │
│ │                                     │ │
│ │ Omzet ×2        [75%] ▓▓▓▓▓▓▓░░    │ │
│ │ Kosten -15%     [45%] ▓▓▓▓░░░░░    │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 🏢 Organisation      [→]           │ │
│ │                                     │ │
│ │ [Simple list view]                  │ │
│ │ • Sales (3 members)                 │ │
│ │ • Finance (2 members)               │ │
│ │ • Operations (4 members)            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [+ Quick Action]                        │
│                                         │
└─────────────────────────────────────────┘
```

**Board Queue (Mobile):**
- Swipe naar rechts = Goedkeuren
- Swipe naar links = Afwijzen
- Tap = Details bekijken
- Pull-to-refresh

**Org Chart (Mobile):**
- Verticale tree view (ipv horizontaal)
- Tap to expand/collapse
- Pinch to zoom
- Pan with touch

### 8.3 Touch Targets

| Element | Min Size | Padding |
|---------|----------|---------|
| Buttons | 44x44px | 8px |
| Cards | Full width | 16px margin |
| List items | 48px height | 12px padding |
| Icons | 24x24px | 10px touch area |

---

## 9. Toegankelijkheid (A11y)

### 9.1 WCAG 2.1 AA Compliance

| Criterium | Implementatie |
|-----------|---------------|
| **1.1.1 Non-text Content** | Alle iconen hebben aria-labels of hidden text |
| **1.3.1 Info and Relationships** | Structural elements (header, main, nav), ARIA landmarks |
| **1.4.3 Contrast** | Min 4.5:1 voor normale text, 3:1 voor grote text |
| **2.1.1 Keyboard** | Alle functionaliteit toegankelijk via toetsenbord |
| **2.4.3 Focus Order** | Logische tab volgorde, skip links |
| **4.1.2 Name, Role, Value** | ARIA labels voor custom components |

### 9.2 Keyboard Navigation

**Org Chart Builder:**
```
Tab: Navigate between nodes
Arrow keys: Move selection up/down/left/right
Enter: Select node / Open edit
Space: Expand/collapse
Delete: Remove node (with confirmation)
Ctrl+N: Add new node
Ctrl+S: Save
Esc: Deselect / Close panel
```

**Goal Tree:**
```
Tab: Navigate goals
Arrow Right: Expand / Go to first child
Arrow Left: Collapse / Go to parent
Arrow Up/Down: Navigate siblings
Enter: Edit goal
Space: Toggle expand/collapse
```

**Globale sneltoetsen (alle pagina's):**
```
?: Toon keyboard shortcuts help panel (overlay)
Cmd/Ctrl+K: Command palette (zoek pagina's, goals, agents)
Cmd/Ctrl+S: Sla huidige context op
Esc: Sluit modal / deselect
```

**Keyboard Shortcuts Help Panel (`?`):**
```
┌─────────────────────────────────────────────────────────┐
│ ⌨️  Keyboard Shortcuts                              [×] │
├──────────────────────────────────────────────────────────┤
│ Globaal                                                  │
│  ?          Toon dit paneel                             │
│  ⌘K         Command palette                            │
│  ⌘S         Opslaan                                    │
│  Esc        Sluiten / Deselecteren                     │
├──────────────────────────────────────────────────────────┤
│ Org Chart Builder                                        │
│  Tab        Volgende node                              │
│  ↑↓←→       Navigeer nodes                            │
│  Enter      Bewerk geselecteerde node                  │
│  Del        Verwijder node (met bevestiging)           │
│  ⌘N         Nieuw department                          │
├──────────────────────────────────────────────────────────┤
│ Goal Tree                                                │
│  →          Uitklappen / Naar kind                     │
│  ←          Inklappen / Naar ouder                     │
│  ↑↓          Navigeer siblings                         │
│  Enter      Bewerk goal                                │
└──────────────────────────────────────────────────────────┘
```

### 9.3 Screen Reader Support

**Goal Ancestry Breadcrumb:**
```html
<nav aria-label="Goal hierarchy">
  <ol>
    <li>
      <a href="/goals/mission-1" aria-current="false">
        Mission: Duurzame marktleider
      </a>
    </li>
    <li aria-hidden="true">→</li>
    <li>
      <a href="/goals/strategic-1" aria-current="false">
        Strategic: Omzet verdubbelen
      </a>
    </li>
    <li aria-hidden="true">→</li>
    <li>
      <span aria-current="page">
        Project: Webshop optimalisatie
      </span>
    </li>
  </ol>
</nav>
```

**Board Decision Card:**
```html
<article aria-label="Board decision: Budget overschrijding">
  <h3>Budget overschrijding vereist goedkeuring</h3>
  <dl>
    <dt>Company</dt>
    <dd>TechStart BV</dd>
    <dt>Goal</dt>
    <dd>Omzet verdubbelen</dd>
    <dt>Risk Level</dt>
    <dd>Medium</dd>
  </dl>
  <button aria-label="Goedkeuren: Budget overschrijding">
    Goedkeuren
  </button>
</article>
```

### 9.4 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  .pulse-animation,
  .bounce-animation,
  .slide-animation {
    animation: none;
    transition: none;
  }

  .heartbeat-indicator {
    /* Static color instead of pulse */
    background-color: var(--color-status-online);
  }
}
```

---

## 10. Micro-interacties & Animaties

### 10.1 Timing & Easing

```css
:root {
  /* Durations */
  --duration-instant: 0ms;
  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 350ms;
  --duration-enter: 400ms;
  --duration-exit: 300ms;

  /* Easings */
  --ease-default: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-enter: cubic-bezier(0, 0, 0.2, 1);
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);
  --ease-bounce: cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
```

### 10.2 Component Animaties

**Goal Progress Bar:**
```css
@keyframes progress-fill {
  from { width: 0%; }
  to { width: var(--progress); }
}

.goal-progress-bar {
  animation: progress-fill 1s var(--ease-enter) forwards;
}

/* Value counter animation */
@keyframes count-up {
  from { --num: 0; }
  to { --num: var(--target); }
}
```

**Heartbeat Indicator:**
```css
@keyframes heartbeat-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.1);
  }
}

.heartbeat-indicator.online {
  animation: heartbeat-pulse 2s ease-in-out infinite;
}

.heartbeat-indicator.offline {
  animation: heartbeat-pulse 1s ease-in-out infinite;
  background-color: var(--color-status-offline);
}
```

**Board Card Entrance:**
```css
@keyframes slide-in-top {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.board-decision-card {
  animation: slide-in-top var(--duration-enter) var(--ease-enter);
}

/* Stagger children */
.board-queue > .board-decision-card:nth-child(1) { animation-delay: 0ms; }
.board-queue > .board-decision-card:nth-child(2) { animation-delay: 100ms; }
.board-queue > .board-decision-card:nth-child(3) { animation-delay: 200ms; }
```

**Pack Activation Success:**
```css
@keyframes activation-success {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}

.pack-card.activated {
  animation: activation-success 0.3s var(--ease-bounce);
  border-color: var(--color-confidence-high);
  background-color: var(--color-confidence-high-bg);
}
```

### 10.3 Loading States

**Skeleton Loading:**
```
┌─────────────────────────────────────────┐
│ ┌─────────┐ ┌─────────────────────────┐ │
│ │ ▓▓▓▓▓▓▓ │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ │ ▓▓▓▓▓▓▓ │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ └─────────┘ └─────────────────────────┘ │
└─────────────────────────────────────────┘

@keyframes skeleton-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-skeleton-base) 25%,
    var(--color-skeleton-highlight) 50%,
    var(--color-skeleton-base) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
}
```

**Org Chart Node Loading:**
```
┌─────────────────────────┐
│ ┌─────┐ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│ │ ▓▓▓ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│ └─────┘ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
└─────────────────────────┘
```

---

## 11. Error Handling & Feedback

### 11.1 Error Types & Presentatie

| Error Type | Presentatie | Herstel |
|------------|-------------|---------|
| **Validation** | Inline field errors | Correct input |
| **Network** | Toast + retry button | Auto-retry / Manual |
| **Permission** | Modal + redirect | Contact admin |
| **Goal Misalignment** | Warning modal | Escalate / Cancel |
| **Heartbeat Timeout** | Agent card + notification | Check agent / Restart |

### 11.2 Error Messages (Nederlands)

**Goal Alignment:**
```
⚠️ DRIFT_WARNING:
"Deze taak lijkt minder relevant voor je huidige doel
'OmezProject: Webshop optimalisatie'.
Wil je doorgaan of het doel aanpassen?"

❌ MISALIGNED:
"Deze taak conflicteert met je strategische doel
'Kosten verlagen'. Deze actie vereist Board approval."
[Escaleren naar Board] [Annuleren]
```

**External Agent:**
```
🔴 OFFLINE:
"Agent 'data-analyzer-prod' reageert niet meer (5 min).
Mogelijke oorzaken:
• Script is gecrasht
• Netwerk connectiviteit
• API key verlopen"

[Diagnose uitvoeren] [Agent herstarten] [Contact support]
```

### 11.3 Toast Notifications

```typescript
interface ToastConfig {
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}
```

**Voorbeelden:**
```
┌─────────────────────────────────────────┐
│ ✅ Pack geactiveerd                     │
│ mkb.digital_storefront is nu actief    │
│                    [Undo]     [×]       │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ ⚠️ Goal alignment warning               │
│ Taak is tangentieel aan doel           │
│                 [Details]     [×]       │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 🔴 Agent offline                        │
│ data-analyzer-prod mist heartbeats     │
│               [Diagnose]     [×]        │
└─────────────────────────────────────────┘
```

---

## 12. Empty States & Onboarding

### 12.1 Empty States

**No Company Yet:**
```
┌─────────────────────────────────────────┐
│                                         │
│         ┌─────────────┐                 │
│         │   🏢        │                 │
│         │   +         │                 │
│         └─────────────┘                 │
│                                         │
│      Nog geen Company geconfigureerd    │
│                                         │
│   Start je virtuele bedrijf in 3        │
│   simpele stappen.                      │
│                                         │
│      [🚀 Company Aanmaken]              │
│                                         │
│   [ℹ️ Meer informatie]                  │
│                                         │
└─────────────────────────────────────────┘
```

**No Goals:**
```
┌─────────────────────────────────────────┐
│                                         │
│              🎯                         │
│                                         │
│      Geen goals gedefinieerd            │
│                                         │
│   Goals helpen je om elke taak te       │
│   koppelen aan een groter doel.         │
│                                         │
│      [+ Eerste Goal Maken]              │
│                                         │
│   💡 Tip: Begin met je Company Mission  │
│                                         │
└─────────────────────────────────────────┘
```

**Empty Board Queue:**
```
┌─────────────────────────────────────────┐
│                                         │
│              ✅                         │
│                                         │
│      Geen pending beslissingen          │
│                                         │
│   Alle governance beslissingen zijn     │
│   verwerkt. Goed werk!                  │
│                                         │
│   [📊 Bekijk Historie]                  │
│                                         │
└─────────────────────────────────────────┘
```

**No External Agents:**
```
┌─────────────────────────────────────────┐
│                                         │
│              🤖                         │
│                                         │
│      Geen externe agents                │
│                                         │
│   Integreer je eigen scripts en tools   │
│   via het heartbeat protocol.           │
│                                         │
│      [+ Agent Registreren]              │
│                                         │
│   [📚 SDK Documentatie]                 │
│                                         │
└─────────────────────────────────────────┘
```

**No Departments (Org Chart Builder):**
```
┌─────────────────────────────────────────┐
│                                         │
│           ┌─────────────┐               │
│           │   🏢        │               │
│           │   + ?       │               │
│           └─────────────┘               │
│                                         │
│   Nog geen departments aangemaakt       │
│                                         │
│   Begin met het CEO-niveau en voeg      │
│   daarna afdelingen toe.                │
│                                         │
│      [+ Eerste Department]              │
│                                         │
│   💡 Tip: Gebruik een template voor     │
│   een snel startpunt                    │
│   [📋 Templates bekijken]               │
│                                         │
└─────────────────────────────────────────┘
```

### 12.2 Contextual Help

**Tooltips:**
```
┌─────────────────────────────────────────┐
│  Confidence Score [?]                   │
│                                         │
│  Tooltip:                               │
│  ┌─────────────────────────────────────┐│
│  │ Het percentage geeft aan hoe sterk ││
│  │ deze pack matcht met je bedrijfs-  ││
│  │ structuur. Hoger = betere match.   ││
│  │                                    ││
│  │ EXACT (>90%): Auto-activation      ││
│  │ HIGH (70-90%): Sterke match        ││
│  │ MEDIUM (50-70%): Suggestie         ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

**Coach Marks (First-time):**
```
┌─────────────────────────────────────────┐
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  🎯 Dit is je Goal Tree           │  │
│  │                                   │  │
│  │  Hier zie je de hiërarchie van   │  │
│  │  je bedrijfsdoelen. Elke taak    │  │
│  │  linkt automatisch aan deze      │  │
│  │  structuur.                      │  │
│  │                                   │  │
│  │  [Volgende] [Overslaan]          │  │
│  └───────────────────────────────────┘  │
│           ↑                             │
│     [Highlight]                         │
│                                         │
└─────────────────────────────────────────┘
```

---

## 13. Dark Mode

### 13.1 Dark Mode Tokens

```css
[data-theme="dark"] {
  /* Backgrounds */
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;

  /* Goal Colors (adjusted for dark) */
  --color-goal-mission: #a78bfa;
  --color-goal-strategic: #60a5fa;
  --color-goal-project: #22d3ee;
  --color-goal-task: #34d399;

  /* Status (brighter for visibility) */
  --color-status-online: #4ade80;
  --color-status-offline: #f87171;

  /* Text */
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
}
```

### 13.2 Dark Mode Component Examples

**Goal Card (Dark):**
```
Dark Mode:
┌─────────────────────────────────────────┐
│ BG: #1e293b                             │
│                                         │
│ 🎯 Goal Title                    [▲▼] │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Progress: #334155 track, #60a5fa fill │
│                                         │
│ Status: #34d399 icon                    │
│                                         │
└─────────────────────────────────────────┘
```

---

## 14. Performance & Perceived Performance

### 14.1 Loading Strategieën

**Progressive Loading:**
```
1. Skeleton placeholders (instant)
2. Critical data (mission, goals) < 500ms
3. Secondary data (metrics) < 1s
4. Non-critical (suggestions) < 2s
```

**Virtualisatie (grote lijsten):**

| Drempelwaarde | Component | Oplossing |
| ------------- | --------- | --------- |
| >200 goals | Goal Tree (Lijst/Kanban) | `@tanstack/react-virtual` — render alleen zichtbare rijen |
| >100 org nodes | Org Chart Builder | ReactFlow ingebouwde virtualisatie + lazy-load sub-trees |
| >50 board items | Board Approval Queue | Windowed list met infinite scroll |
| >500 pack catalog | Pack Selector | Virtual scroll + server-side search |

```typescript
// Voorbeeld: Goal Tree Lijst met TanStack Virtual
import { useVirtualizer } from '@tanstack/react-virtual';

const rowVirtualizer = useVirtualizer({
  count: flatGoals.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 72,  // geschatte rijhoogte in px
  overscan: 5,             // extra rijen buiten viewport
});
```

> **Lazy-load child goals:** Laad children pas on-demand (bij expand). Cache geladen children in `Map<goalId, Goal[]>` om herhaalde fetches te voorkomen.

**Optimistic UI:**
```typescript
// Pack activation
const activatePack = async (packId: string) => {
  // 1. Optimistically update UI
  setPackStatus(packId, 'activating');

  // 2. Show success toast immediately
  showToast({ type: 'info', message: 'Pack wordt geactiveerd...' });

  try {
    // 3. Actual API call
    await api.activatePack(packId);

    // 4. Confirm success
    setPackStatus(packId, 'active');
    showToast({ type: 'success', message: 'Pack geactiveerd!' });
  } catch (error) {
    // 5. Rollback on error
    setPackStatus(packId, 'inactive');
    showToast({ type: 'error', message: 'Activatie mislukt' });
  }
};
```

### 14.2 Perceived Performance Tricks

**Instant Feedback:**
```
User clicks "Create Company"
    ↓
< 100ms: Button shows loading spinner
         Route transition starts
    ↓
< 300ms: New page skeleton visible
    ↓
< 500ms: Critical content (mission input) visible
    ↓
< 1s:   Full page content
```

**Skeleton to Content Transition:**
```css
.content-reveal {
  animation: fade-in var(--duration-fast) var(--ease-enter);
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### 14.3 Caching Strategie

| Data | Cache Strategy | TTL |
|------|----------------|-----|
| Company config | Stale-while-revalidate | 5 min |
| Org chart | Stale-while-revalidate | 2 min |
| Goals | Real-time (WebSocket) | - |
| Pack catalog | Static + background refresh | 1 hour |
| Board queue | Real-time (WebSocket) | - |
| External agent status | Real-time (WebSocket) | - |

---

## 15. Real-time Collaboration Architecture

### 15.1 Technologiekeuze: Yjs CRDT

De Org Chart Builder en Goal Tree ondersteunen **simultaan bewerken door meerdere gebruikers**. De aanbevolen aanpak is **Yjs CRDT** (Conflict-free Replicated Data Types):

| Aspect | Yjs CRDT | Optimistic Lock (huidig) |
| ------ | -------- | ------------------------ |
| **Conflictresolutie** | Automatisch — clients convergeren | Handmatig — 409 + revert |
| **Latency** | <50ms (lokale update direct zichtbaar) | 1 RTT naar backend |
| **Complexiteit backend** | Lager (geen conflict-logica nodig) | Version field vereist |
| **Use case** | Free-form editing (nodes slepen, goals editen) | Formulieren, budgetten |

> **Aanbeveling:** Gebruik Yjs voor **org chart node posities** en **goal tree structuur** (drag-and-drop). Behoud de bestaande optimistic lock (version field) voor **formuliervelden** (naam, budget, deadline) — daar is conflict-UX duidelijker.

### 15.2 Stack

```
Frontend:          Yjs + @tldraw/sync (of y-websocket provider)
Presence:          Yjs Awareness API (cursor pos + user info)
Backend:           Hocuspocus WebSocket server (open-source)
                   OF: Liveblocks Yjs (managed, minder infra)
Rich text:         Tiptap + @tiptap/extension-collaboration
```

### 15.3 Presence Indicators (Figma-patroon)

**Live cursors op Org Chart en Goal Tree:**
```
┌──────────────────────────────────────────────────────────────┐
│  ReactFlow Canvas                                            │
│                                                              │
│    [CEO]                                                     │
│      │              👆 Jan (blauw)                          │
│   [Sales]──────────────────────────────                     │
│      │                                                       │
│   [Finance]     👆 Lisa (groen)                             │
│                                                              │
│  ┌───────────────────────────────────┐                      │
│  │ 🔵 Jan  🟢 Lisa  +2 anderen       │  ← avatar stack      │
│  └───────────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────┘
```

**Technische implementatie:**
```typescript
// Yjs Awareness voor cursor tracking
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';

const ydoc = new Y.Doc();
const provider = new WebsocketProvider(
  'wss://api.sanskritisetu.com/yjs',
  `org-chart-${companyId}`,
  ydoc
);

// Cursor positie broadcasten (debounced 50ms)
const awareness = provider.awareness;
const broadcastCursor = useMemo(
  () => debounce((position: XYPosition) => {
    awareness.setLocalStateField('cursor', position);
  }, 50),
  [awareness]
);

// Cursor posities van anderen weergeven
const [cursors, setCursors] = useState<Map<number, CursorState>>(new Map());
awareness.on('change', () => {
  const states = new Map<number, CursorState>();
  awareness.getStates().forEach((state, clientId) => {
    if (clientId !== awareness.clientID && state.cursor) {
      states.set(clientId, { position: state.cursor, user: state.user });
    }
  });
  setCursors(states);
});
```

**CursorOverlay component:**
```typescript
interface CursorState {
  position: XYPosition;
  user: { name: string; color: string; avatar?: string };
}

export function CollaborationCursorOverlay({ cursors }: { cursors: Map<number, CursorState> }) {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {Array.from(cursors.entries()).map(([clientId, { position, user }]) => (
        <div
          key={clientId}
          className="absolute transition-transform duration-75"
          style={{ transform: `translate(${position.x}px, ${position.y}px)` }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16">
            <path d="M0 0 L0 12 L4 8 L8 16 L10 15 L6 7 L12 7Z"
                  fill={user.color} stroke="white" strokeWidth="1" />
          </svg>
          <span
            className="absolute top-4 left-2 px-1.5 py-0.5 rounded text-xs text-white whitespace-nowrap"
            style={{ backgroundColor: user.color }}
          >
            {user.name}
          </span>
        </div>
      ))}
    </div>
  );
}
```

### 15.4 Conflict Feedback UI

**Scenario A — Geen conflict (Yjs automatisch):**
```
User A sleept Sales node →  lokale update direct zichtbaar
User B ziet Sales node bewegen in real-time (Yjs sync)
→ Geen toast, geen interruptie
```

**Scenario B — Formulierconflict (optimistic lock, 409):**
```
User A opent "Sales" edit form
User B slaat "Sales" budget op (version 3 → 4)
User A probeert op te slaan (version 3 → verwacht 4)
  → 409 ConflictError van backend
  → Toast: "⚠️ [Lisa] heeft dit department net bijgewerkt.
             Je wijzigingen zijn niet opgeslagen."
  → [Herladen en opnieuw invullen]  [Toch overschrijven]
  → Form toont diff: huidig (Lisa's versie) vs jouw versie
```

**Diff weergave bij conflict:**
```
┌──────────────────────────────────────────────────────────┐
│ ⚠️ Conflicterende wijziging                              │
├────────────────────┬─────────────────────────────────────┤
│ Jouw versie        │ Lisa's versie (opgeslagen)          │
├────────────────────┼─────────────────────────────────────┤
│ Budget: €80.000    │ Budget: €95.000                     │
│ Head: Jan          │ Head: Pieter                        │
├────────────────────┴─────────────────────────────────────┤
│ [← Jouw versie behouden]  [Lisa's versie overnemen →]   │
└──────────────────────────────────────────────────────────┘
```

### 15.5 Avatar Stack Component

```typescript
interface CollaboratorAvatarStackProps {
  collaborators: Array<{ id: string; name: string; color: string; avatar?: string }>;
  max?: number;  // default: 4 (overige tonen als "+N")
  onHide?: () => void;  // verberg andere cursors (Figma-patroon)
}
```

```
┌─────────────────────────────────────┐
│ 🔵 🟢 🟣 +2                [👁 Hide] │
│ Jan  Lisa  Pieter   anderen         │
└─────────────────────────────────────┘
```

- Hover op avatar = tooltip met naam + "Bekijk wat [naam] doet"
- Click op avatar = camera springt naar cursor positie van die gebruiker
- `[👁 Hide]` verbergt alle cursors (voor focus-mode)

---

## 16. ReactFlow & Rendering Performance Guide

### 16.1 Memoïsatie (kritiek voor >30 nodes)

Alle custom node- en edge-componenten **moeten** in `React.memo()` worden gewrapped. Zonder memoïsatie re-rendert elke node bij elke state-update (bijv. cursor beweging).

```typescript
// ✅ CORRECT
const OrgChartNode = React.memo(({ data }: NodeProps<DepartmentData>) => {
  return (
    <div className="org-chart-node">
      <h3>{data.name}</h3>
      <p>{data.head}</p>
    </div>
  );
});
OrgChartNode.displayName = 'OrgChartNode';

// ❌ FOUT — re-rendert bij elke parent state-wijziging
const OrgChartNode = ({ data }: NodeProps<DepartmentData>) => { ... };
```

**Props-functies stabiliseren met `useCallback`:**
```typescript
// ✅ CORRECT — stabiele referentie
const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
  setSelectedNode(node.id);
}, []);  // geen dependencies → altijd dezelfde functie

// ❌ FOUT — nieuwe functie bij elke render → memo werkt niet
const onNodeClick = (event: React.MouseEvent, node: Node) => { ... };
```

**Object-props stabiliseren met `useMemo`:**
```typescript
// ✅ CORRECT
const defaultEdgeOptions = useMemo(() => ({
  animated: false,
  style: { stroke: 'var(--color-border)' }
}), []);

// ❌ FOUT — nieuw object bij elke render
const defaultEdgeOptions = { animated: false, style: { ... } };
```

### 16.2 Dagre Auto-layout

**Dagre** is het aanbevolen layout-algoritme voor de Org Chart Builder. Het berekent automatisch hiërarchische node-posities (zoals een org chart hoort).

```typescript
import dagre from '@dagrejs/dagre';

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

export function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB'  // TB = top-bottom (standaard), LR = links-rechts
): { nodes: Node[]; edges: Edge[] } {
  dagreGraph.setGraph({ rankdir: direction, nodesep: 80, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 200, height: 80 });
  });
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  return {
    nodes: nodes.map((node) => {
      const { x, y } = dagreGraph.node(node.id);
      return { ...node, position: { x: x - 100, y: y - 40 } };
    }),
    edges,
  };
}
```

**Gebruik in component:**
```typescript
const [nodes, setNodes, onNodesChange] = useNodesState([]);
const [edges, setEdges, onEdgesChange] = useEdgesState([]);

const onAutoLayout = useCallback(() => {
  const { nodes: layoutedNodes, edges: layoutedEdges } =
    getLayoutedElements(nodes, edges, 'TB');
  setNodes([...layoutedNodes]);
  setEdges([...layoutedEdges]);
}, [nodes, edges]);

// [🪄 Auto-layout] knop roept onAutoLayout() aan
```

### 16.3 Performance Drempelwaarden

| Nodes | Aanpak |
| ----- | ------ |
| <30 | Standaard ReactFlow, geen extra maatregelen |
| 30–100 | `React.memo()` + `useCallback` verplicht; minimap aan |
| 100–500 | Lazy-load sub-trees (laad children pas bij expand) |
| >500 | ReactFlow virtualisatie-mode + server-side paginering van departments |

### 16.4 Sidebar State Isolatie

Een veelvoorkomende performance-fout: de details-sidebar abonneert zich op de volledige `nodes`-array, waardoor hij bij elke node-beweging re-rendert.

```typescript
// ❌ FOUT — sidebar re-rendert bij elke node-drag
function DepartmentSidebar({ nodes }: { nodes: Node[] }) {
  const selected = nodes.find(n => n.selected);
  return <form>{selected?.data.name}</form>;
}

// ✅ CORRECT — sidebar ontvangt alleen geselecteerde node-id
function DepartmentSidebar({ selectedNodeId }: { selectedNodeId: string | null }) {
  // Haal node-data op via selector, niet via volledige array
  const node = useStore(
    useCallback((s) => s.nodeInternals.get(selectedNodeId ?? ''), [selectedNodeId])
  );
  return <form>{node?.data.name}</form>;
}
```

### 16.5 Minimap Configuratie

```typescript
<ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange}>
  <MiniMap
    nodeColor={(node) => {
      switch (node.data.budgetStatus) {
        case 'healthy': return 'var(--color-budget-healthy)';
        case 'warning': return 'var(--color-budget-warning)';
        case 'critical': return 'var(--color-budget-critical)';
        default: return 'var(--color-bg-tertiary)';
      }
    }}
    nodeStrokeWidth={2}
    pannable
    zoomable
    style={{ bottom: 16, right: 16 }}
  />
  <Controls />
  <Background variant={BackgroundVariant.Dots} gap={24} size={1} />
</ReactFlow>
```

---

## Appendix A: Iconography

### A.1 Icon Set

| Concept | Icon | Usage |
|---------|------|-------|
| Mission | 🎯 | Goal hierarchy top level |
| Strategic | 📊 | Strategic goals |
| Project | 📁 | Project goals |
| Task | ✅ | Tasks |
| Company | 🏢 | Company entities |
| Department | 👥 | Departments |
| Agent (internal) | 🤖 | Internal agents |
| Agent (external) | 🔌 | External agents |
| Pack | 📦 | Domain packs |
| Board | 🏛️ | Governance |
| Approval | ✅ | Approved decisions |
| Rejection | ❌ | Rejected decisions |
| Heartbeat | 💓 | Agent health |
| Online | 🟢 | Active status |
| Offline | 🔴 | Inactive status |
| Warning | ⚠️ | Alerts |
| Confidence HIGH | 🟢 | Match confidence |
| Confidence MEDIUM | 🟡 | Match confidence |
| Confidence LOW | 🟠 | Match confidence |

### A.2 Icon Sizes

| Context | Size |
|---------|------|
| Inline with text | 16px |
| List items | 20px |
| Cards headers | 24px |
| Empty states | 48px |
| Feature highlights | 64px |

---

## Appendix B: Figma Structure

```
SanskritiSetu UI Kit
├── 01. Foundations
│   ├── Colors (light/dark)
│   ├── Typography
│   ├── Spacing
│   ├── Shadows
│   └── Icons
│
├── 02. Components
│   ├── Buttons
│   ├── Inputs
│   ├── Cards
│   ├── Modals
│   ├── Navigation
│   ├── GoalAncestryBreadcrumb
│   ├── OrgChartNode
│   ├── GoalCard
│   ├── PackActivationCard
│   ├── BoardDecisionCard
│   └── ExternalAgentCard
│
├── 03. Patterns
│   ├── Forms
│   ├── Tables
│   ├── Lists
│   ├── Empty States
│   └── Loading States
│
├── 04. Page Templates
│   ├── Company Dashboard
│   ├── Org Chart Builder
│   ├── Goal Tree
│   ├── Board Queue
│   └── External Agent Hub
│
└── 05. Prototypes
    ├── Onboarding Flow
    ├── Goal Alignment Flow
    ├── Board Approval Flow
    └── External Agent Setup
```

---

Laatste update: 11 maart 2026 — v1.1 (gap review + best practices verwerkt)

**Verantwoordelijk:**
- [ ] UX Lead
- [ ] Frontend Lead
- [ ] Product Owner
