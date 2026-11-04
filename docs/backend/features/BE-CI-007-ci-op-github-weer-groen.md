# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CI-007
- **Feature naam:** De CI op GitHub weer groen: python-jose, niet-ASCII lokaal afgedwongen, twee ratels
- **Status:** Geimplementeerd (Gate 2 ronde 1 verwerkt)
- **Auteur:** bouwer (tak `iter/cigroen`)
- **Reviewer:** security-reviewer (Gate 2, een ronde)
- **Datum:** 2026-10-23
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-23-sprint-dag-ci-op-github-weer-groen.md`
- **Gerelateerde modules:** `scripts/check_non_ascii.py`, `scripts/hooks/pre-commit`, `.github/workflows/ci-feature.yml`, `docs/compliance/soc2/risk-register.md`, `docs/compliance/soc2/vulnerability-management.md`, `frontend/any-type-baseline.json`
- **Database:** geen migratie.

---

## Doel en scope

### Doel

De eerste proefrun van GitHub Actions op develop (run 39852524654, 2026-10-22) was rood. Vier stappen faalden:

| Job | Stap | Oorzaak (gemeten) |
|---|---|---|
| Security Scan | Dependency audit | `python-jose 3.5.0` heeft PYSEC-2026-4298; er is geen herstelde versie |
| Python | non-ASCII gate | twee tekens in `src/core/llm/mistral_provider.py` en `src/core/copilot/service.py` |
| Python | ratel op tests die nooit draaien | twee architectuurtests parametriseren over een LEGE lijst; pytest maakt een overgeslagen item `[NOTSET]` |
| Frontend | Any-type gate | het aantal is GEDAALD (431 naar 419), niet gestegen |

### In scope

1. python-jose: reproduceren, bereikbaarheid meten, gedateerde uitzondering met guard.
2. Niet-ASCII: een script als enige definitie, aangeroepen door pre-commit (stap 0) en CI.
3. Ratel op tests die nooit draaien: de twee tests zijn gewone tests.
4. Frontend-baseline omlaag vastgelegd.

### Out of scope

- python-jose vervangen door PyJWT (raakt inloggen; eigen brief).
- Een push of een run op GitHub.

---

## Technische beschrijving

### python-jose (PYSEC-2026-4298)

- Het lek: tot en met 3.5.0 accepteert python-jose een DER-gecodeerde publieke sleutel als HMAC-geheim; wie de publieke sleutel kent kan HS256-tokens vervalsen als de aanroep zijn algoritmen niet beperkt. 3.5.0 is de nieuwste versie; er is geen herstelde versie.
- Gereproduceerd met `pip-audit` 2.9.0 en de vlaggen van de CI: 1 lek (exit 1). Met de uitzondering: geen lekken, 6 genegeerd (exit 0).
- Bereikbaarheid, per verificatieplek: alle gebruik in `src/` heeft een vaste algoritmelijst (`HS256`, of `HS256/384/512` via een whitelist) en een geheime tekst als sleutel. De enige RS256-plek (`token_service.py`) gebruikt PyJWT, niet python-jose. Het lek vraagt een publieke sleutel EN onbeperkte algoritmen; geen van beide komt voor.
- Gedaan: `--ignore-vuln PYSEC-2026-4298` met `# SKIP:`-markering; entry in het risicoregister met herbeoordeling **2026-11-22** (30 dagen); acceptatie door Rakesh nog te geven; guard `tests/architecture/test_python_jose_blijft_onbereikbaar_voor_het_lek.py` (decode zonder `algorithms=`, asymmetrisch algoritme, publieke sleutel of een import buiten `jose.jwt` en de uitzonderingsklassen laat hem falen).
- Blijft over: python-jose vervangen door PyJWT; dat laat de uitzondering vervallen.

### Niet-ASCII

`scripts/check_non_ascii.py` (standaardbibliotheek): bestanden als argument (pre-commit) of `--alles` (CI: gevolgde `.py` onder `src/`, `scripts/`, `mcp-server/`, zonder `src/alembic/versions/archive/`). Een niet-UTF-8 bestand telt als schending. Splitst op `"\n"` (niet `splitlines()`) en leest `git ls-files -z`. De pre-commit slaat de stap over in een tak zonder het script, omdat `.git/hooks` gedeeld wordt.

### Ratels

