STATUS: APPROVED

# Review BE-CD-STAGING-001 -- de staging-uitrol klaarmaken

Gate 2: security-reviewer (subagent), commit bd16d458, een ronde op 2026-10-23. Eindoordeel GO, geen lek en geen omzeilbare poort die de uitrol blokkeert. De reparaties hieronder zijn daarna door de bouwer gedaan en NIET opnieuw door een reviewer gelezen.

## Bevindingen en afhandeling

| # | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| 1 | Middel | ActivePieces krijgt de eigenaarsrol (`STAGING_DATABASE_URL`) als gewone env-var voor zijn eigen database; derde-partij-image met externe ingress. Niet nieuw. | NIET OPGELOST, bewust: eigen brief (een eigen AP-databaserol + container-app-geheim). Genoemd in `docs/infra/UITROL-STAGING-2026-10.md` sectie 6; de guard kent de AP-stap als benoemde uitzondering met reden. |
| 2 | Laag-Middel | De preflight eiste niet dat de inlogrol (`STAGING_BYPASS_DATABASE_URL`) een eigen rol is; zette iemand hem op de eigenaar, dan hield de API eigenaarsrechten via `bypass_session`. | OPGELOST: de rollencontrole eist `bypass` niet gelijk aan de eigenaar of de applicatierol; test en mutatie. |
| 3 | Laag | De hex-controle van het bonlezer-Redis-wachtwoord zat pas in de bonlezer-stap, na de backend. | OPGELOST: eigen preflightstap `Check that the bonlezer Redis password is URL-safe`; de test eist dat hij voor de backend-stap komt. |
| 4 | Laag | Azure Files met de accountsleutel, `dir_mode=0777`, uitgaand verkeer en een Redis zonder TLS binnen de omgeving (breder dan docker-compose.yml); Redis-image niet op digest. | NIET OPGELOST, bewust: staat onder "Niet gemeten" in de lijst; een share-scoped SAS of eigen opslagaccount en een image-digest zijn een vervolg. |
| 5 | Laag | De `az rest PATCH` op de backend vervangt `volumes` en `containers`; ARM-gedrag niet gemeten. | NIET OPGELOST, bewust: de stap is idempotent en weigert bij niet precies een container; genoemd onder "Niet gemeten". |
| 6 | Laag | `MASTER_ENCRYPTION_KEY` gaat ook naar de planner en de leerwerker (alleen waar de code hem aantoonbaar leest); verouderde geheimen (`database-url` op de API-app, `deepseek-api-key`) blijven na `update` staan. | DEELS: opruimlijst toegevoegd (sectie 5b); of planner en leerwerker de sleutel echt lezen is niet nagegaan. |
| 7 | Laag | `printf '"%s"'` in de YAML zonder escaping voor de optionele SMTP-waarden; heredoc-bestanden blijven op de runner. | NIET OPGELOST: alleen wie geheimen mag zetten kan dit breken; bestaand gedrag. |
| d | bewaking | `_GEHEIM_PATRONEN` kende de bonlezer-Redis, de opslagsleutel en het mailwachtwoord niet. | OPGELOST: `STORAGE_KEY`, `REDIS_PASSWORD` en `SMTP_PASSWORD` toegevoegd; mutatie (geheim inline in de shelltekst) wordt rood. |
| e | guard | `APP_STAPPEN` is een vaste lijst; een nieuwe app-stap met een andere naam die de eigenaar noemt viel erbuiten; de regex voor `DATABASE_URL=secretref:app-database-url` matchte ook `BYPASS_DATABASE_URL=...`. | OPGELOST: omgekeerde test met benoemde lijst `EIGENAAR_TOEGESTAAN` (reden per stap) en staleness-test; de regex heeft een woordgrens. |

## Mutatiebewijs na de reparaties (alles hersteld uit kopie)

- Een nieuwe stap met een andere naam die `STAGING_DATABASE_URL` in `env:` zet -> `alleen_benoemde_stappen` ROOD.
- `bypass in (eigenaar, app)` weg -> ROOD. De hexcontrole-stap uit de preflight -> ROOD.
- De AP-stap noemt de eigenaar niet meer -> staleness ROOD.
- Een geheim inline (`${{ secrets.STAGING_BONLEZER_REDIS_PASSWORD }}`) in de shelltekst van een CD-stap -> `test_cd_secrets_go_through_env` ROOD.

## Niet gemeten

De reviewer en de bouwer hebben niets tegen Azure of GitHub gedaan; de workflow is nooit gedraaid (zie `docs/infra/UITROL-STAGING-2026-10.md`, sectie 6).
