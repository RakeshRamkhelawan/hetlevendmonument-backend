STATUS: APPROVED

# Review BE-ZAD-001: Zero-Admin Bookkeeping afwerken

- **Datum:** 2026-10-19
- **Spec:** `docs/backend/features/BE-ZAD-001-zero-admin-afwerken.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** bouwsessie zeroadmin, tak `iter/zeroadmin`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit 719c1e29)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | CHANGES_REQUESTED | HOOG: stap 3 telde de eerste 200 rijen zonder statusfilter; 250 betaalde vorderingen konden een open vordering verbergen en het scherm zei dan "Geen openstaande vorderingen". MIDDEL: de CSV verloor `bestand_id`, dus oude bevestigingen zonder naam en bonnen met dezelfde naam waren niet meer te onderscheiden. LAAG: kwartaalgrens in UTC; `Number()` in de controleregels; `undefined` voor `bevestigd` gold als bevestigd. Omvang: vier thema's in een diff. |
| quality-reviewer | GO | ruff, pyright 0, mypy 0, Any-ratel 7037 = 7037, type-check en lint (0 errors) op of onder de baseline; geen non-ASCII, geen geheimen. |
| security-reviewer | GO | LAAG: de telling leest de registry rechtstreeks (alleen lezen, eigen tenant, alleen een getal); een foutmelding met de ticketzin kon de teller verhogen; oude bevestigingen hebben geen naam. Geen kritiek, hoog of middel. CSV-injectie via de nieuwe bestandsnaam, pad-traversal via kwartaal of naam, tenant uit invoer en lekken via de samenvatting zijn getoetst en schoon. |

## Wat ermee gedaan is (commit 49cb160a)

Eerst rode tests, dan de reparatie:

- Stap 3 telt per niet-betaalde status (`open`, `herinnerd`, `geescaleerd`) met het statusfilter van de tool. Een mislukte status maakt de telling onbekend; een afkapping wordt nooit gemeld bij 0.
- Alleen een melding van de governance-poort (`kind == "governance"`) telt als klaargezet ticket.
- De CSV houdt `bestand_id` als laatste kolom, naast `bestandsnaam` vooraan.
- `!bon.bevestigd` in plaats van `=== null`.
- Een tabeltest in TypeScript (`bon-controle.test.ts`) koppelt de controleregels aan dezelfde tabellen als de Python-tests.

Bewust niet gedaan, met reden: de kwartaalgrens in Nederlandse tijd (backend en venster zijn onderling gelijk, een randgeval van twee uur per kwartaal); `Number()` vervangen door een eigen bedragparser (het formulier normaliseert bedragen vooraf); een architecture-test die bewaakt dat de skill alleen `list_receivables` aanroept; een `count()` per status (zou lichter zijn, vraagt een nieuwe repositorymethode); de tak splitsen (de vier thema's raken dezelfde schermen).

## Gate 2 -- ronde 2 (commit 49cb160a)

| Reviewer | Oordeel | Opmerkingen |
|---|---|---|
| code-reviewer | GO | De vier herstelpunten doen wat de beschrijving zegt en openen geen nieuw gat; bij telling 0 komt nooit een afkapping. LAAG (opgepakt): de tenant-test keek alleen naar de laatste van drie aanroepen (nu elke aanroep); afkapping alleen getest voor `open` (nu elke status). LAAG (niet opgepakt): drie niet-atomaire aanroepen kunnen een vordering die van status wisselt dubbel tellen (hooguit te veel); een `count()` zou lichter zijn. |

## Mutatiebewijs

35 mutaties in een wegwerp-worktree, alle 35 rood (`mut9.log` in `D:\Dev\ss-backup-avgc-2026-10-13`; map weg, gecontroleerd): 20 in Python (kwartaalregel, jaarwissel, vrije tekst, stap 1 en 2 negeren het kwartaal, telling, statusfilter, telfout, ticketsoort, vrijgave in de uitslag, naam, tijdzone, `bestand_id`, weergavenaam) en 15 in de frontend (melding, sprong naar het kwartaal, labels, regexen, absolute waarde, standaardkwartaal, keuze, meesturen van het kwartaal, tekst van stap 3, weergavenaam). Een overlever (het blok sprong ook naar een kwartaal buiten de keuze; jsdom liet de select terugvallen) is gevangen door de test te versterken met een controle op de opgevraagde kwartalen.
