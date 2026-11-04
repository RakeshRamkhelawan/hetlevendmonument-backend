STATUS: APPROVED

# Review BE-BON-002: bonlezer dag 2 (eigen worker)

- **Datum:** 2026-10-15
- **Spec:** `docs/backend/features/BE-BON-002-bonlezer-dag2-eigen-worker.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** sessie sanskritisetu-org-bd (nu -7d), tak `iter/bonlezer1`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit 491b8694)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED | Een niet-ASCII teken in een docstring; de lezer werd voor een geweigerde opdracht geladen; het fouttype stond niet in het log; geen expliciete bewaartijd; het evidence-document noemde de compose-dienst als gemeten terwijl de meting wegwerpcontainers gebruikte. |
| quality-reviewer | CHANGES_REQUESTED | Alleen het niet-ASCII teken. ruff, pyright 0, mypy 0, Any 7037, bandit 0. |
| security-reviewer | voorwaardelijk NO-GO | HOOG: het hoofdwachtwoord van Redis zat in de worker. HOOG: opties per bericht overschrijven de limieten. "Te groot" en de hash bij een weigering verraden het bestaan. Geen `restart`; `pgrep` bestaat niet in het image. |

## Wat ermee gedaan is (commit 0679e846)

Elke reparatie kreeg eerst een rode test (10 tests rood tegen de oude code): ASCII, eigen Redis-gebruiker en
sleutelvoorvoegsel, `_VasteOpties`, uniforme weigering zonder hash, `_LuiweLezer`, `reden=<type>` in het
log, `restart` en `pids_limit`, een healthcheck zonder `pgrep`, `result_ttl` 300 s.

Daarvoor al, op verzoek van regie: de tenant- en bestandsgaten en de verwisselcontrole kregen tests die ook
op Windows draaien (zonder echte symlinks). Het eerste mutatiebewijs liet 9 van 32 mutaties door.

## Gate 2 -- ronde 2 (commit 0679e846)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED op een punt | BLOCKER: `BONLEZER_REDIS_PASSWORD` was verplicht in de hoofd-Redis en liet bestaande opstellingen niet starten. Opmerkingen: `result_ttl` per bericht werkte nooit (docstring onjuist), een test voor het behoud van `redis_message_id`, de healthcheck is niet bestand tegen een verdwenen pid. |
| security-reviewer | GO, voorwaardelijk | Gemeten ACL: de gevaarlijke commando's zijn geweigerd. `EVAL` kan de Redis stilleggen en kan niet dicht zonder Dramatiq te breken; `SCAN`, `RANDOMKEY` en `DBSIZE` toonden sleutelnamen; het patroon van 32 hexadecimale tekens is breder dan beschreven. |

## Wat ermee gedaan is (commit e87bf561)

- De Redis-gebruiker staat standaard uit (`BONLEZER_REDIS_STATUS`, gemeten `WRONGPASS`), het wachtwoord is
  niet verplicht in de hoofd-Redis.
- `-scan -randomkey -dbsize` toegevoegd; meting met de echte worker: 24 van 24 gelezen, geen `NOPERM`.
- Docstrings en evidence gecorrigeerd; test dat `redis_message_id`, `retries` en `traceback` blijven staan.
- Laten liggen, met de reden: `EVAL` (alleen een aparte Redis lost het op, besluit regie voor dag 3);
  de healthcheck met `try/except` (kleine kans op een vals-negatief, opgevangen door `retries: 3`); de
  tenantmap met `dir_fd` (risico laag zolang het volume voor de worker alleen-lezen is).
- Na deze laatste reparatie heeft geen reviewer meer gekeken; de guardtest ving een plakfout in de compose.

## Gemeten

ruff schoon, pyright 0 fouten, mypy-audit 0, Any-telling 7037; bonlezer-tests en guard 426 groen; mutatiebewijs
32 van 32 en 20 van 20 gevangen. De compose-dienst zelf is niet gestart.
