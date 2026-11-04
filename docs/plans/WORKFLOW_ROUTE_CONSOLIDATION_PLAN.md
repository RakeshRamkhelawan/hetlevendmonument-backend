# Workflow Route Consolidatie Implementatieplan

**Datum:** 25 maart 2026
**Status:** Ready for Review
**Scope:** Consolidatie van 5 workflow-gerelateerde routes naar 2 canonieke routes
**Doel:** UX-verwarring elimineren, governance versterken, functionaliteit behouden

---

## Architectuurprincipes (Leidend voor Alle Beslissingen)

**Owner of Truth Regels:**

1. **`/workflows`** is de **enige** inventory/manage surface
   - Alle workflow-lijsten, zoekopdrachten, filters en lifecycle-management
   - Geen andere route toont workflow-inventaris

2. **`/focus-builder`** is de **enige** authoring surface
   - Alle workflow-creatie, editing, refinement en template-instantiatie
   - Geen nieuwe authoring-functionaliteit toevoegen aan deprecated routes
   - Alle creatie-paden convergeren hier

3. **Templates zijn een mode binnen de authoring surface**
   - Geen zelfstandige product-ingang meer
   - Blijft ontdekkbaar via navigatie (alias-strategie, zie hieronder)

**Convergentieregel:**
> Alle workflow creation en editing moet convergeren op `/focus-builder`. Geen uitzonderingen.

---

## Quick Reference (Executive Summary)

### Beslisregels (Owner of Truth)

| Vraag | Route | Toelichting |
| ------- | ------- | ------------- |
| Ik wil bestaande workflows bekijken | `/workflows` | Enige inventory surface |
| Ik wil een workflow beheren (delete, status) | `/workflows` | Enige lifecycle surface |
| Ik wil een nieuwe workflow maken | `/focus-builder` | Enige authoring surface |
| Ik wil een bestaande workflow bewerken | `/focus-builder?id=` | Enige edit surface |
| Ik wil een template gebruiken | `/focus-builder?mode=templates` | Templates zijn een mode |
| Ik wil een template ontdekken | Navigatie → Templates | Wijst naar `/focus-builder?mode=templates` |

### Route Status Overzicht

| Route | Status | Actie | Timeline |
| ------- | -------- | ------- | ---------- |
| `/workflows` | ✅ Canoniek | Geen | Blijft |
| `/focus-builder` | ✅ Canoniek | Geen | Blijft |
| `/workflow-builder` | ⚠️ Deprecated | Hard redirect | Fase 3 |
| `/workflow-templates` | ⚠️ Deprecated | Hard redirect | Fase 3 |
| `/templates` | 🟡 Alias | Zachte redirect → optioneel verwijderen | Fase 1-5 |

### Fasering in 1 Oogopslag

| Fase | Doel | Belangrijkste Actie | Duration |
| ------ | ------ | --------------------- | ---------- |
| **Fase 1** | Navigatie updaten | Templates knop wijst naar focus-builder | Week 1 |
| **Fase 2** | Pariteit bouwen | Templates panel, delete, start options | Week 2-3 |
| **Fase 3** | Harde redirects | `/workflow-builder` en `/workflow-templates` | Week 4 |
| **Fase 4** | Cleanup | Code archiveren, tests valideren | Week 5-6 |
| **Fase 5** | Alias verwijderen | `/templates` optioneel verwijderen | Week 7-8 |

### Parity Gates (Must Pass Before Phase 3)

✅ Template browse, instantiate, canvas hydration, details modal
✅ Blank workflow, existing edit, save/update, execute, delete
✅ Desktop/mobile discoverability, direct URL access

**Signoff required:** Tech Lead, UX Lead, QA Lead, Product Owner

---

## 1. Scope en Afbakening

Dit document beschrijft het volledige implementatieplan om de huidige 5 workflow-gerelateerde routes te consolideren naar 2 canonieke routes:

1. **`/workflows`** — Workflow beheerhub (bestaande workflows beheren)
2. **`/focus-builder`** — Workflow creatiehub (nieuwe workflows maken, bestaande bewerken, templates gebruiken)

**Te depreceren routes:**

- `/workflow-builder` → migrate naar `/focus-builder`
- `/workflow-templates` → migrate naar `/focus-builder?mode=templates`
- `/templates` → **tijdelijk behouden als alias** naar `/focus-builder?mode=templates`

**Alias-strategie voor templates:**

- Conceptueel: templates verhuizen naar focus-builder
- Route-technisch: `/templates` blijft tijdelijk bestaan als nette alias
- Navigatie: "Templates" knop blijft zichtbaar maar wijst naar `/focus-builder?mode=templates`
- Rationale: gebruikers kennen deze ingang, template discovery is echte user intent, eerst UX bewijzen in focus-builder voordat we harde redirects doen

---

## 2. Huidige Staat Analyse

### 2.1 Bestaande Routes

| Route | Component | Doel | Status |
| ------- | ----------- | ------ | -------- |
| `/workflows` | `Workflows.tsx` | Workflow inventaris, zoeken, filteren, beheren | ✅ Behouden |
| `/focus-builder` | `FocusModeBuilderPage.tsx` | AI-assisted workflow creatie | ✅ Behouden |
| `/workflow-builder` | `WorkflowBuilderPage.tsx` | Handmatige workflow editor | ⚠️ Depreceren |
| `/workflow-templates` | `WorkflowTemplatesPage.tsx` | Template catalogus | ⚠️ Depreceren |
| `/templates` | `TemplatesPage.tsx` | Template browser + instantiatie | ⚠️ Depreceren (feature behouden) |

### 2.2 Functionele Overlap

**Probleem:** Drie routes lossen dezelfde user-job op: "Ik wil een workflow maken"

1. `/workflow-builder` — handmatig samenstellen
2. `/workflow-templates` — template kiezen
3. `/templates` — template kiezen + instantiëren

**Gevolg:**

- Gebruiker weet niet welke route te kiezen
- Dubbele logica (template browse in 2 plekken)
- Aparte state management per route
- Moeilijk te onderhouden en testen

### 2.3 Unieke Waarde Per Route

| Route | Unieke Capabilities | Overlap |
| ------- | --------------------- | --------- |
| `/workflows` | Workflow inventaris, search, filter, delete, status management | Geen overlap met builders |
| `/focus-builder` | AI generatie, refinement, chat, template_match, versioning | Overlap met alle builders |
| `/workflow-builder` | Handmatige SOP editor, template sidebar | Volledige overlap met focus-builder |
| `/workflow-templates` | Template grid, categorieën, lokale JSON data | Overlap met templates |
| `/templates` | Template browse, instantiate, API-backed | Overlap met workflow-templates |

---

## 3. Doelarchitectuur

### 3.1 Eindbeeld

