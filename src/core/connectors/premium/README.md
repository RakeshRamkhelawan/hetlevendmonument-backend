# Premium Connectors (Betaalde Integraties)

Deze connectoren hebben **externe kosten** en zijn daarom niet inbegrepen in de standaard abonnementen. Ze worden aangeboden als **Premium Add-ons**.

## Kostenoverzicht per Connector

### 1. Mollie (Betalingen)
**Kostenmodel:** Per transactie (pay-as-you-go), geen vaste kosten
- iDEAL: €0,29 per transactie
- Creditcards (EEA): 1,8% + €0,25 per transactie
- Creditcards (non-EEA): 2,9% + €0,25 per transactie
- SEPA Direct Debit: €0,25 per transactie
- Refund fee: €0,25 per terugboeking

**Wanneer te gebruiken:** Echte betalingen in productie (demo's gebruiken gesimuleerde betalingen)

---

### 2. KVK API (Handelsregister)
**Kostenmodel:** Hybride (vast + per gebruik)
- Vaste kosten: €6,40 per maand (API key)
- Gebruik: €0,02 per bevraging
- Voorbeeld: 1000 opvragingen/maand = €6,40 + €20 = €26,40/maand

**Wanneer te gebruiken:** Auto-offerte generatie, compliance checks, klantverificatie

---

### 3. Belastingdienst Digipoort (BTW-aangifte)
**Kostenmodel:** Via middleware partner (Bokkz.nl)
- Bokkz.nl kosten: ~€19,50 per maand voor BTW module
- Alternatief: Fiscaal-Online (vergelijkbare kosten)
- Directe Digipoort koppeling: €0 (maar zeer complex, 4-6 weken implementatie)

**Wanneer te gebruiken:** Automatische BTW-aangifte, compliance automation

---

### 4. IBAN-naam Check (Betaalvereniging NL)
**Kostenmodel:** Partnerschap Currence vereist
- Setup: Partnerschap aanvragen (eenmalig)
- Per check: Geschat €0,05-€0,15 (afhankelijk van volume)

**Wanneer te gebruiken:** Fraudepreventie bij uitbetalingen, automatische incasso's

---

### 5. Exact Online (Boekhouding)
**Kostenmodel:** Licentie afhankelijk
- Exact Online licentie vereist (vanaf ~€30/maand)
- API toegang: Inbegrepen bij meeste abonnementen

**Wanneer te gebruiken:** MKB+ met bestaande Exact omgeving

---

### 6. AFAS (HR/Payroll)
**Kostenmodel:** Licentie afhankelijk
- AFAS licentie vereist (3,4M NL loonstroken via AFAS)
- API toegang: Inbegrepen bij Pro licenties

**Wanneer te gebruiken:** Werkgevers met AFAS payroll

---

### 7. PostNL (Logistiek)
**Kostenmodel:** Abonnement + per zending
- API toegang: Gratis met PostNL account
- Zendingen: €4,50-€7,50 per pakket (afhankelijk van formaat)

**Wanneer te gebruiken:** Echte verzendingen (demo's gebruiken gesimuleerde labels)

---

### 8. Teamleader Focus (CRM)
**Kostenmodel:** Abonnement vereist
- Teamleader Focus: Vanaf ~€50/maand per gebruiker
- API toegang: Inbegrepen

**Wanneer te gebruiken:** CRM integratie voor bestaande Teamleader gebruikers

---

## Implementatie Status

| Connector | Status | Gebouwd | Geïntegreerd |
|-----------|--------|---------|--------------|
| Mollie | ✅ | Ja | Nee (premium add-on) |
| KVK API | ✅ | Ja | Nee (premium add-on) |
| Belastingdienst | ✅ | Ja | Nee (premium add-on) |
| IBAN Check | ⏳ | Nee | Nee |
| Exact Online | ⏳ | Nee | Nee |
| AFAS | ⏳ | Nee | Nee |
| PostNL | ⏳ | Nee | Nee |
| Teamleader | ⏳ | Nee | Nee |

**Legenda:**
- ✅ = Klaar voor gebruik (code beschikbaar)
- ⏳ = Gepland/nog niet gebouwd

---

## Pricing voor Klanten

### Premium Connector Pack (aanbevolen)
- Prijs: **€49/maand** bovenop bestaand abonnement
- Inclusief:
  - Mollie integratie (transactiekosten apart)
  - KVK API (€6,40/maand inbegrepen, gebruik tot 500 calls)
  - PostNL labelgeneratie (zendingkosten apart)
  - Teamleader Focus koppeling

### Pay-per-use (alternatief)
- Mollie: Alleen transactiekosten (doorberekend)
- KVK API: €6,40/maand + €0,02/call
- Belastingdienst: €19,50/maand (Bokkz)

---

## Waarom Aparte Premium Categorie?

1. **Kostentransparantie**: Klanten zien exact waar ze voor betalen
2. **No-surprise billing**: Geen onverwachte kosten in basisabonnement
3. **Compliance**: Sommige diensten (KVK, Belastingdienst) hebben wettelijke vereisten
4. **Marktpositionering**: Gratis demo's (D1-D3) blijven beschikbaar zonder externe kosten

---

## Technische Implementatie

Alle premium connectoren gebruiken:
- **Capability contract** (Fase 0)
- **Tenant policy enforcement** (Fase 3)
- **Execution tracing** (Fase 0)
- **Audit bundles** (Fase 3)

Ze kunnen worden geactiveerd via:
```python
from src.core.connectors.premium import MollieConnector, KVKConnector

# Alleen beschikbaar als tenant premium_pack heeft gekocht
if tenant.has_feature("premium_connectors"):
    connector = MollieConnector(tenant.config)
```
