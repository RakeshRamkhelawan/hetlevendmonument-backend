STATUS: APPROVED

# Review BE-BON-003: bonlezer dag 3 (eigen Redis en upload-route)

- **Datum:** 2026-10-17
- **Spec:** `docs/backend/features/BE-BON-003-bonlezer-dag3-eigen-redis-en-upload.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** sessie sanskritisetu-org-bd (nu -7d), tak `iter/bonlezer3`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit 6e5e2a68)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED | BLOKKERING: een klare bon werd na 300 s (resultaat weg) tot 600 s nog "wachten" getoond. Opmerkingen: verouderde comment over een Redis-gebruiker, foutvorm als dict, onderbouwing van het fan-out-budget, bewaartermijn niet in de spec. |
| quality-reviewer | GO | ruff, C901, pyright 0, mypy 0, Any 7037, bandit 0, ASCII (alleen vier oude regels in de compose), documentatiepoort groen. Opmerking: `type: ignore` in tests zonder uitleg. |
| security-reviewer | NO-GO | HOOG: de worker zag `backend:8000` op hetzelfde interne netwerk. HOOG: het quotum was parallel en door de status op te vragen te omzeilen. MIDDEL: de sha256-toets beschermt niet tegen een kwaadwillende worker; de worker kon Redis laten hangen of volschrijven; de body wordt voor de rechtencontrole gelezen; gifpil (hypothese). |

## Wat ermee gedaan is (commit 69822afa)

Elke reparatie kreeg eerst een rode test: twee interne netwerken (gemeten: de worker bereikt de API niet),
reserveren voor tellen, 12 uploads per minuut, strenge toets op de velden van de worker, de verlopen-grens op
de bewaartijd, vol-schijf geeft 503 en ruimt op, time-outs en een geheugengrens voor de bonlezer-Redis,
foutmelding als tekst, weigeringen in het log. Mutatiebewijs: 33 van 33.

Bewust niet vandaag, met reden (evidence-document): de lichaamsgrootte voor de rechtencontrole (vraagt een
wijziging in een gedeelde middleware), de gifpil (niet gemeten), een opruimtaak (gebruikersdata, interlock 1).

## Gate 2 -- ronde 2 (commit 1d6938c8)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED | BLOKKERING: de time-out van 5 s deed niets, want bij `url=` maakt dramatiq een eigen verbindingspool (gemeten op `connection_kwargs`). BLOKKERING: niets zette `request.state.user`, dus de sleutel van de limiet was het IP. Opmerkingen: leverancier (tot 500) en factuurnummer (tot 64) werden te streng getoetst. |
| security-reviewer | NO-GO op de limiet | De limiet was niet per gebruiker (zelfde bevinding). MIDDEL: schijf vullen door een gewone gebruiker (open punt). LAAG: tekstvelden zonder tekenklasse (eis voor dag 4); een alleenstaande surrogaat geeft een permanente 500. Gemeten: de twee netwerken werken zoals bedoeld (de worker bereikt de backend, de hoofd-Redis en het internet niet). |

## Wat ermee gedaan is (commit dcb7510f)

- De time-outs staan in de URL; tests in een apart proces lezen de verbindingspool van de echte clients.
  Gemeten met `CLIENT PAUSE 20000`: zonder instelling wacht `PING` 13,8 s, met `5` volgt na 5,0 s een `TimeoutError`.
- De rechten-afhankelijkheid zet de gebruiker op het verzoek; test met twee gebruikers op hetzelfde adres.
- Grenzen 500 en 64 voor leverancier en factuurnummer; een ongeldige tekenreeks wordt geweigerd of weggelaten.
- Mutatiebewijs voor deze reparaties: 13 van 13.
- Laten liggen, met de reden en in het evidence-document: schijf vullen (een vast plafond blokkeert echte klanten
  zonder opruimtaak), tekstvelden zonder tekenklasse (dag 4), een gedeelde teller voor de limiet (meer
  gunicorn-workers), de body voor de rechtencontrole, de gifpil.
- Na ronde 2 heeft geen reviewer meer gekeken (afspraak: maximaal twee rondes).

## Gemeten

ruff schoon, pyright 0 fouten, mypy-audit 0, Any-telling 7037; integratietest met echte rechten 13 groen;
echte upload via de API door de echte worker 24 van 24 (uitslag per veld gelijk aan dag 1 en 2), 404 voor een
andere tenant, 413 en 415 zonder bestanden achter te laten, 429 bij de zesde upload, geen bontekst in de logs.
De compose-dienst zelf en de echte backend-container zijn niet gestart.