```text
┌─────────────────────────────────────────────────────────┐
│                  SanskritiSetu App                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  /workflows                    /focus-builder            │
│  ┌──────────────────┐          ┌──────────────────────┐ │
│  │ Workflow         │          │ Workflow Creatie     │ │
│  │ Management Hub   │          │                      │ │
│  │                  │          │  ┌────────────────┐  │ │
│  │ • Lijst          │          │  │ Start Options  │  │ │
│  │ • Search         │          │  │ • From Scratch │  │ │
│  │ • Filter         │          │  │ • From Template│  │ │
│  │ • Delete         │          │  │ • AI Generate  │  │ │
│  │ • Open/Edit      │ ────────▶│  │ • Continue     │  │ │
│  │ • New Workflow ──┘          │  └────────────────┘  │ │
│  └──────────────────┘          │                      │ │
│                                │  Templates Panel     │ │
│                                │  (?mode=templates)   │ │
│                                └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Route Mapping

| Oude Route | Nieuwe Locatie | Migratietype |
| ------------ | ---------------- | -------------- |
| `/workflows` | `/workflows` | Geen wijziging |
| `/focus-builder` | `/focus-builder` | Geen wijziging |
| `/workflow-builder` | `/focus-builder` | Hard redirect (Fase 3) |
| `/workflow-templates` | `/focus-builder?mode=templates` | Hard redirect (Fase 3) |
| `/templates` | `/focus-builder?mode=templates` | **Alias-strategie**: navigatie wijst al, route blijft bestaan als soft redirect (Fase 1-4), harde redirect pas na parity-signoff (Fase 5) |

### 3.3 Feature Mapping

| Feature | Huidig | Doel |
| --------- | -------- | ------ |
| Workflow lijst | `/workflows` | `/workflows` ✅ |
| Workflow zoeken | `/workflows` | `/workflows` ✅ |
| Workflow delete | `/workflows` | `/workflows` ✅ |
| Workflow openen | `/workflows` → `/focus-builder?id=` | `/workflows` → `/focus-builder?id=` ✅ |
| Nieuwe workflow | `/workflows` → `/focus-builder` | `/workflows` → `/focus-builder` ✅ |
| Handmatige editor | `/workflow-builder` | `/focus-builder` |
| Template catalogus | `/workflow-templates` | `/focus-builder?mode=templates` |
| Template browse | `/templates` | `/focus-builder?mode=templates` |
| Template instantiate | `/templates` | `/focus-builder?mode=templates` |
| AI generatie | `/focus-builder` | `/focus-builder` ✅ |
| Refinement | `/focus-builder` | `/focus-builder` ✅ |

---

## 4. Functional Parity Matrix

### 4.1 `/workflow-builder` → `/focus-builder`

| Capability | Huidige Implementatie | Doel Implementatie | Gap |
| ------------ | ---------------------- | ------------------- | ----- |
| Handmatige canvas editor | `SOPFlowEditor` component | `FocusCanvas` + `NodePropertiesPanel` | ✅ Bestaat al |
| Template sidebar | `TemplateSidebar` component | `TemplatesPanel` in focus-builder | ⚠️ Moet geïntegreerd |
| Workflow opslaan | `WorkflowService.create/update` | `focusBuilderApi.saveWorkflow` | ✅ Bestaat al |
| Workflow uitvoeren | `WorkflowService.execute` | `RunFlowButton` component | ✅ Bestaat al |
| Workflow delete | `WorkflowService.delete` | Moet toegevoegd worden | ⚠️ Moet toe |
| Workflow naam/desc | Inline inputs | Inline inputs | ✅ Bestaat al |
| Nodes bewerken | React Flow editor | React Flow editor | ✅ Bestaat al |

**Acties:**

1. Voeg delete-knop toe aan `FocusModeBuilderEnhanced.tsx` header
2. Integreer template-selectie als startmodus in plaats van sidebar
3. Zorg dat bestaande workflow edit werkt via `?id=` param

### 4.2 `/workflow-templates` → `/focus-builder?mode=templates`

| Capability | Huidige Implementatie | Doel Implementatie | Gap |
| ------------ | ---------------------- | ------------------- | ----- |
| Template grid | `WorkflowTemplateCard` grid | `TemplatesBrowser` component | ✅ Bestaat al |
| Categorie filter | Category tabs | Category tabs in TemplatesBrowser | ✅ Bestaat al |
| Template search | Search input | Search input in TemplatesBrowser | ✅ Bestaat al |
| Template gebruiken | `handleUseTemplate` → alert | `handleUseTemplate` → instantiate + canvas | ⚠️ Moet verbeteren |
| Template details | Alert popup | Modal of side panel | ⚠️ UX verbetering |

**Acties:**

1. `TemplatesBrowser.tsx` hergebruiken in focus-builder context
2. Template instantiatie flow integreren met canvas hydratie
3. Template details modal verbeteren (geen alert)

### 4.3 `/templates` → `/focus-builder?mode=templates`

| Capability | Huidige Implementatie | Doel Implementatie | Gap |
| ------------ | ---------------------- | ------------------- | ----- |
| Template browse | `TemplatesBrowser` | `TemplatesBrowser` | ✅ Bestaat al |
| Template select | `handleSelectTemplate` | `handleSelectTemplate` | ✅ Bestaat al |
| Template instantiate | `InstantiationModal` | `InstantiationModal` | ✅ Bestaat al |
| Blank workflow | `Create Blank Workflow` knop | Start tab in focus-builder | ✅ Bestaat al |
| Template details | Alert popup | Modal | ⚠️ UX verbetering |
| Na instantiatie | Alert + builder | Canvas hydratie + refinement | ⚠️ Moet verbeteren |

**Acties:**

1. `InstantiationModal.tsx` response verwerken tot canvas nodes
2. Template spec omzetten naar workflow nodes/connections
3. Na instantiatie direct refinement mogelijk maken

---

## 5. Implementatiefasen

### **Fase 1: Navigatie Voorbereiden (Week 1)**

**Doel:** Gebruikers navigeren al naar nieuwe waarheid zonder routes te breken

#### 1.1 Update `Sidebar.tsx`

**Bestand:** `frontend/src/components/layout/Sidebar.tsx`

```typescript
const navItems = [
  // ... andere items
  { icon: Workflow, label: 'Workflows', path: '/workflows' }, // WIJZIGEN: wijst nu nog naar /workflow-builder
  { icon: Sparkles, label: 'Create Workflow', path: '/focus-builder' }, // NIEUW
  // Templates: NIET verwijderen, maar wijzigen naar focus-builder met mode param
  { icon: Layers, label: 'Templates', path: '/focus-builder?mode=templates' }, // WIJZIGEN
];
```

**Belangrijk:**

- `Workflows` moet worden omgezet van `/workflow-builder` naar `/workflows`
- `Create Workflow` toevoegen die wijst naar `/focus-builder`
- `Templates` **NIET verwijderen** — wijzigen naar `/focus-builder?mode=templates`
- Rationale: template discovery is echte user intent, gebruikers kennen deze ingang, eerst UX bewijzen in nieuwe context voordat we hem weghalen

#### 1.2 Update `Layout.tsx`

**Bestand:** `frontend/src/components/Layout.tsx`

```typescript
const navigation = [
  // ... andere items
  { name: 'Workflows', href: '/workflows', icon: Workflow, section: 'main' },
  { name: 'Create Workflow', href: '/focus-builder', icon: Sparkles, section: 'main' }, // NIEUW
  // Templates verwijderen of wijzigen naar /focus-builder?mode=templates
];
```

#### 1.3 Update `MobileNav.tsx`

**Bestand:** `frontend/src/components/layout/MobileNav.tsx`

```typescript
const defaultItems: NavItem[] = [
  { label: 'Workflows', path: '/workflows', icon: Workflow },
  // Templates wijzigen naar focus-builder met mode param
  { label: 'Templates', path: '/focus-builder?mode=templates', icon: Layers },
];
```

#### 1.4 Deprecation Banners Toevoegen

**Bestand:** `frontend/src/pages/WorkflowBuilderPage.tsx`

```typescript
// Toevoegen bovenaan component
<div className="bg-amber-500/20 border border-amber-500/50 rounded-xl p-4 mb-6">
  <p className="text-amber-200 font-medium">
    ⚠️ Deze editor verhuist naar Focus Builder
  </p>
  <p className="text-white/60 text-sm mt-1">
    De functionaliteit wordt geïntegreerd in een verbeterde ervaring.
  </p>
  <Button
    variant="primary"
    size="sm"
    className="mt-3"
    onClick={() => navigate('/focus-builder')}
  >
    Ga naar Focus Builder →
  </Button>
</div>
```

**Bestand:** `frontend/src/pages/templates/TemplatesPage.tsx`

```typescript
// Vergelijkbare banner toevoegen
<div className="bg-amber-500/20 border border-amber-500/50 rounded-xl p-4 mb-6">
  <p className="text-amber-200 font-medium">
    🎨 Templates openen nu in Focus Builder
  </p>
  <p className="text-white/60 text-sm mt-1">
    Browse en instantieer templates in de nieuwe workflow builder.
  </p>
  <Button
    variant="primary"
    size="sm"
    className="mt-3"
    onClick={() => navigate('/focus-builder?mode=templates')}
  >
    Open in Focus Builder →
  </Button>
</div>
```

**Bestand:** `frontend/src/pages/workflow/WorkflowTemplatesPage.tsx`

```typescript
// Vergelijkbare banner toevoegen
```

#### 1.5 Update `Workflows.tsx` navigatie

**Bestand:** `frontend/src/pages/Workflows.tsx`

**LET OP:** Dit bestand gebruikt **nu al** de juiste routes!

```typescript
// Regel 65-68 — AL CORRECT
const handleCreateWorkflow = () => {
  navigate('/focus-builder'); // ✅ Bestaat al
};

