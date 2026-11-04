# BE-AGT-065: Annex III Classificatie (OP-144) & ALWAYS_HITL_ACTIONS Activering (OP-164)

Feature ID:       BE-AGT-065
Sprint:           Beleids- en Governance-Sluiting
Domein:           governance / als / council
ADR:              ADR-031, ADR-036, ADR-015
Auteur:           Rakesh (solo developer) & Antigravity
Datum:            2026-08-25
Status:           ACCEPTED (Groen op alle gates)

---

## 1. Context en Doel

Dit document legt de definitieve beleidsmatige sluiting vast van:
1. **OP-144**: Alle resterende 11 HR-gerelateerde manifesten (plus shiftplanner.yml) expliciet classificeren conform de **EU AI Act Bijlage III punt 4 (Werkgelegenheid en werknemersbeheer)** en AVG art. 5 (data-minimalisatie).
2. **OP-164**: Het activeren en vullen van ALWAYS_HITL_ACTIONS in src/core/copilot/council/coordinator.py met de 7 onomkeerbare hoog-risico acties conform **AVG / GDPR art. 22** en **AI Act art. 14**.

---

## 2. Technische Implementatie

### A. OP-144: Manifest-Classificatie en Data-Sanering
In src/core/als/agents/skills/manifests/:
- **7 High-Risk Agents naar nnex_iii en hitl**:
  - skillpathfinder.yml (Loopbaanpaden & promotie-advies)
  - urnoutcoach.yml (Werkdruk- en verzuimrisicomonitoring)
  - emotionalmirror.yml (Emotie- en sentimentsanalyse van medewerkers)
  - leavemanager.yml (Verlof- en afwezigheidstoekenning)
  - 
egotiationcoach.yml (Arbeidsvoorwaarden- en salarisadvisering)
  - ocusguardian.yml (Productiviteits- en werkgedragsmonitoring)
  - shiftplanner.yml (Personeelsrooster- en ploegendiensttoewijzing)
- **4 Low-Risk Agents naar 
one en hotl + Tool-Sanering**:
  - reakreminder.yml, digitaldetox.yml, meetingnotes.yml, knowledgecurator.yml
  - Verwijdering van query_hr_database uit hun llowed_tools zodat deze ondersteunende agents geen onnodige toegang hebben tot personeelsdossiers.
- **Architectuur Guard**:
  - KNOWN_UNDECLARED in 	ests/architecture/test_hr_agents_declare_their_annex_iii_classification.py is leeg ({}).

### B. OP-164: Vullen van ALWAYS_HITL_ACTIONS
In src/core/copilot/council/coordinator.py:
- 7 onomkeerbare hoog-risico acties geconfigureerd (	erminate_employee, hire_candidate, djust_compensation, disciplinary_action, sign_external_contract, execute_high_value_payout, delete_tenant_data).
- Elk van deze acties triggert via deliberate() automatisch een upgrade van APPROVED en MODIFIED naar HITL_REQUIRED.
- Alle 5 aanroeppaden maken gegarandeerd een ticket aan (afgerond in OP-167/168).

---

## 3. Verificatie en Bewijs

1. 	ests/architecture/test_hr_agents_declare_their_annex_iii_classification.py (3 passed).
2. 	ests/unit/copilot/council/test_coordinator.py (42 passed, inclusief 7 geparametriseerde live tests voor ALWAYS_HITL_ACTIONS).
3. Mypy: 0 fouten over 2.308 bestanden.
4. Pyright: 0 fouten.