- `test_elke_uitzondering_heeft_een_reden` in `test_geen_procesbrede_broker.py` en `test_workflowuitvoering_zoeken_op_execution_id.py` is niet meer geparametriseerd.
- `frontend/any-type-baseline.json`: 431 naar 419, alleen verwijderde regels.

## Acceptatiecriteria

- `pip-audit` met de vlaggen uit de workflow: exit 0.
- `python scripts/check_non_ascii.py --alles`: exit 0; een gestaged `.py` met een niet-ASCII-teken (ook U+2028) faalt.
- `python scripts/count_disabled_tests.py`: exit 0.
- `node frontend/scripts/check-any-gate.mjs --baseline frontend/any-type-baseline.json`: exit 0.

Tests: `test_precommit_weigert_niet_ascii.py` (20), `test_python_jose_blijft_onbereikbaar_voor_het_lek.py` (25), de twee aangepaste architectuurtests.

## Trainingssamenvatting

### Een commit met een niet-ASCII-teken

- Actor: ontwikkelaar
- Voorwaarde: een gestaged `.py` onder `src/`, `scripts/` of `mcp-server/` bevat een teken buiten ASCII
- Actie: commit
- Systeemreactie: de pre-commit draait `scripts/check_non_ascii.py` en stopt de commit met bestand, regel en kolom
- Succes: na ASCII maken slaagt de commit
- Fout: "niet-ASCII teken(s) in Python-broncode (NOOIT-lijst)" met de plek
- Uitzonderingen: het archief telt niet; een tak zonder het script slaat de stap over

### Een pip-audit-uitzondering toevoegen

- Actor: ontwikkelaar of beveiligingsverantwoordelijke
- Voorwaarde: `pip-audit` meldt een lek zonder herstelde versie
- Actie: meet bereikbaarheid, leg meting en herbeoordelingsdatum vast in het risicoregister, zet de vlag met `# SKIP:`
- Systeemreactie: de audit slaagt met "N ignored"
- Succes: CI groen, de uitzondering heeft een einddatum
- Fout: een uitzondering zonder entry of meting wordt in review geweigerd
- Uitzonderingen: acceptatie door Rakesh blijft nodig

## Bewust laten liggen

| Punt | Reden |
|---|---|
| `core.quotepath=off` in de `STAGED=`-regel van de pre-commit | een hookwijziging maakt de guard `test_de_geinstalleerde_hook_is_de_bron` rood in andere werkkopieen; wacht op sein van de regie |
| Verlopen herbeoordelingen chromadb PYSEC-2026-311 en ecdsa PYSEC-2026-1325 (2026-10-13) | risicoacceptatie is aan Rakesh; gemeld aan de regie |
| Guard ziet geen variabele algoritmelijst met RS256 | vraagt een codewijziging die het register als herbeoordelingstrigger noemt |

## Niet gemeten

- De CI op GitHub zelf; per rode stap is lokaal met dezelfde commando's nagedraaid.
- Migraties, integratietests, coverage, Playwright-E2E en Docker-validatie van de CI.
- Of `ecdsa` alleen via python-jose binnenkomt.

## Uitslag van de CI op GitHub na de push (2026-10-24)

Run **40030781485** op develop `69f433cc` (de eerste volledige run na de reparaties van deze dag; door de regie gemeld):

- **Groen:** Security Scan (de python-jose-uitzondering werkt), Frontend, de Any-baseline, Bicep, Docker.
- **Rood:** de Python-job, 1 gefaald en 7614 geslaagd: `tests/unit/als/test_dunning_hotl_meting.py::test_hotl_creates_no_ticket_and_the_broker_refuses_the_send`, met `EchteVerbindingInUnitTest` naar `::1:5432` (een unittest die een echte databaseverbinding probeert).

Die ene rode test hoort niet bij deze brief: hij komt uit de bestaande dunning-brief en heeft een eigen brief (sessie 7f). De vier stappen die de proefrun van 2026-10-22 rood zette (dependency-audit, niet-ASCII, ratel op tests die nooit draaien, frontend-any) zijn op GitHub groen. Daarmee is de CI-brief af. Wat de CI in die proefrun nooit mat en lokaal niet is nagelopen (migraties, integratietests, coverage, Playwright-E2E, Docker-validatie) is nu door deze run gemeten, behalve wat in de job `Python` door die ene rode test is overgeslagen.