// Regel 70-73 — AL CORRECT
const handleEditWorkflow = (id: string) => {
  navigate(`/focus-builder?id=${id}`); // ✅ Bestaat al
};
```

**Actie:** Geen wijziging nodig — dit is een voorbeeld van de gewenste eindtoestand die al live staat.

**Voordeel:** Dit betekent dat Fase 1 voor dit component alleen navigatie-items in sidebar/layout hoeft aan te passen, niet de feitelijke workflow-creatieflow.

---

## Parity Signoff Checklist (VEREIST VÓÓR Harde Redirects)

**Critical Gate:** Voordat ook maar één harde redirect wordt geactiveerd (Fase 3), moet deze checklist volledig zijn afgevinkt.

### Template Flow Parity

- [ ] **Template browse** — Gebruiker kan templates browsen in `/focus-builder?mode=templates`
  - Test: template grid laadt, categorieën werken, search werkt
  - Metric: < 500ms laadtijd, geen console errors

- [ ] **Template instantiate** — Gebruiker kan template instantiëren via modal
  - Test: template selectie → modal → parameters invullen → succesvolle instantiatie
  - Metric: API call slaagt, response wordt correct verwerkt

- [ ] **Canvas hydration** — Na instantiatie wordt canvas gevuld met template nodes
  - Test: nodes verschijnen op canvas, connections zijn correct
  - Metric: alle template nodes zichtbaar binnen 2s na instantiatie

- [ ] **Template details** — Gebruiker kan template details bekijken (geen alert!)
  - Test: details modal opent, toont description, integrations, preview
  - Metric: modal sluit netjes, geen memory leaks

### Workflow Authoring Parity

- [ ] **Blank workflow** — Gebruiker kan lege workflow starten
  - Test: "Blank Workflow" knop → leeg canvas → nodes toevoegen → save
  - Metric: workflow wordt opgeslagen met correcte ID

- [ ] **Existing workflow edit** — Gebruiker kan bestaande workflow openen en bewerken
  - Test: `/workflows` → edit knop → `/focus-builder?id=X` → wijzig → save
  - Metric: workflow update slaagt, geen data loss

- [ ] **Save/update** — Workflow opslaan werkt voor nieuwe en bestaande
  - Test: create → save, edit → update
  - Metric: API calls slagen, optimistic updates werken

- [ ] **Execute** — Workflow uitvoeren werkt vanuit builder
  - Test: "Run Workflow" knop → execution start → monitor pagina
  - Metric: execution ID wordt gegenereerd, user wordt doorgestuurd

- [ ] **Delete** — Workflow verwijderen werkt vanuit builder
  - Test: "Delete" knop → confirm → workflow verwijderd → redirect naar `/workflows`
  - Metric: workflow verdwijnt uit lijst, geen orphaned records

### Discoverability Parity

- [ ] **Desktop navigatie** — Templates knop zichtbaar in sidebar
  - Test: sidebar toont "Templates" → wijst naar `/focus-builder?mode=templates`
  - Metric: geen regressie in template discovery rate

- [ ] **Mobile navigatie** — Templates knop zichtbaar in mobile nav
  - Test: mobile bottom nav toont Templates icoon
  - Metric: mobile template usage blijft op baseline

- [ ] **Direct URL access** — `/templates` URL werkt (alias)
  - Test: directe navigatie naar `/templates` opent focus-builder met templates panel
  - Metric: geen 404s, geen broken bookmarks

### Acceptatiecriteria voor Fase 2

**ALLE bovenstaande checkboxes moeten ✅ zijn** voordat:

- Deprecation banners worden verwijderd
- Harde redirects worden geactiveerd
- Code wordt gearchiveerd

**Signoff vereist van:**

- [ ] Tech Lead
- [ ] UX Lead
- [ ] QA Lead
- [ ] Product Owner

---

### **Fase 2: Functionele Pariteit Bouwen (Week 2-3)**

**Doel:** Alle functionaliteit van oude routes migreren naar `/focus-builder`

#### 2.1 Template Mode Integratie in Focus Builder

**Bestand:** `frontend/src/pages/FocusModeBuilderPage.tsx`

```typescript
export default function FocusModeBuilderPage() {
  const navigate = useNavigate();
  const searchParams = new URLSearchParams(window.location.search);
  const workflowId = searchParams.get('id') || undefined;
  const initialPrompt = searchParams.get('prompt') || undefined;
  const mode = searchParams.get('mode') || undefined; // NIEUW: 'templates' | 'scratch' | 'ai'

  // ... rest van code
}
```

**Bestand:** `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

```typescript
export interface FocusModeBuilderEnhancedProps {
  workflowId?: string;
  initialPrompt?: string;
  mode?: 'scratch' | 'templates' | 'ai'; // NIEUW
  onSave?: () => void;
  onExit?: () => void;
}

export const FocusModeBuilderEnhanced: React.FC<FocusModeBuilderEnhancedProps> = ({
  workflowId,
  initialPrompt,
  mode = 'scratch', // DEFAULT
  onSave,
  onExit,
}) => {
  // State voor template mode
  const [showTemplatesPanel, setShowTemplatesPanel] = useState(mode === 'templates');

  // Effect: open templates panel als mode=templates
  useEffect(() => {
    if (mode === 'templates') {
      setShowTemplatesPanel(true);
    }
  }, [mode]);

  // ... rest van code
};
```

#### 2.2 TemplatesPanel Component Creëren

**Bestand:** `frontend/src/components/focus-builder/TemplatesPanel.tsx` (NIEUW)

```typescript
import React from 'react';
import { TemplatesBrowser } from '@/components/templates/TemplatesBrowser';
import { InstantiationModal } from '@/components/templates/InstantiationModal';
import { Template } from '@/types/templates';
import { Button } from '@/components/ui/Button';

interface TemplatesPanelProps {
  onClose: () => void;
  onTemplateSelected: (template: Template) => void;
}

export const TemplatesPanel: React.FC<TemplatesPanelProps> = ({
  onClose,
  onTemplateSelected,
}) => {
  const [selectedTemplate, setSelectedTemplate] = React.useState<Template | null>(null);
  const [isInstantiationModalOpen, setIsInstantiationModalOpen] = React.useState(false);

  const handleSelectTemplate = (template: Template) => {
    setSelectedTemplate(template);
    setIsInstantiationModalOpen(true);
  };

  const handleInstantiationSuccess = (response: any) => {
    // Hydrate canvas met template spec
    // Dit wordt afgehandeld door parent component via callback
    onTemplateSelected({
      template_id: response.template_id,
      spec: response.spec,
      workflow_name: response.workflow_name,
    });
    setIsInstantiationModalOpen(false);
    onClose();
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700/50">
        <h2 className="text-lg font-semibold text-white">Choose a Template</h2>
        <Button variant="ghost" size="sm" onClick={onClose}>
          ✕
        </Button>
      </div>

      {/* Template Browser */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <TemplatesBrowser
          onSelectTemplate={handleSelectTemplate}
          onViewTemplateDetails={(template) => {
            // Verbeter: geen alert, maar modal
            console.log('Template details:', template);
          }}
        />
      </div>

      {/* Instantiation Modal */}
      {selectedTemplate && (
        <InstantiationModal
          template={selectedTemplate}
          isOpen={isInstantiationModalOpen}
          onClose={() => setIsInstantiationModalOpen(false)}
          onSuccess={handleInstantiationSuccess}
        />
      )}
    </div>
  );
};
```

#### 2.3 Canvas Hydratie Na Template Instantiatie

**Bestand:** `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

```typescript
// Nieuwe callback voor template hydratie
const handleTemplateInstantiated = useCallback((templateData: {
  template_id: string;
  spec: any;
  workflow_name: string;
}) => {
  // Transform template spec naar workflow nodes/connections
  const { spec } = templateData;

  if (spec && spec.nodes && spec.connections) {
    // Bestaande store methods gebruiken
    const nodes = safeTransformNodes(spec.nodes);
    const connections = safeTransformEdges(spec.connections);

    // Set workflow in store
    setWorkflow({
      name: templateData.workflow_name,
      nodes,
      connections,
    });

    logger.debug('Canvas hydrated from template', {
      template_id: templateData.template_id,
      node_count: nodes.length
    }, 'FocusModeBuilderEnhanced');
  }
}, [setWorkflow]);

