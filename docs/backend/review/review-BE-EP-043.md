# Code & Quality Review: BE-EP-043 Foundation Portal XML Sitemap Endpoint

## Review Metadata

- **Feature ID**: `BE-EP-043`
- **Datum**: 2026-09-12
- **Reviewer**: Red Team / Shadow CEO
STATUS: APPROVED

---

## Review Bevindingen

### 1. Architectuur & Tenant Isolatie
- **Multi-Tenant Scheiding**: Het endpoint queryt expliciet op `FoundationContent.tenant_id == tenant.id`. Er is geen mogelijkheid tot cross-tenant data-lekkage.
- **N-2 Invariant**: Zowel `Privacy.PUBLIC` als `Visibility.PUBLIC` worden hard afgedwongen in de WHERE-clause, naast `ContentStatus.APPROVED`. Educatieve content (`Visibility.EDU`), community-only en niet-goedgekeurde items zijn hermetisch uitgesloten van de index.
- **ADR-033 Conformiteit**: De router is geregistreerd via de Laag 3 registry (`src/core/api/registries/foundation.py`) en sub-router in `src/core/api/v1/foundation/router.py`.

### 2. Kwaliteit, Beveiliging & Codebase Regels
- **Geen Naive Datetime**: Gebruikt `to_utc()` uit `src.core.shared.datetime_utils`. Geen `datetime.now()` of `datetime.utcnow()`.
- **ASCII Handhaving**: Geen emoji's of non-ASCII tekens in broncode, commentaren of logs.
- **Geen Onbewezen Aannames**: ElementTree parse-tests en canonieke domeinresoluties zijn empirisch getoetst via unit-tests.
- **DoS & Scrape Protectie**: Het endpoint is gedecoreerd met `@portal_public_read_limit` en retourneert `Cache-Control: public, max-age=3600, s-maxage=86400`, waardoor reverse proxies en CDNs de belasting effectief opvangen.

---

## Devil's Advocate (Red Team Mandate)

Waarom zou deze oplossing in de toekomst kunnen falen of technische schuld bevatten?

1. **50.000 Items Plafond & Sitemap Indexering**:
   - *Risico*: De huidige implementatie pagineert via een cap van 50.000 items (de maximale limiet van een enkel XML-bestand conform sitemaps.org). Indien een erfgoedstichting meer dan 50.000 publieke items bezit, worden items boven de limiet afgekapt.
   - *Mitigatie*: Voor MVP en Fase 2 is dit ruim voldoende (de grootste erfgoedcollectie binnen het platform telt momenteel enkele duizenden items). Zodra een collectie 40.000 items nadert, dient een geautomatiseerde `sitemap_index.xml` met gepartitioneerde sub-sitemaps (`sitemap_1.xml`, `sitemap_2.xml`) geïmplementeerd te worden.

2. **Dynamische Basis-URL Spoofing via Host Headers**:
   - *Risico*: Indien Traefik of de edge proxy ongefilterde `Host` of `X-Forwarded-Host` headers toestaat van externe partijen, zou een aanvaller een valse canonieke URL in de sitemap kunnen forceren (Host Header Injection).
   - *Mitigatie*: De backend geeft absolute prioriteit aan `tenant.custom_domain` uit de beveiligde PostgreSQL tenant-tabel. Alleen bij afwezigheid van een custom domain wordt de gevalideerde host-resolving engine (`normalize_host` met RFC 1035 verificatie) aangesproken.

---

## Verdict

**STATUS: APPROVED**  
De implementatie is robuust, veilig, dekt alle gestelde vereisten af en doorstaat de kwaliteitsgates.
