# Backend Feature Review -- BE-DEB-004

## Metadata

- **Review ID:** review-BE-DEB-004
- **Feature ID:** BE-DEB-004
- **Feature naam:** Debiteuren rondt zichzelf af -- bankafschrift, escalatietermijn, geen brief na betaling, verloop per factuur
- **Reviewer:** security-reviewer (subagent, Gate 2, twee rondes). De code-reviewer is voor deze dag NIET ingezet: de brief vroeg de security-reviewer.
- **Datum:** 2026-10-20
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED

Ronde 1 (sha 10ef17c6): CHANGES_REQUESTED, 1 HIGH, 3 MEDIUM, 3 LOW. Alles verwerkt.
Ronde 2 (sha bf317355): CHANGES_REQUESTED, 3 MEDIUM, 1 LOW. Alles verwerkt in fab3090a, en elk punt is eerst aan de code
getoetst. Een derde ronde door de bouwer is niet gedaan (grens: twee rondes).
Gerichte review door de regie (2026-10-20) op `bf317355..fab3090a`: **GO**. N1, N3 (alle drie de schrijvers) en N4 zijn
opgelost, N2 grotendeels; de regie vond daarbij twee restpunten (F1, F2) en een meetpunt (pgcode). Die zijn hieronder
verwerkt (sectie B, "Gerichte review"); daarmee is de status APPROVED. De reparaties van F1 en F2 zelf zijn niet door een
reviewer nagelopen (zie sectie E).

## B. Bevindingen en wat ermee is gedaan

### Ronde 1

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| CPU: aantal bijschrijvingen niet begrensd, lineaire scan per bijschrijving | HIGH | Opgelost: `MAX_BIJSCHRIJVINGEN`, index op (valuta, bedrag), tests |
| Geheugen: boom van een groot plat bestand voor het parsen | MEDIUM | Opgelost: `MAX_TAGS` voor het parsen |
| Retour of eigen debet binnen een creditregel telde als betaling | MEDIUM | Opgelost: `_is_terugboeking`, tests |
| Race bij gelijktijdig afvinken | MEDIUM | Opgelost in ronde 1 met een rijslot; bleek in ronde 2 onvolledig (N1) |
| Lost update op `tenants.settings` | LOW | Opgelost in ronde 1 voor de nieuwe schrijver; onvolledig (N3) |
| Notitie in de tijdlijn kan persoonsgegevens bevatten | LOW | Opgelost: afgekapt op 200 tekens |
| E-mailopzoeking zonder tenantfilter | LOW | Opgelost: `tenant_id`-parameter, alle aanroepers geven hem mee |

### Ronde 2

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| N1: rijslot werkt niet als de sessie de rij al kent (geen `populate_existing`) | MEDIUM | Bevestigd rood met een test, opgelost |
| N2: koppelwerk begrensd door bedrag, niet door aantal; regex per factuur; parsen op de event loop | MEDIUM | Opgelost: plafond `MAX_VERGELIJKINGEN` voor het afvinken, substring-voorfilter, lezen in een thread. `MAX_TAGS` niet verlaagd (zie onder) |
| N3: vier-ogen-schrijvers nemen geen slot en overschrijven de hele JSON | MEDIUM | Bevestigd rood met een test, opgelost in alle drie de schrijvers |
| N4: tegengestelde lock-volgorde met de verzendlus; bestandsvolgorde binnen een upload | LOW | Opgelost: afvinken in id-volgorde, 409 bij deadlock of lock-timeout. De volgorde bericht-dan-vordering van de worker is niet aangepast |