// In render:
{showTemplatesPanel && (
  <TemplatesPanel
    onClose={() => setShowTemplatesPanel(false)}
    onTemplateSelected={handleTemplateInstantiated}
  />
)}
```

#### 2.4 Delete Functionaliteit Toevoegen aan Focus Builder

**Bestand:** `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

```typescript
// State toevoegen
const [isDeleting, setIsDeleting] = useState(false);

// Delete handler toevoegen
const handleDelete = useCallback(async () => {
  if (!workflowId) return;

  if (!confirm('Are you sure you want to delete this workflow? This action cannot be undone.')) {
    return;
  }

  setIsDeleting(true);
  try {
    await focusBuilderApi.deleteWorkflow(workflowId);
    toast.success('Workflow deleted successfully');
    onExit?.();
  } catch (error) {
    logger.error('Failed to delete workflow', error, 'FocusModeBuilderEnhanced');
    toast.error('Failed to delete workflow');
  } finally {
    setIsDeleting(false);
  }
}, [workflowId, onExit]);

// In header render:
{workflowId && (
  <Button
    variant="outline"
    size="sm"
    onClick={handleDelete}
    disabled={isDeleting}
    className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
  >
    {isDeleting ? 'Deleting...' : 'Delete'}
  </Button>
)}
```

#### 2.5 Template Details Modal Verbeteren

**Bestand:** `frontend/src/components/templates/TemplatesBrowser.tsx`

```typescript
// Replace alert with proper modal
const handleViewTemplateDetails = (template: Template) => {
  // Open modal in plaats van alert
  setSelectedTemplateForDetails(template);
};

// In render:
{selectedTemplateForDetails && (
  <TemplateDetailsModal
    template={selectedTemplateForDetails}
    onClose={() => setSelectedTemplateForDetails(null)}
    onUse={() => {
      onSelectTemplate(selectedTemplateForDetails);
      setSelectedTemplateForDetails(null);
    }}
  />
)}
```

**Bestand:** `frontend/src/components/templates/TemplateDetailsModal.tsx` (NIEUW)

```typescript
import React from 'react';
import { Template } from '@/types/templates';
import { Button } from '@/components/ui/Button';
import { X } from 'lucide-react';

interface TemplateDetailsModalProps {
  template: Template;
  onClose: () => void;
  onUse: () => void;
}

export const TemplateDetailsModal: React.FC<TemplateDetailsModalProps> = ({
  template,
  onClose,
  onUse,
}) => {
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-700">
          <h2 className="text-2xl font-bold text-white">{template.name}</h2>
          <button onClick={onClose} className="text-white/60 hover:text-white">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <p className="text-white/80">{template.description}</p>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider">Category</h3>
              <p className="text-white">{template.category}</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider">Author</h3>
              <p className="text-white">{template.author || 'SanskritiSetu'}</p>
            </div>
          </div>

          {template.required_integrations && template.required_integrations.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-2">Required Integrations</h3>
              <div className="flex flex-wrap gap-2">
                {template.required_integrations.map((integration) => (
                  <span key={integration} className="px-3 py-1 bg-violet-500/20 text-violet-300 rounded-full text-sm">
                    {integration}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Preview */}
          <div>
            <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-2">Workflow Preview</h3>
            <div className="bg-slate-800 rounded-xl p-4 min-h-[200px]">
              {/* Hier kan een mini-canvas preview komen */}
              <p className="text-white/60 text-sm">
                {template.spec?.nodes?.length || 0} nodes, {template.spec?.connections?.length || 0} connections
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-slate-700">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={onUse}>Use This Template</Button>
        </div>
      </div>
    </div>
  );
};
```

#### 2.6 Start Options Panel Toevoegen

**Bestand:** `frontend/src/components/focus-builder/StartOptionsPanel.tsx` (NIEUW)

```typescript
import React from 'react';
import { FileText, Sparkles, Layers } from 'lucide-react';

interface StartOptionsPanelProps {
  onBlankWorkflow: () => void;
  onTemplate: () => void;
  onAIGenerate: () => void;
}

export const StartOptionsPanel: React.FC<StartOptionsPanelProps> = ({
  onBlankWorkflow,
  onTemplate,
  onAIGenerate,
}) => {
  return (
    <div className="h-full flex flex-col items-center justify-center p-8">
      <h2 className="text-3xl font-bold text-white mb-8">Start Building Your Workflow</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl w-full">
        {/* Option 1: Blank Workflow */}
        <button
          onClick={onBlankWorkflow}
          className="p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:bg-slate-800 hover:border-violet-500/50 transition-all group"
        >
          <FileText className="w-12 h-12 text-violet-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-semibold text-white mb-2">Blank Workflow</h3>
          <p className="text-white/60 text-sm">
            Start with a clean canvas and build your workflow from scratch.
          </p>
        </button>

        {/* Option 2: From Template */}
        <button
          onClick={onTemplate}
          className="p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:bg-slate-800 hover:border-violet-500/50 transition-all group"
        >
          <Layers className="w-12 h-12 text-amber-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-semibold text-white mb-2">From Template</h3>
          <p className="text-white/60 text-sm">
            Choose from pre-built workflows and customize them to your needs.
          </p>
        </button>

        {/* Option 3: AI Generate */}
        <button
          onClick={onAIGenerate}
          className="p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:bg-slate-800 hover:border-violet-500/50 transition-all group"
        >
          <Sparkles className="w-12 h-12 text-emerald-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-semibold text-white mb-2">AI Generate</h3>
          <p className="text-white/60 text-sm">
            Describe what you need and let AI build the workflow for you.
          </p>
        </button>
      </div>
    </div>
  );
};
```

**Integratie in FocusModeBuilderEnhanced:**

```typescript
// State
const [showStartOptions, setShowStartOptions] = useState(!workflowId && nodes.length === 0);

// Handlers
const handleBlankWorkflow = () => {
  setShowStartOptions(false);
  // Reset canvas
  setWorkflow({ name: 'New Workflow', nodes: [], connections: [] });
};

const handleTemplate = () => {
  setShowStartOptions(false);
  setShowTemplatesPanel(true);
};

const handleAIGenerate = () => {
  setShowStartOptions(false);
  setActiveTab('generate');
};

// In render:
{showStartOptions ? (
  <StartOptionsPanel
    onBlankWorkflow={handleBlankWorkflow}
    onTemplate={handleTemplate}
    onAIGenerate={handleAIGenerate}
  />
) : (
  // Bestaande canvas/chat UI
  <>
    <FocusCanvas />
    <FocusChatPanel />
  </>
)}
```

**Acceptatiecriteria:**

- [ ] TemplatesPanel werkt in focus-builder context
- [ ] Template instantiatie hydrateert canvas
- [ ] Delete workflow werkt in focus-builder
- [ ] Start options panel toont 3 keuzes
- [ ] Template details modal (geen alert)
- [ ] Mode param `?mode=templates` opent templates panel
- [ ] **Templates knop in sidebar wijst naar `/focus-builder?mode=templates`**
- [ ] **Mobile nav Templates knop wijst naar `/focus-builder?mode=templates`**

---

### **Fase 3: Redirects Implementeren (Week 4)**

**Doel:** Oude routes omleiden naar nieuwe locaties

#### 3.1 Update `App.tsx` Routes

**Bestand:** `frontend/src/App.tsx`

```typescript
// Huidige routes (regels ~175-185)
<Route path="/workflows" element={<ProtectedRoute><Workflows /></ProtectedRoute>} />
<Route path="/workflow-builder" element={<ProtectedRoute><WorkflowBuilderPage /></ProtectedRoute>} />
<Route path="/workflow-templates" element={<ProtectedRoute><WorkflowTemplatesPage /></ProtectedRoute>} />
<Route path="/focus-builder" element={<ProtectedRoute><FocusModeBuilderPage /></ProtectedRoute>} />
<Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />

// VERVANGEN DOOR:
<Route path="/workflows" element={<ProtectedRoute><Workflows /></ProtectedRoute>} />
<Route path="/focus-builder" element={<ProtectedRoute><FocusModeBuilderPage /></ProtectedRoute>} />

// Redirect routes
<Route path="/workflow-builder" element={<Navigate to="/focus-builder" replace />} />
<Route path="/workflow-templates" element={<Navigate to="/focus-builder?mode=templates" replace />} />
<Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
```

