# Backend Feature Specification

## Metadata

- **Feature ID:** BE-BON-003
- **Feature naam:** Bonlezer dag 3 -- een eigen afgeschermde Redis voor de worker en een bon uploaden via de API
- **Status:** Gereed op code en meting (Gate 2 afgerond, zie de review); de agent is NIET bedraad, er is geen scherm
- **Auteur:** bouwer bonlezer3 (sessie sanskritisetu-org-bd, nu -7d)
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-17
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-17-sprint-dag-bonlezer-dag3-eigen-redis-en-upload.md` (SP-KLANT-04, `mkb.zero_admin`)
- **Gerelateerde router / module:** `src/core/api/v1/bonnen/` (router, dependencies), `src/core/api/registries/bonnen.py`, `src/core/als/bonlezer/upload.py`, `src/core/als/bonlezer/worker.py`
- **Gerelateerde frontend endpoints:** geen (het scherm komt op dag 4)
- **Gerelateerde database tabellen:** geen (GEEN migratie); wel nieuwe rijen in de rolzaaier (`receipts:read`, `receipts:write`) via `ensure_default_roles`
- **Versie:** 1.0

## Doel en scope

### Doel

Een medewerker uploadt een bon of factuur via de applicatie; de aparte bonlezer-worker leest hem; de
medewerker ziet de uitkomst. De worker deelt geen Redis meer met de rest van de stack.

### In scope

- Compose-dienst `bonlezer-redis` (op twee interne netwerken: `bonlezer_intern` met de worker en
  `bonlezer_koppel` met de backend, zodat de worker de backend niet ziet; geen poort, wachtwoord zonder
  terugval, niets naar schijf, geheugengrens 256mb met `noeviction`); de beperkte gebruiker in de hoofd-Redis
  verdwijnt; worker en backend gebruiken `BONLEZER_BROKER_URL` en vallen nooit terug op de hoofd-Redis; de
  backend wacht hooguit 5 s op die Redis (`BONLEZER_SOCKET_TIMEOUT`, in de URL; gemeten met `CLIENT PAUSE`).
- `POST /api/v1/bonnen` en `GET /api/v1/bonnen/{bestand_id}` met het recht `receipts:write` en
  `receipts:read`; de tenant komt uit de JWT.
- Grootte-, soort- en beginbytecontrole voor opslaan; `bestand_id` uit `secrets.token_hex(16)`; de metadata
  (sha256, bericht-id, tijdstip, afgerond) in een bestand naast de bon op het volume dat de worker alleen leest;
  toetsing van het resultaat aan de sha256 van de upload en van de velden aan een vast schema; quotum van 5
  openstaande opdrachten per tenant (429, eerst reserveren dan tellen) en 12 uploads per minuut per gebruiker.
- Meting: `scripts/bonlezer/meet_upload.sh`, `scripts/bonlezer_upload_api.py`,
  `scripts/bonlezer_upload_meting.py`; bewijs in `docs/evidence/bonlezer-upload-2026-10-17.md`.

### Buiten scope

- Scherm, de agent bedraden in het pakket, het btw-concept (dag 4).
- Een opruimtaak voor oude uploads (gebruikersdata, eigen besluit), `docker-compose.prod.yml`, de CD.

## Gemeten (2026-10-17)

| Wat | Uitkomst |
| --- | --- |
| 24 testbonnen via `POST` en `GET` door de echte worker | 24 van 24, uitslag per veld gelijk aan dag 1 en 2 |
| Tenant B op de bon van tenant A | 404 |
| 26 MB en `.exe` | 413 en 415, de uploadmap groeit niet |
| Zesde upload achter elkaar | 429 met een Nederlandse melding |
| Bontekst in het log | 0 treffers van 84 zoektermen |
| Integratietest met echte rechten | 13 geslaagd |

## Trainingssamenvatting

### Een bon uploaden en de uitkomst bekijken (medewerker)

- **Actor:** een ingelogde medewerker (rol `user`, `editor` of beheerder).
- **Voorwaarde:** een pdf, jpg, png of tif tot 25 MB; de bonlezer-worker en zijn Redis draaien
  (`BONLEZER_REDIS_PASSWORD` is gezet); minder dan 5 bonnen staan te wachten.
- **Actie:** `POST /api/v1/bonnen` met het bestand; daarna `GET /api/v1/bonnen/{bestand_id}` tot de status
  niet meer `wachten` is.
- **Systeemreactie:** de backend controleert het bestand, bewaart het onder de map van de eigen tenant, legt
  de sha256 vast en zet een opdracht op de bonlezer-wachtrij; het antwoord bevat alleen het `bestand_id`.
- **Succes:** status `gelezen` met de velden (leverancier, datum, totaal, btw per tarief, factuurnummer,
  btw-nummer, KvK-nummer).
- **Fout:** 413 (te groot), 415 (verkeerd soort of inhoud), 422 (leeg), 429 (te veel wachtend), 503 (de
  bonlezer is niet bereikbaar); status `geweigerd` of `fout` van de worker met de reden; `ongeldig` als het
  resultaat niet bij het bestand hoort.
- **Uitzondering:** de uitkomst blijft 300 s beschikbaar; daarna is de status `verlopen`. Een bon van een
  andere tenant geeft 404, ook als het `bestand_id` klopt.

## Bewaartermijn en rechten (open besluiten)

- Een geuploade bon en zijn metabestand blijven staan; er is nog GEEN opruimtaak. Een bon bevat
  persoonsgegevens (AVG), dus een bewaartermijn en het verwijderen zijn een eigen besluit voor Rakesh
  (interlock 1), niet onderdeel van deze dag.
- Het recht `receipts:write` heeft de standaardrol `user`: elke medewerker kan taken op de gedeelde worker
  zetten (begrensd door het quotum van 5 en 12 uploads per minuut per gebruiker). Bewust; hier vastgelegd.
- De worker heeft het uploadvolume alleen-lezen en kan dus de bonnen van ALLE tenants lezen: inherent aan een
  gedeelde worker.

## Regressierisico's

- `BONLEZER_REDIS_PASSWORD` is verplicht in compose voor de nieuwe diensten; een omgeving zonder die
  variabele in `.env` start niet meer (compose controleert het hele bestand).
- De architectuurguards `test_every_dispatched_actor_is_loaded_by_a_worker` (kent nu workers via `:_broker`) en
  het fan-out-budget van `core_api` (563 naar 565) zijn aangepast.
- De rolzaaier kreeg rijen voor `receipts`; bestaande tenants krijgen die pas bij `ensure_default_roles`.
