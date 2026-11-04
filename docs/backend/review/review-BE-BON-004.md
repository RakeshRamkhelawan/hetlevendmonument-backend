STATUS: APPROVED

# Review BE-BON-004: bonlezer dag 4 (scherm, bevestigen, opruiming na 30 dagen)

- **Datum:** 2026-10-17
- **Spec:** `docs/backend/features/BE-BON-004-bonlezer-dag4-scherm-bevestigen-en-30-dagen.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** sessie sanskritisetu-org-bd (nu -7d), tak `iter/bonlezer4`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit 22631098)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED | HOOG: het scherm vroeg maar 50 bonnen. HOOG: onzichtbare tekens als rauwe tekens in testbestanden (ASCII-regel). HOOG: de opruiming stopte bij een OSError in een tenantmap. LAAG: geen verversing bij status wachten, bedrag met meerdere duizendtalpunten, twee functies voor de uploadmap. |
| quality-reviewer | CHANGES_REQUESTED | ASCII (zelfde tekens). ruff, pyright 0, mypy 0, Any 7037 geslaagd. Opmerking: een tijdelijk bestand met de bevestigde velden bleef bij een schrijffout achter. Frontend type-check niet meetbaar in zijn worktree (geen node_modules). |
| security-reviewer | GO | MIDDEL: geen limiet op lezen en bevestigen. LAAG: geen CSRF op bevestigen (en upload), opruiming faalt bij een mapfout, race opruiming en bevestigen, rw-volume in een worker die ook agentstappen draait, opnieuw bevestigen zonder versie. |

## Wat ermee gedaan is (commit f1e7bd49)

Eerst rode tests, dan de reparatie: CSRF op upload en bevestigen, limieten (60 lezen, 30 bevestigen per
minuut), opruiming gaat door bij een mapfout of verdwenen bestand, geen tijdelijk bestand of wees-metabestand
meer, tekens als escape, scherm vraagt limit 1000 en meldt "U ziet X van Y bonnen". Mutatiebewijs voor deze
reparaties: 10 van 10 gevangen (`mutatiebewijs-bonlezer-dag4-ronde2.txt`, in een wegwerp-worktree, map weg).

Bewust niet vandaag, met reden: verversen bij status wachten (de medewerker klikt opnieuw), een tweede
uploadmap-functie samenvoegen (opmerking), rw-volume in de workflow-worker en versie van bevestigingen (open
besluiten in de spec), een gedeelde teller voor de limiet (meer gunicorn-workers, zelfde als dag 3).

## Gate 2 -- ronde 2 (commit f1e7bd49)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| security-reviewer (ook code) | GO | Alle reparaties correct. Laag: `bedrag()` maakte van `1,234.56` stil `1.234`; de limiet telt per bon-pad. |

Het `bedrag()`-punt is daarna hersteld (alleen de Nederlandse vorm wordt omgezet, de rest gaat ongewijzigd naar
de server); de limiet per pad blijft (zelfde gedrag als de uploadlimiet van dag 3).

## Acceptatie (2026-10-17) en Gate 2 op het herstelwerk

De acceptant keurde dag 4 af op vier punten: het leesresultaat verdween na ~6 minuten (gemeten: sleutel had 286 s
van 300 s over), "Controleren" verscheen nooit, de lijst toonde alleen tijdstip en status, de pakketuitslag noemde
stap 1 "Stap 1" en toonde niets over de bonnen. Besluit Rakesh (via de regie): bevestigde velden bewaard tot het
einde van het kwartaal van de bondatum plus 3 maanden. Alles hersteld met eerst een rode test.

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| security-reviewer ronde 1 | CHANGES_REQUESTED | HOOG: een bondatum in het jaar 9999 liet `bewaar_tot` crashen en blokkeerde de opruiming van alle tenants (gemeten: ValueError). MIDDEL: de bondatum is invoer van de gebruiker en bepaalt de termijn (ver verleden = meteen weg, ver toekomst = nooit). LAAG: diep geneste JSON, lijst bij kapotte Redis, onware docstring over de bestandsnaam, kapot resultaatbestand gaf permanent "verlopen". |
| code-reviewer ronde 1 | CHANGES_REQUESTED | HOOG: de lijst haalde een bon die niemand opende alleen binnen 480 s op, terwijl het resultaat 30 dagen in Redis staat. LAAG: na een Redis-fout niet verder proberen, race opruiming en vastleggen (onschadelijk). |
| security-reviewer ronde 2 | GO | Alle reparaties correct; opmerking: `_lees_json` ving `RecursionError` niet (ook hersteld). |

Herstel: `bewaar_tot` geeft `date.max` voorbij de kalender; de termijn eindigt niet eerder dan 30 dagen na het
bevestigen en niet later dan 10 jaar daarna (aanname van de bouwer, niet besloten); `RecursionError` afgevangen;
een kapot of onbekend resultaatbestand geldt als afwezig (terugval op Redis); de lijst haalt ook oude bonnen op en
stopt na de eerste fout. Het mutatiebewijs liet twee overlevers zien (M25 en M26: mijn testdata was ook om een
andere reden ongeldig); die tests bewaken nu elke voorwaarde apart. Eindstand: 33 van 33 mutaties gevangen
(26 backend, 7 frontend), bewijs in `mutatiebewijs-bonlezer-dag4-acceptatiefixes.txt` naast de overige logs.

Niet gedaan: een derde reviewronde (afspraak: maximaal twee) en een nieuwe acceptatie met beeld; die volgt bij de regie.

## Gemeten

Zie `docs/evidence/bonlezer-dag4-2026-10-17.md`.