#### 3.2 Redirect Component Met Toast

**Bestand:** `frontend/src/App.tsx` (nieuwe component toevoegen)

```typescript
// Nieuw redirect component met toast notificatie
function WorkflowBuilderRedirect() {
  useEffect(() => {
    toast.success('Workflow Builder is now part of Focus Builder!', {
      duration: 4000,
      icon: '✨',
    });
  }, []);

  return <Navigate to="/focus-builder" replace />;
}

function TemplatesRedirect() {
  useEffect(() => {
    toast.info('Templates are now integrated in Focus Builder', {
      duration: 4000,
      icon: '🎨',
    });
  }, []);

  return <Navigate to="/focus-builder?mode=templates" replace />;
}

// In routes:
<Route path="/workflow-builder" element={<WorkflowBuilderRedirect />} />
<Route path="/workflow-templates" element={<TemplatesRedirect />} />
<Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
```

#### 3.3 Bookmark Compatibility

Voor gebruikers met bookmarks:

```typescript
// FocusModeBuilderPage.tsx
export default function FocusModeBuilderPage() {
  const searchParams = new URLSearchParams(window.location.search);
  const workflowId = searchParams.get('id') || undefined;
  const initialPrompt = searchParams.get('prompt') || undefined;
  const mode = searchParams.get('mode') || undefined;

  // Legacy param support
  const legacyTemplateId = searchParams.get('templateId'); // Oude workflow-builder param

  useEffect(() => {
    if (legacyTemplateId) {
      // Redirect naar nieuwe mode met template geselecteerd
      toast.info('Opening template in new builder...', { duration: 2000 });
    }
  }, [legacyTemplateId]);

  // ... rest
}
```

**Acceptatiecriteria:**

- [ ] `/workflow-builder` redirect naar `/focus-builder`
- [ ] `/workflow-templates` redirect naar `/focus-builder?mode=templates`
- [ ] `/templates` **BLIJFT BESTAAN ALS ALIAS** (geen harde redirect in Fase 3!)
- [ ] Toast notificaties tonen bij redirect
- [ ] Bestaande bookmarks werken nog steeds

**LET OP:** `/templates` krijgt in Fase 3 **geen** harde redirect. Deze route blijft bestaan als zachte alias tot Fase 5, na expliciete parity-signoff.

---

### **Fase 4: Cleanup en Validatie (Week 5-6)**

**Doel:** Code cleanup, regressietests, documentatie

#### 4.1 Code Cleanup

**Te archiveren bestanden (verplaatsen naar `frontend/src/archive/`):**

1. `frontend/src/pages/WorkflowBuilderPage.tsx` → archive (Fase 4, na parity-signoff)
2. `frontend/src/pages/workflow/WorkflowTemplatesPage.tsx` → archive (Fase 4, na parity-signoff)
3. `frontend/src/pages/templates/TemplatesPage.tsx` → **NIET archiveren in Fase 4** (blijft als alias wrapper tot Fase 5)
4. `frontend/src/components/workflow/SOPFlowEditor.tsx` → archive (Fase 4)
5. `frontend/src/components/workflow/TemplateSidebar.tsx` → archive (Fase 4)

**Let op:** Archiveer pas na bevestiging van functionele pariteit!

**TemplatesPage.tsx alias-strategie:**

```typescript
// frontend/src/pages/templates/TemplatesPage.tsx
// Fase 1-4: bestaat als wrapper die doorverwijst naar focus-builder
export const TemplatesPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Zachte redirect met toast
    toast.info('Templates zijn nu geïntegreerd in Focus Builder', {
      duration: 3000,
      icon: '🎨',
    });
    navigate('/focus-builder?mode=templates', { replace: true });
  }, [navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-white/80">Templates openen in Focus Builder...</p>
      </div>
    </div>
  );
};

// Fase 5: kan worden verwijderd na parity-signoff en redirect naar <Navigate>
```

#### 4.2 Testplan

**Unit Tests:**

```typescript
// frontend/src/pages/__tests__/Workflows.test.tsx
describe('Workflows Page', () => {
  it('navigates to /focus-builder when creating new workflow', async () => {
    render(<Workflows />);
    const newButton = screen.getByText('New Workflow');
    await userEvent.click(newButton);
    expect(window.location.pathname).toBe('/focus-builder');
  });

  it('navigates to /focus-builder?id= when editing workflow', async () => {
    render(<Workflows />);
    const workflowCard = screen.getByTestId('workflow-card-1');
    await userEvent.click(workflowCard);
    expect(window.location.pathname).toBe('/focus-builder');
    expect(window.location.search).toContain('id=');
  });
});

// frontend/src/pages/__tests__/FocusModeBuilderPage.test.tsx
describe('FocusModeBuilderPage', () => {
  it('opens templates panel when mode=templates', async () => {
    window.history.pushState({}, '', '/focus-builder?mode=templates');
    render(<FocusModeBuilderPage />);
    await waitFor(() => {
      expect(screen.getByText('Choose a Template')).toBeInTheDocument();
    });
  });

  it('shows start options when no workflowId and empty nodes', () => {
    render(<FocusModeBuilderPage />);
    expect(screen.getByText('Start Building Your Workflow')).toBeInTheDocument();
  });
});
```

**Integration Tests:**

```typescript
// frontend/src/__tests__/integration/workflow-consolidation.test.tsx
describe('Workflow Route Consolidation', () => {
  it('redirects /workflow-builder to /focus-builder', async () => {
    window.history.pushState({}, '', '/workflow-builder');
    render(<App />);
    await waitFor(() => {
      expect(window.location.pathname).toBe('/focus-builder');
    });
  });

  it('aliases /templates to /focus-builder?mode=templates', async () => {
    window.history.pushState({}, '', '/templates');
    render(<App />);
    await waitFor(() => {
      expect(window.location.pathname).toBe('/focus-builder');
      expect(window.location.search).toBe('?mode=templates');
    });
  });

  it('preserves workflowId when redirecting edit link', async () => {
    window.history.pushState({}, '', '/workflow-builder?id=123');
    render(<App />);
    await waitFor(() => {
      expect(window.location.pathname).toBe('/focus-builder');
      expect(window.location.search).toContain('id=123');
    });
  });
});
```

**E2E Tests (Playwright):**

```typescript
// frontend/tests/e2e/workflow-consolidation.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Workflow Route Consolidation', () => {
  test('should redirect workflow-builder to focus-builder', async ({ page }) => {
    await page.goto('/workflow-builder');
    await expect(page).toHaveURL(/.*\/focus-builder/);
    await expect(page.getByText('Focus Builder')).toBeVisible();
  });

  test('should open templates alias in focus-builder with mode=templates', async ({ page }) => {
    await page.goto('/templates');
    await expect(page).toHaveURL(/.*\/focus-builder\?mode=templates/);
    await expect(page.getByText('Choose a Template')).toBeVisible();
  });

  test('should create workflow from templates panel', async ({ page }) => {
    await page.goto('/focus-builder?mode=templates');

    // Select template
    const templateCard = page.getByTestId('template-card').first();
    await templateCard.click();

    // Fill instantiation form
    await page.fill('input[name="workflow_name"]', 'My Template Workflow');
    await page.click('button:has-text("Instantiate")');

    // Verify canvas hydrated
    await expect(page.getByTestId('workflow-canvas')).toBeVisible();
  });

  test('should delete workflow from focus-builder', async ({ page }) => {
    // Create workflow first
    await page.goto('/focus-builder');
    // ... create workflow steps ...

    // Delete workflow
    await page.click('button:has-text("Delete")');
    await page.click('button:has-text("Confirm")');

    // Verify redirected to workflows list
    await expect(page).toHaveURL(/.*\/workflows/);
  });
});
```

#### 4.3 Performance Validatie

**Te controleren metrics:**

1. **Load time Focus Builder:**
   - Target: < 2s initial load
   - Lazy loading voor TemplatesPanel
   - Code splitting voor start options

