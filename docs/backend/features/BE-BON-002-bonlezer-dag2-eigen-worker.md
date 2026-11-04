# Backend Feature Specification

## Metadata

- **Feature ID:** BE-BON-002
- **Feature naam:** Bonlezer dag 2 -- een eigen worker die een bon uit de uploadmap van een tenant leest, los van de backend
- **Status:** Gereed op code en meting (Gate 2 twee rondes afgerond, zie de review); de agent is NIET bedraad, er is geen upload-route
- **Auteur:** bouwer bonlezer1 (sessie sanskritisetu-org-bd, nu -7d)
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2, twee rondes)
- **Datum:** 2026-10-15
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag2-eigen-worker.md` (SP-KLANT-04, `mkb.zero_admin`)
- **Gerelateerde router / module:** `src/core/als/bonlezer/worker.py`; GEEN router en GEEN endpoint
- **Gerelateerde frontend endpoints:** geen
- **Gerelateerde database tabellen:** geen (GEEN migratie, de uitkomst gaat via de resultaatopslag van Dramatiq in Redis)
- **Versie:** 1.0

## Doel en scope

### Doel

Docling, torch en Tesseract draaien alleen in een EIGEN worker-image, niet in het backend-image. De worker
neemt een opdracht `lees_bon(tenant_id, bestand_id)` aan van een eigen wachtrij `bonlezer`, leest het
bestand uit de eigen uploadmap van die tenant en geeft status, reden, sha256 en velden terug.

### In scope

- Dockerfile-doel `bonlezer-worker` en compose-dienst `bonlezer-worker` op het interne netwerk
  `bonlezer_intern` (`internal: true`, alleen Redis erbij), uploadmap alleen-lezen, geen poort, geen database,
  `cap_drop: ALL`, `no-new-privileges`, `restart`, `pids_limit`, healthcheck.
- Actor `lees_bon` op een eigen broker met eigen sleutelvoorvoegsel en een eigen, beperkte Redis-gebruiker.
- Veilig openen: `tenant_id` uit de opdracht (nooit uit het bestand), `bestand_id` van 32 hexadecimale
  tekens en een vaste extensie, `lstat`, `O_NOFOLLOW`, vergelijking van descriptor en `lstat`, een keer
  lezen, hash, privekopie 0600, uniforme weigering, geen bontekst in log of resultaat.
- Middleware `_VasteOpties`: de limieten van een bericht staan vast, wat het bericht ook meebrengt.
- Guardtest `tests/architecture/test_bonlezer_zit_alleen_in_de_eigen_worker.py`.
- Meting: `scripts/bonlezer/meet_worker.sh` en `scripts/bonlezer_worker_meting.py`;
  `docs/evidence/bonlezer-worker-2026-10-15.md`.

### Buiten scope

- Upload-route, scherm, btw-concept en de agent bedraden (dag 3-4).
- Een aparte Redis-instantie voor de worker: besluit regie 2026-10-15, wordt dag 3.

## Gemeten (2026-10-15)

| Wat | Uitkomst |
| --- | --- |
| Image | 5,09 GB, circa 2,2 GB extra boven het basisimage |
| 24 testbonnen via de worker | 24 van 24 gelezen, uitslag per veld gelijk aan dag 1 |
| Leestijd | gemiddeld 4,7 s, langste 26,0 s |
| Netwerk | Redis bereikbaar, internet niet |
| Foute opdrachten | andere tenant, pad met `..`, verzonnen nummer: alle drie geweigerd |
| Mutatiebewijs | 32 van 32 en 20 van 20 gevangen |

## Trainingssamenvatting

### Een bon laten lezen door de worker (backend, vanaf dag 3)

- **Actor:** de backend, namens een ingelogde gebruiker; vandaag alleen het meetscript.
- **Voorwaarde:** het bestand staat onder `<uploadmap>/<tenant_id>/<bestand_id>` met een `bestand_id` van 32
  hexadecimale tekens en een toegestane extensie; de worker draait met zijn eigen Redis-gebruiker
  (`BONLEZER_REDIS_STATUS=on` en `BONLEZER_REDIS_PASSWORD`).
- **Actie:** `lees_bon.send(tenant_id, bestand_id)` met de `tenant_id` uit de JWT, daarna het resultaat
  ophalen met `haal_resultaat`.
- **Systeemreactie:** de worker leest het bestand een keer, hasht het, geeft de lezer een privekopie en
  antwoordt met status, reden, sha256 en velden; het log bevat tenant, hash, duur en status, geen bontekst.
- **Succes:** status `gelezen` met de velden.
- **Fout:** status `geweigerd` ("bestand niet gevonden" voor een ontbrekend, te groot of andermans bestand,
  "ongeldige opdracht" voor een slecht nummer) of `fout` met alleen de naam van het fouttype.
- **Uitzondering:** het resultaat blijft 300 s in Redis; daarna volgt `ResultMissing`. Een bon met een
  opmaak buiten de testset kan velden leeg laten.

## Open punten

Zie `docs/evidence/bonlezer-worker-2026-10-15.md`, sectie Open punten: Redis-isolatie (aparte instantie),
de eisen voor dag 3, de nieuwe omgevingsvariabelen `BONLEZER_REDIS_STATUS` en `BONLEZER_REDIS_PASSWORD`, en
wat niet gemeten is.
