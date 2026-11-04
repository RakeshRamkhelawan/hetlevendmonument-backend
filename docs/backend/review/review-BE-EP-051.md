# Code Review: BE-EP-051 Foundation Notice & Takedown Curation & Resolution API

**Feature ID:** `BE-EP-051`  
**Onderwerp:** Foundation Notice & Takedown Curator Moderatie, Content Statusverwijdering & Notificatiestroom  
**Reviewer:** Red Team / Shadow CEO  
**Datum:** 2026-09-15  
**STATUS: APPROVED**  

---

## 1. Doel & Beoordeling

Het doel van `BE-EP-051` is het bieden van een conforme en veilige curator workflow voor Notice & Takedown meldingen conform art. 6:196c BW, de NTD Gedragscode en EU DSA Art. 16/17.

### Pluspunten
- Verplichte motivering (`resolution_note`, min 5 tekens) conform DSA motiveringseisen.
- Geen hard delete: status wijzigt naar `ContentStatus.REMOVED`, waardoor bewijslast bewaard blijft.
- Publieke endpoints verbergen direct alle `REMOVED` content.
- OAI-PMH export bevat correcte deleted status tags.
- Reversal mogelijkheid via `restore_content` bij gegrond tegenbericht/bezwaar.
- Geautomatiseerde Brevo notificaties naar melder en uploader.
- 100% testdekking via unit tests en PostgreSQL integratietests.

---

## 2. Devil's Advocate (Red Team Mandaat)

### Risico's & Beheersing
1. **Onterechte Verwijdering & Chilling Effect:** Een curator zou te snel tot verwijdering kunnen overgaan uit angst voor aansprakelijkheid. Beheersing: De wet en NTD code vereisen een zorgvuldige belangenafweging; de motivering is verplicht en kan via de restore endpoint altijd hersteld worden.
2. **Cross-Tenant Escalatie:** Curatoren van tenant A mogen nooit meldingen van tenant B kunnen inzien of manipuleren. Beheersing: Strikt afgedwongen via `public_tenant_scope` en geautomatiseerde isolatietests.

**Oordeel:** GO (STATUS: APPROVED).