2. **Template API response:**
   - Target: < 500ms
   - Cache via React Query
   - Fallback naar JSON bij fout

3. **Canvas render performance:**
   - Target: 60fps bij 50+ nodes
   - Memoization van node renders
   - Virtual scrolling voor grote workflows

#### 4.4 Documentatie Update

**Te updaten documenten:**

1. `AGENTS.md` — Route structuur updaten
2. `frontend/README.md` — Navigatie documentatie
3. `docs/user-guides/workflows.md` — User guide herschrijven
4. `CHANGELOG.md` — Deprecatie notitie toevoegen

**Voorbeeld CHANGELOG entry:**

```markdown
## [Version X.X.X] - 2026-03-25

### Changed
- **Workflow Routes Consolidated**: Consolidated 5 workflow-related routes into 2 canonical routes
  - `/workflows` remains unchanged (workflow management hub)
  - `/focus-builder` is now the primary creation hub (was: AI-only)
  - `/workflow-builder` → redirected to `/focus-builder`
  - `/workflow-templates` → redirected to `/focus-builder?mode=templates`
  - `/templates` → tijdelijk alias naar `/focus-builder?mode=templates`

### Added
- Templates panel integrated in Focus Builder
- Start options panel (Blank/Template/AI)
- Template instantiation with canvas hydration
- Delete workflow functionality in Focus Builder

### Deprecated
- `/workflow-builder` route (use `/focus-builder`)
- `/workflow-templates` route (use `/focus-builder?mode=templates`)
- `/templates` as zelfstandige product-ingang (behouden als tijdelijke alias)

### Removed
- Template sidebar from workflow builder
- Standalone template browser page (now integrated)
```

**Acceptatiecriteria:**

- [ ] Alle tests slagen (unit, integration, E2E)
- [ ] Performance metrics binnen targets
- [ ] Documentatie geüpdatet
- [ ] CHANGELOG entry toegevoegd
- [ ] Oude gearchiveerde bestanden verplaatst

---

### **Fase 5: Templates Alias Verwijderen (Week 7-8, Optioneel)**

**Doel:** `/templates` route verwijderen na bevestigde succesvolle adoptie

**VEREISTEN VÓÓR DEZE FASE:**

- [ ] Alle Fase 2-4 checkboxes ✅
- [ ] Template usage in `/focus-builder?mode=templates` > 80% van totale template usage
- [ ] Directe `/templates` URL traffic < 10% van totale template traffic
- [ ] Geen kritieke bugs gemeld rond template discovery
- [ ] Product Owner expliciete goedkeuring

**Acties:**

1. **Update `App.tsx` — harde redirect**

```typescript
// VERVANG zachte redirect door harde Navigate
<Route path="/templates" element={<Navigate to="/focus-builder?mode=templates" replace />} />
```

1. **Verwijder `TemplatesPage.tsx` wrapper**

```bash
# Verplaats naar archive
mv frontend/src/pages/templates/TemplatesPage.tsx frontend/src/archive/
```

1. **Update navigatie — verwijder "Templates" knop**

```typescript
// Sidebar.tsx — verwijder Templates item
const navItems = [
  // ... andere items
  // Templates item VERWIJDERD (na Week 8)
];

// Layout.tsx — verwijder Templates item
const navigation = [
  // ... andere items
  // Templates item VERWIJDERD (na Week 8)
];
```

1. **Update documentatie**

- CHANGELOG: noteer verwijdering `/templates` route
- User guides: update screenshots en instructies
- Interne docs: update route-overzicht

**Acceptatiecriteria Fase 5:**

- [ ] `/templates` URL redirect naar `/focus-builder?mode=templates`
- [ ] `TemplatesPage.tsx` gearchiveerd
- [ ] "Templates" navigatieknoppen verwijderd uit sidebar en mobile nav
- [ ] Template discovery rate niet gedaald (> 95% van baseline)
- [ ] Geen toename in support tickets rond template vinden
- [ ] Product Owner heeft finale goedkeuring gegeven

**LET OP:** Deze fase is **optioneel**. Als de alias-strategie goed werkt en geen verwarring veroorzaakt, kan `/templates` maanden blijven bestaan als zachte redirect. Er is geen haast bij verwijdering.

---

## 6. Risico's en Mitigatie

### 5.1 Functionele Regressie

**Risico:** Functionaliteit gaat verloren tijdens migratie

**Mitigatie:**

1. Parity matrix voor elke capability
2. Test coverage > 90% op nieuwe componenten
3. Feature flag voor templates panel
4. Gradual rollout (eerst interne users)

### 5.2 Gebruikersverwarring

**Risico:** Bestaande gebruikers weten niet waar features zijn

**Mitigatie:**

1. Duidelijke deprecation banners (4 weken)
2. Toast notificaties bij redirects
3. Help documentation updaten
4. Onboarding tour voor nieuwe UI

### 5.3 Performance Issues

**Risico:** Focus Builder wordt te zwaar met alle features

**Mitigatie:**

1. Lazy loading voor TemplatesPanel
2. Code splitting per mode
3. React Query caching voor templates
4. Performance budget: < 2s load time

### 5.4 SEO/Bookmark Impact

**Risico:** Bookmarks en deep links werken niet meer

**Mitigatie:**

1. Redirects met `replace` voor SEO
2. Query params behouden waar mogelijk
3. 301 redirects voor externe links
4. Sitemap updaten

### 5.5 Template Source of Truth Drift

**Risico:** Frontend fallback JSON en backend/API leveren verschillende templatewerkelijkheden op.

**Mitigatie:**

1. Expliciet vastleggen dat productiegedrag API-first en DB-backed is
2. Frontend JSON alleen als development fallback toestaan
3. Verschillen tussen API-respons en fallback detecteren in tests of telemetry

### 5.6 RBAC en Tenant-isolatie bij Deep Links

**Risico:** Directe URL's zoals `/focus-builder?id=...` of aliasgedrag openen workflows buiten tenant- of permissiegrenzen.

**Mitigatie:**

1. Autorisatie en tenant-checks expliciet testen op edit-routes
2. Redirects en aliases nooit permissiechecks laten omzeilen
3. Negatieve tests toevoegen voor unauthorized en cross-tenant toegang

### 5.7 State/Store Migratie Regressies

**Risico:** Legacy builder en focus-builder gebruiken andere statepatronen, waardoor edit- of save-gedrag ongemerkt kan breken.

**Mitigatie:**

1. Aparte technische migratietaak voor statecontracten
2. Regressietests voor create, edit, save, execute en delete
3. Query-param contract expliciet documenteren en testen

### 5.8 Test-debt Maskeert Nieuwe Regressies

**Risico:** Bestaande testinstabiliteit verbergt regressies in de consolidatie.

**Mitigatie:**

1. Kleine gerichte consolidatie-testset onderhouden
2. Routeconsolidatie niet afhankelijk maken van brede suite-instabiliteit
3. Go/no-go baseren op gerichte kritieke flows, niet alleen op totale suite-status

### 5.9 Support, Onboarding en Interne Documentatie

**Risico:** Oude routes blijven leven in handleidingen, support-antwoorden, bookmarks en trainingen.

**Mitigatie:**

1. Supportscripts en onboardingmateriaal tegelijk updaten met Fase 3/Fase 5
2. Redirect- of aliasgedrag opnemen in helpteksten
3. Analytics gebruiken om te bepalen wanneer oude verwijzingen echt verdwijnen

---

## 7. Success Metrics

### 6.1 UX Metrics

| Metric | Before | Target | How to Measure |
| -------- | -------- | -------- | ---------------- |
| Time to create workflow | 4.2 min | 2.5 min | Analytics events |
| Template usage rate | 23% | 45% | Template instantiation events |
| User confusion (support tickets) | 12/maand | < 3/maand | Support ticket tagging |
| Navigation errors | 8% | < 2% | Frontend error tracking |

### 6.2 Technical Metrics

| Metric | Before | Target | How to Measure |
| -------- | -------- | -------- | ---------------- |
| Route count (workflow) | 5 | 2 | Route config audit |
| Code duplication | 34% | < 5% | Code climate analysis |
| Bundle size (workflow) | 234 KB | < 180 KB | Webpack bundle analyzer |
| Test coverage | 67% | > 90% | Coverage report |

### 6.3 Adoption Metrics