### Gerichte review door de regie (op `bf317355..fab3090a`)

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| F1: `TenantService.update_tenant` (bereikbaar via `PUT /api/v1/tenants/{id}` voor een beheerder van de eigen tenant) zette `settings` als geheel terug; alleen `llm_provider` bleef. Een ontbrekende vier-ogen-sleutel betekent UIT: een gewone wijziging zette vier ogen stil uit en wiste de escalatietermijn | MIDDEL | Eerst rode test, daarna opgelost: rijslot met verse rij, en `behoud_beheerde_instellingen` (`src/core/shared/tenant_instellingen.py`) laat `four_eyes_actions` (ook een lege lijst), `four_eyes_explanation_pending`, `escalatie_na_dagen` en `llm_provider` staan tenzij uitdrukkelijk meegegeven. Een test houdt de sleutels gelijk aan die van hun eigenaren |
| F2: de koppellus draaide op de event loop met maximaal 5.000.000 vergelijkingen en `lower()` per kandidaat | LAAG-MIDDEL | Eerst rode tests, daarna opgelost: de koppellus draait in `asyncio.to_thread`, `lower()` een keer per bijschrijving, plafond `MAX_VERGELIJKINGEN` verlaagd naar 500.000 |
| Meten: bestaat `exc.orig.pgcode` echt bij asyncpg? | LAAG | Gemeten met een echte deadlock tussen twee verbindingen op PostgreSQL (`TestEchteDeadlock`): `pgcode` is `40P01`. De 409-tak klopt |

Gemeten slechtste geval van F2 (afschrift met 1000 bijschrijvingen van 500 tekens, 500 facturen met hetzelfde bedrag,
precies op het plafond; terwijl er een volledige testronde meedraaide, dus eerder te hoog dan te laag):

| Geval | Tijd |
|---|---|
| 500.000 vergelijkingen, nooit een match | 0,53 s |
| 500.000 vergelijkingen, het voorfilter slaagt vaak (omschrijving vol factuurnummers; de omschrijving is op 500 tekens afgekapt, dus hoogstens ongeveer 40 nummers per bijschrijving) | 1,10 s |
| 600.000 vergelijkingen (boven het plafond) | 0,13 s, geweigerd `TE_VEEL_WERK` |
| 5000 transacties tegen 5000 facturen met een ander bedrag | 0,24 s |
| 199.000 tags parsen (net onder `MAX_TAGS`) | 0,60 s |

Dit alles draait nu in een thread en blokkeert de event loop niet; een ander verzoek wacht er niet op.

## C. Bewust gelaten

- Het vorderingsslot in de uploadroute en de volgorde bericht-dan-vordering van de verzendlus: zie N4.
- `MAX_TAGS` blijft 200.000: een echt afschrift met 5000 transacties heeft ongeveer 60.000 tags, en de reviewer stelde
  ongeveer 50.000 voor. Dat zou een geldig groot afschrift weigeren. De parse draait nu wel buiten de event loop.
- De worker houdt het vorderingsslot tijdens het versturen van de e-mail (SMTP); een afvinkpoging op die ene factuur
  wacht dan tot de mail klaar is. Niet gewijzigd: raakt de verzendlus van een eerdere dag.
- `omschrijving` uit het afschrift komt in het antwoord terug (control-tekens zijn gestript). Of de frontend dat veilig
  rendert is niet apart nagelopen; React escapet tekst standaard.

## D. Mutatiebewijs

24 mutaties in een wegwerp-worktree op fab3090a, elk met de bewakende test: alle 24 gevangen (rood). Twee mutaties waren
in een eerste meting NIET gevangen (tagtelling en tenantfilter bij het ophalen van de lijst); de tests zijn daarna
scherper gemaakt en opnieuw gemeten. Niet te mutatietesten, want gedragsgelijk: het substring-voorfilter in `_komt_voor`.

## E. Niet getoetst

- De reparaties van F1 en F2 zijn door mij getest (rode tests, daarna groen) maar niet opnieuw door een reviewer nagelopen.
- Gelijktijdig afvinken met twee echte verbindingen; de rijslot-tests bootsen de verse-rij-situatie na in een sessie. Een echte deadlock is wel gemeten (alleen de foutcode).
- Het geheugen onder het plafond en onder `MAX_TAGS`. De rekentijd van het slechtste geval is wel gemeten (sectie B).
- Rechten van de applicatierol (RLS) voor `FOR UPDATE` op `tenants`.
- Een tijdlijntest met een auditregel van een andere tenant op dezelfde resource.