| Metric | Target | Timeline |
| -------- | -------- | ---------- |
| Users on new flow | 80% | Week 4 |
| Old route direct traffic | < 5% | Week 6 |
| Template usage increase | +50% | Week 8 |
| Support tickets workflow | -75% | Week 6 |

---

## 8. Rollout Strategie

### 7.1 Fase 1: Internal Testing (Week 1-2)

**Doelgroep:** Development team, interne testers

**Acties:**

- Navigatie updaten
- Deprecation banners tonen
- Feedback verzamelen
- Bugs fixen

**Success criteria:**

- Alle interne testers kunnen workflows maken
- Geen kritieke bugs
- Positieve feedback op UX

### 7.2 Fase 2: Beta Release (Week 3-4)

**Doelgroep:** 10% van productie users

**Acties:**

- Feature flag enabled voor beta cohort
- Redirects actief maar met "terug" optie
- Analytics closely monitoren
- Support team briefen

**Success criteria:**

- < 5% error rate
- Positieve user feedback (> 4/5)
- Geen performance degradatie

### 7.3 Fase 3: General Availability (Week 5-6)

**Doelgroep:** Alle users

**Acties:**

- Redirects hard enabled
- Oude code archiveren
- Documentatie publiceren
- Support team trainen

**Success criteria:**

- 80% adoptie in eerste week
- Support tickets < baseline
- Performance binnen budget

### 7.4 Fase 4: Cleanup en Validatie (Week 5-6)

**Doelgroep:** Alle users, QA team

**Acties:**

- Code archiveren (behalve TemplatesPage.tsx)
- Feature flags voor consolidatie activeren
- Final metrics rapporteren
- Lessons learned documenteren
- Parity signoff formeel vastleggen

### 7.5 Fase 5: Templates Alias Verwijderen (Week 7-8, Optioneel)

**Doelgroep:** Product Owner, UX Lead

**Go/No-Go Criteria:**

- Template usage in focus-builder > 80% van baseline
- Directe `/templates` URL traffic < 10%
- Geen kritieke bugs
- PO goedkeuring

**Acties:**

- Harde redirect voor `/templates` activeren
- TemplatesPage.tsx archiveren
- "Templates" navigatieknoppen verwijderen
- Discovery rate monitoren (mag niet dalen)

**BELANGRIJK:** Deze fase is optioneel. Als de alias-strategie goed werkt, kan `/templates` maanden blijven bestaan zonder problemen.

---

## 9. Technische Specificaties

### 8.1 Query Params Specificatie

```typescript
// /focus-builder query parameters
interface FocusBuilderQueryParams {
  /** Workflow ID voor bestaande workflow edit */
  id?: string;

  /** Initial prompt voor AI generatie */
  prompt?: string;

  /** Start mode */
  mode?: 'scratch' | 'templates' | 'ai';

  /** Template ID voor directe selectie (legacy support) */
  templateId?: string;
}
```

### 8.2 Event Tracking

```typescript
// Analytics events voor consolidatie
interface WorkflowAnalyticsEvents {
  // Navigation
  'workflow_navigation': {
    from: '/workflows' | '/workflow-builder' | '/templates' | '/workflow-templates';
    to: '/focus-builder' | '/workflows';
    action: 'create' | 'edit' | 'browse_templates' | 'redirect';
  };

  // Template usage
  'template_selected': {
    template_id: string;
    category: string;
    mode: 'focus_builder' | 'legacy_templates';
  };

  'template_instantiated': {
    template_id: string;
    workflow_name: string;
    duration_ms: number;
  };

  // Workflow creation
  'workflow_creation_started': {
    method: 'blank' | 'template' | 'ai';
    workflow_id?: string;
  };

  'workflow_creation_completed': {
    workflow_id: string;
    method: 'blank' | 'template' | 'ai';
    node_count: number;
    duration_ms: number;
  };
}
```

### 8.3 Feature Flag Config

```python
# src/core/shared/config.py

class Settings(BaseSettings):
    # ... andere config

    # Workflow route consolidatie
    feature_workflow_consolidation: bool = Field(
        default=True,
        description="Enable consolidated workflow routes (2-route model)"
    )

    feature_focus_builder_templates: bool = Field(
        default=True,
        description="Enable templates panel in Focus Builder"
    )

    # Deprecation flags
    deprecate_workflow_builder: bool = Field(
        default=True,
        description="Deprecate /workflow-builder route"
    )

    deprecate_workflow_templates: bool = Field(
        default=True,
        description="Deprecate /workflow-templates route"
    )

    deprecate_templates: bool = Field(
        default=True,
        description="Deprecate /templates route"
    )
```

---

## 10. Belangrijke Bestanden

### 9.1 Frontend Componenten

**Te wijzigen:**

- `frontend/src/App.tsx` — Routes en redirects
- `frontend/src/pages/FocusModeBuilderPage.tsx` — Mode support
- `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx` — Templates panel integratie
- `frontend/src/components/layout/Sidebar.tsx` — Navigatie items
- `frontend/src/components/layout/Layout.tsx` — Navigatie items
- `frontend/src/components/layout/MobileNav.tsx` — Mobile navigatie

**Alleen verifiëren, geen functionele wijziging verwacht:**

- `frontend/src/pages/Workflows.tsx` — Create/edit routes wijzen al naar `/focus-builder`

**Nieuw:**

- `frontend/src/components/focus-builder/TemplatesPanel.tsx`
- `frontend/src/components/focus-builder/StartOptionsPanel.tsx`
- `frontend/src/components/templates/TemplateDetailsModal.tsx`

**Te archiveren:**

- `frontend/src/pages/WorkflowBuilderPage.tsx`
- `frontend/src/pages/workflow/WorkflowTemplatesPage.tsx`
- `frontend/src/pages/templates/TemplatesPage.tsx` (optioneel)
- `frontend/src/components/workflow/SOPFlowEditor.tsx`
- `frontend/src/components/workflow/TemplateSidebar.tsx`

### 9.2 Backend Routes

**Geen wijzigingen nodig:**

- `/api/v1/workflow-templates` — Blijft ongewijzigd
- `/api/v1/focus-builder/*` — Blijft ongewijzigd
- `/api/v1/workflows/*` — Blijft ongewijzigd

### 9.3 Tests

**Nieuwe tests:**

- `frontend/src/pages/__tests__/Workflows.test.tsx` — Navigatie tests
- `frontend/src/pages/__tests__/FocusModeBuilderPage.test.tsx` — Mode tests
- `frontend/src/__tests__/integration/workflow-consolidation.test.tsx` — Integratie tests
- `frontend/tests/e2e/workflow-consolidation.spec.ts` — E2E tests

**Te updaten:**

- Bestaande workflow tests die verwijzen naar oude routes

---

## 11. Uitvoerbare Takenlijst per Bestand

Deze lijst vertaalt het plan naar direct uitvoerbare werkitems, gegroepeerd per bestand. De bedoeling is dat een engineer of subagent hiermee meteen kan starten zonder opnieuw het hele document te moeten ontleden.

### 11.1 Routing en app entrypoints

#### `frontend/src/App.tsx`

- [ ] Fase 3: vervang legacy route-rendering voor `/workflow-builder` door redirect naar `/focus-builder`
- [ ] Fase 3: vervang legacy route-rendering voor `/workflow-templates` door redirect naar `/focus-builder?mode=templates`
- [ ] Fase 3: behoud `/templates` als alias via `TemplatesPage` wrapper
- [ ] Fase 5: zet `/templates` om naar harde redirect als go/no-go criteria gehaald zijn
- [ ] Voeg of behoud redirect/toast-gedrag waar gewenst

#### `frontend/src/pages/FocusModeBuilderPage.tsx`

- [ ] Voeg support toe voor `mode` query parameter
- [ ] Ondersteun legacy query params zoals `templateId` waar nodig
- [ ] Zorg dat `id`, `prompt` en `mode` samen correct worden doorgegeven aan de builder

#### `frontend/src/pages/templates/TemplatesPage.tsx`

- [ ] Fase 1-4: maak of behoud alias-wrapper die doorstuurt naar `/focus-builder?mode=templates`
- [ ] Toon tijdelijke redirect/toast-ervaring zonder harde breuk
- [ ] Fase 5: archiveer of verwijder bestand als alias wordt uitgefaseerd

### 11.2 Navigatie

#### `frontend/src/components/layout/Sidebar.tsx`

- [ ] Zet `Workflows` om naar `/workflows`
- [ ] Voeg `Create Workflow` toe met route `/focus-builder`
- [ ] Laat `Templates` wijzen naar `/focus-builder?mode=templates`
- [ ] Fase 5: verwijder `Templates` alleen als alias-removal expliciet is goedgekeurd

#### `frontend/src/components/Layout.tsx`

- [ ] Breng desktop-navigatie in lijn met de canonieke routes
- [ ] Voeg `Create Workflow` toe als aparte entry indien deze navigatie actief wordt gebruikt
- [ ] Zorg dat eventuele templates-ingang naar `mode=templates` wijst

#### `frontend/src/components/layout/MobileNav.tsx`

- [ ] Zet mobiele workflow-ingangen gelijk aan desktopnavigatie
- [ ] Verifieer dat `Templates` zichtbaar en bruikbaar blijft in Fase 1-4
- [ ] Fase 5: verwijder templates-ingang alleen na adoptiebevestiging

### 11.3 Builderfunctionaliteit

#### `frontend/src/components/workflow/FocusModeBuilderEnhanced.tsx`

- [ ] Voeg `mode`-ondersteuning toe (`scratch`, `templates`, `ai`)
- [ ] Voeg state toe voor templates panel en startopties
- [ ] Hydrateer canvas vanuit template-instantiatie-response
- [ ] Voeg delete-functionaliteit toe voor bestaande workflows
- [ ] Zorg dat save, update, execute en delete in dezelfde flow blijven werken

#### `frontend/src/components/focus-builder/TemplatesPanel.tsx`

- [ ] Nieuw component aanmaken
- [ ] `TemplatesBrowser` integreren
- [ ] `InstantiationModal` koppelen
- [ ] Callback leveren voor canvas-hydratie in de parent builder

#### `frontend/src/components/focus-builder/StartOptionsPanel.tsx`

- [ ] Nieuw component aanmaken
- [ ] Drie startopties tonen: blank, template, AI
- [ ] Builder-state correct omschakelen per keuze

#### `frontend/src/components/templates/TemplatesBrowser.tsx`

- [ ] Verwijder `alert()`-achtig detailgedrag
- [ ] Koppel template details aan een echte modal
- [ ] Verifieer search, category filters en selectiestroom in buildercontext

#### `frontend/src/components/templates/InstantiationModal.tsx`

- [ ] Verifieer dat response alle data levert voor workflow-hydratie
- [ ] Maak responsecontract expliciet richting builder

#### `frontend/src/components/templates/TemplateDetailsModal.tsx`

- [ ] Nieuw component aanmaken
- [ ] Toon description, category, integrations en preview
- [ ] Voeg CTA toe om template direct te gebruiken

### 11.4 Legacy componenten en archivering

#### `frontend/src/pages/WorkflowBuilderPage.tsx`

- [ ] Fase 1: voeg deprecation banner toe
- [ ] Fase 4: archiveer bestand na parity-signoff

#### `frontend/src/pages/workflow/WorkflowTemplatesPage.tsx`

- [ ] Fase 1: voeg deprecation banner toe
- [ ] Fase 4: archiveer bestand na parity-signoff

#### `frontend/src/components/workflow/SOPFlowEditor.tsx`

- [ ] Bevestig dat er geen actieve afhankelijkheden meer zijn
- [ ] Archiveer in Fase 4 als focus-builder parity heeft

#### `frontend/src/components/workflow/TemplateSidebar.tsx`

- [ ] Bevestig dat template-keuze volledig naar templates panel is gemigreerd
- [ ] Archiveer in Fase 4

### 11.5 Tests en kwaliteitscontrole

#### `frontend/src/pages/__tests__/Workflows.test.tsx`

- [ ] Voeg navigatietests toe voor create en edit naar `/focus-builder`

#### `frontend/src/pages/__tests__/FocusModeBuilderPage.test.tsx`

- [ ] Voeg tests toe voor `mode=templates`
- [ ] Voeg tests toe voor startopties zonder bestaande workflow

#### `frontend/src/__tests__/integration/workflow-consolidation.test.tsx`

- [ ] Voeg redirect- en alias-tests toe voor oude routes
- [ ] Verifieer query-param behoud bij redirects

#### `frontend/tests/e2e/workflow-consolidation.spec.ts`

- [ ] Voeg E2E-flow toe voor oude route naar nieuwe builder
- [ ] Voeg template browse en instantiation flow toe
- [ ] Voeg delete-flow toe vanuit focus-builder

### 11.6 Documentatie en governance

#### `AGENTS.md`

- [ ] Werk route-overzicht bij naar twee canonieke workflowroutes

#### `frontend/README.md`

- [ ] Werk navigatie- en builderdocumentatie bij

#### `docs/user-guides/workflows.md`

- [ ] Herschrijf gebruikersinstructies op basis van `/workflows` en `/focus-builder`

#### `CHANGELOG.md`

- [ ] Voeg wijziging toe voor consolidatie, redirects en tijdelijke alias-strategie

## 12. Conclusie

Deze consolidatie reduceert de workflow-route complexiteit van 5 naar 2 routes, terwijl alle functionaliteit behouden blijft. De belangrijkste voordelen zijn:

1. **Duidelijke UX:** 2 mentale modellen (beheren vs. creëren)
2. **Minder duplicatie:** Template logica op 1 plek
3. **Betere governance:** 1 pad voor audit en logging
4. **Eenvoudiger onderhoud:** Minder code, minder bugs

**Next Steps:**

1. Dit plan reviewen met team
2. Fase 1 direct starten (navigatie updaten)
3. Wekelijkse check-ins op voortgang
4. Metrics dashboard inrichten

---

**Auteur:** AI Assistant
**Reviewers:** [Nog in te vullen]
**Goedgekeurd door:** [Nog in te vullen]
**Doelimplementatie:** Q2 2026

---

## 13. Version History

- **0.1** — 25 maart 2026 — AI Assistant
  - Eerste concept
- **0.9** — 25 maart 2026 — AI Assistant + User Feedback
  - Critical sharpening
  - Architectuurprincipes toegevoegd (Owner of Truth regels)
  - Alias-strategie voor `/templates` toegevoegd (niet te vroeg verwijderen)
  - Parity Signoff Checklist toegevoegd (vereist vóór Fase 3)
  - Workflows.tsx-correctie toegevoegd (gebruikt al `/focus-builder`)
  - Sidebar-aanpassing verduidelijkt: Templates knop blijft bestaan en wijst naar mode
  - Fase 5 toegevoegd voor optionele alias removal
  - Quick Reference tabel toegevoegd
  - Navigatie-acceptatiecriteria aangescherpt
- **1.0** — Nog in te vullen — Team
  - Beoogde final versie na review
  - Team feedback verwerkt
  - Alle onduidelijkheden weggenomen
  - Klaar voor implementatie

### Belangrijke Wijzigingen in v0.9 (Critical Sharpening)

**Toegevoegd op verzoek van reviewer:**

1. **Architectuurprincipes sectie** — Owner of Truth regels expliciet gemaakt
2. **Alias-strategie** — `/templates` niet te vroeg verwijderen, eerst UX bewijzen
3. **Parity Signoff Checklist** — Harde gate vóór Fase 3 redirects
4. **Workflows.tsx correctie** — Documentatie aangepast aan bestaande code (gebruikt al `/focus-builder`)
5. **Sidebar navigatie** — Templates knop blijft bestaan, wijst naar `/focus-builder?mode=templates`
6. **Fase 5** — Optionele fase voor alias removal na data-gedreven beslissing
7. **Quick Reference** — Executive summary voor snelle context

**Waarom deze wijzigingen cruciaal zijn:**

- Voorkomt feature regression door expliciete parity gates
- Voorkomt gebruikersverwarring door templates te vroeg te verwijderen
- Corrigeert onnauwkeurigheden over bestaande implementatie
- Maakt alias-strategie expliciet voor betere adoptie
- Geeft team snelle context via Quick Reference tabel

---

**Document Status:** v0.9 — Ready for review, implementatie kan starten na expliciete goedkeuring
