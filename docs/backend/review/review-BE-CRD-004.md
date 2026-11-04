STATUS: APPROVED
# Backend Feature Review -- BE-CRD-004

**De acceptatie met beeld staat onderaan; tot die er is, is dit document NIET af.**

## Metadata

- Feature ID: BE-CRD-004
- Feature naam: Crediteuren nazorg: intrekken na goedkeuren, niets blijft stil liggen, een IBAN hoort bij een leverancier, een vaste Nederlandse reden bij een mislukte uitvoering
- Review datum: 2026-10-27
- Reviewers: code-reviewer, quality-reviewer en security-reviewer (Gate 2, een ronde, alleen lezen en meten op de werkboom `iter/crediteuren-nazorg`); de bouwer mat elke bevinding na voordat hij haar overnam
- Spec locatie: `docs/backend/features/BE-CRD-004-crediteuren-nazorg-intrekken-verlopen-iban.md`

---

## Eindoordeel Gate 2

**GO** na verwerking. Beveiliging: GO (geen CRITICAL of HIGH). Kwaliteit: GO (alle meters op de baseline). Code: CHANGES_REQUESTED met een MEDIUM en zeven LOW; alles verwerkt of bewust gelaten, hieronder.

## Bevindingen en wat ermee is gedaan

| Bevinding | Gemeten | Afhandeling |
|---|---|---|
| Code MEDIUM-1 en beveiliging B (LOW): een tweede intrekking op de ticketverwijzing van een OUD voorstel kan de goedkeuring van een NIEUW voorstel ongedaan maken (de facturen staan weer op `goedgekeurd`) | gelezen: het ticket werd nergens als ingetrokken gemerkt | hersteld: bij intrekken gaat `_betaalrun_facturen` uit het ticket en komt `_betaalrun_ingetrokken` erin (zelfde transactie); twee bewakingen die elkaar dekken. Test `test_a_second_withdrawal_of_an_old_ticket_does_not_release_the_invoices_of_a_newer_run` |
| Beveiliging A (MEDIUM): bij een race tussen het betaalbestand en intrekken wordt een voorstel maar half ingetrokken en dat staat niet in het antwoord | gelezen uit de SQL (niet uitgevoerd) | hersteld: zit een factuur van het voorstel al in een bestand, dan gaat er niets terug (rollback, 409). Test `test_a_run_of_which_one_invoice_is_already_in_a_file_is_not_withdrawn_at_all` |
| Beveiliging C (LOW): de reden gaat na de commit door `_schoon`; faalt dat, dan een 500 na een vastgelegd besluit; en `_schoon` maskeert alleen herkende persoonsgegevens | gelezen | hersteld voor het eerste deel (schoonmaken vooraf, vlak voor de commit). Het tweede deel (namen in vrije tekst) blijft: de reden gaat alleen naar het auditlog, nooit terug naar de klant; AVG-restrisico gemeld |
| Code LOW-4: een IBAN-botsing bij het uitvoeren na goedkeuren geeft geen vaste zin | gelezen | hersteld: `IbanAlInGebruik` (eigen soort van `ValidatieFout`), code `iban_al_in_gebruik` en een vaste zin |
| Code LOW-5: de zinnen beloofden "worden opnieuw voorgelegd", maar de agent doet dat niet vanzelf | gelezen | hersteld: "kunnen opnieuw worden voorgelegd: vraag de crediteurenagent om een nieuw voorstel" |
| Code LOW-7: toegankelijkheid van het formulier (focus, `aria-describedby`, `aria-invalid`) | gelezen | hersteld: focus naar het veld bij openen en terug naar de knop bij sluiten; uitleg en fout gekoppeld |
| Code LOW-8: een testbestand stond niet gestaged | `git status` | gestaged en gecommit |
| Code LOW-2: de knop "Goedkeuring intrekken" staat ook bij een goedgekeurd voorstel waarvan de uitvoering mislukte (status `consumed`, geen binding) en bij voorstellen van voor deze wijziging | aanname over de frontend-data | niet gewijzigd: de server weigert dan fail-closed met 409 en een Nederlandse uitleg ("... waarvan bekend is welke facturen erbij horen. Trek de facturen een voor een in"). Het scherm kan de twee soorten niet onderscheiden zonder een nieuw veld; open punt |
| Code LOW-6: intrekken zet ook een factuur die `ontvangen` was op `gecontroleerd` | gelezen | niet gewijzigd: `ontvangen` kan rechtstreeks naar `goedgekeurd` (de brief laat beide toe) en de werkelijke vorige status wordt niet bewaard; een factuur die weer voorgesteld wordt is toch al een menselijk besluit. Open punt voor de regie |
| Code LOW-3: de SQL met `jsonb_build_object` en bindparameters is niet op een echte database aangetoond | gemeten | de integratietests lezen `_betaalrun_facturen` terug uit een echte PostgreSQL (poort 5455) en bewijzen ook het weghalen van de sleutel |
| Kwaliteit LOW: `zetStand` ongebruikt in `PayablesPage.tsx:243` | niet in deze diff gewijzigd (bestond al) | niet gewijzigd |

## Metingen

- Eigen testdatabase `crd_agent`, `-p no:xdist`: 36 integratietests (`test_crediteuren_nazorg.py`) en 12 unit (`tests/unit/payables/test_crediteuren_nazorg.py`) en 35 repository (`test_payable_repository_betaalrun.py`, waarvan 12 nieuw voor intrekken en het IBAN) groen.
- Gate 3: `ruff check src/` schoon, `python -m pyright` 0 errors (90 bestaande waarschuwingen), `scripts/run_mypy_audit.py` 0, Any-ratel 7025 gelijk aan de baseline, bandit op de gewijzigde bestanden zonder bevindingen, geen non-ASCII (scan op bytes > 127 over alle 26 gewijzigde bestanden), tsc 0, eslint 0 fouten.
- **Mutatiebewijs** op een wegwerp-werkboom (kopie als terugweg): 25 backend-mutanten. 23 direct rood, met per punt een mutant in beide richtingen (een legitiem geval mag niet weigeren: een IBAN in een andere tenant, dezelfde leverancier op een IBAN, een nog open ticket houdt de upload vast, een totaal van een leverancier). M09 (de markering "ingetrokken" weghalen) en M24 (de binding laten staan) bleven elk los GROEN omdat die twee bewakingen elkaar dekken; de gecombineerde mutant M25 (beide weg) is ROOD. 6 van 7 frontendmutanten rood; F7 (het slot tegen een dubbelklik via een ref) blijft in jsdom groen omdat het uitschakelen van de knop via state in dezelfde omgeving hetzelfde doet (gelijkwaardig in de testomgeving; in een echte browser is het slot het eerste vangnet).
- Volledige testronde met het slot en acceptatie met beeld: zie onderaan.

## Taak 0 (de brief): draait de uurlijkse opruimtaak in een gedeployd proces?

Ja volgens de uitrol: `docker-compose.yml:287-293`, `docker-compose.prod.yml:198-201`, `docker-compose.dev.yml:138` (entrypoint `python -m src.workers.scheduler`), `cd-production.yml` (`scheduler-prod`) en `cd-staging.yml` (`scheduler-staging`); de job `hitl_ticket_cleanup` loopt elk uur op :15 (`scheduler.py`). Commando: `grep -rn scheduler docker-compose*.yml .github/workflows/*.yml`. **Niet gemeten:** of die containers NU draaien. De verouderde docstring in `hitl_repository.py` ("nul aanroepers") is rechtgezet.

## Niet gemeten

- Dat de scheduler-containers draaien; echte gelijktijdigheid met meerdere API-workers (de atomaire UPDATE is getoetst in een proces en uit de SQL gelezen).
- Een bank en een telefoonscherm.

## Open ontwerppunten voor de regie

Een intrekknop op een voorstel waarvan de uitvoering mislukte; een ingetrokken `ontvangen` factuur wordt `gecontroleerd` (de vorige status wordt niet bewaard); een melding of escalatie bij een verlopen ticket is er niet (de brief vroeg alleen om zichtbaar als verlopen en opnieuw voorleggen).

## Acceptatie met beeld

Onafhankelijke acceptant in een echte browser, 2026-10-27, op een eigen schone database (`crd_agent`, poort 5455; de ontwikkeldatabase is niet aangeraakt), API en dev-server vanuit de werkboom `iter/crediteuren-nazorg` (commit b2106d2a). Beelden: `D:\tmp\crd-acceptatie4\` (reeks 10 tot 33; de beelden 01 horen bij een eerste poging die mislukte door mijn opstart: de dev-server miste `VITE_API_URL`, daarna hersteld en van voor af aan herhaald). Twee gebruikers: een crediteur (mag niet goedkeuren) en een goedkeurder.

**Uitslag: GOEDGEKEURD MET OPMERKINGEN.** Alle negen stappen WERKEN:

| Wat | Uitslag | Beeld |
|---|---|---|
| Twee leveranciers en drie facturen vastleggen, op gecontroleerd zetten | WERKT | 11 |
| Een derde leverancier met het IBAN van een bestaande: Nederlandse weigering die 'Acceptatie A BV' noemt; de leverancier is niet toegevoegd | WERKT | 12, 13 |
| Betaalvoorstel laten maken: "legt 3 facturen voor ... EUR 1.550,00", link naar de goedkeuringen | WERKT | 14 |
| De kaart Betaalvoorstel bij de goedkeurder met afgeschermde IBAN's; goedkeuren zet de drie facturen op Goedgekeurd met een knop Intrekken | WERKT | 15, 16, 17 |
| Factuur intrekken: een te korte reden zet bevestigen uit; met een geldige reden "Factuur AC-3 is ingetrokken en afgewezen." en status Afgewezen; de crediteur ziet GEEN Intrekken-knop | WERKT | 18 tot 21 |
| Voorstel intrekken in de Geschiedenis: "2 facturen zijn vrijgegeven ..."; AC-1 en AC-2 weer Gecontroleerd, AC-3 blijft Afgewezen | WERKT | 22 tot 24 |
| Mislukte uitvoering (IBAN van een leverancier gewijzigd na het voorstel): een BLIJVENDE melding op de pagina met de vaste zin ("... Er is niets goedgekeurd; de facturen kunnen opnieuw worden voorgelegd ..."), ook na 10 seconden; de facturen staan niet op Goedgekeurd | WERKT | 25 tot 28 |
| Verlopen: de aanvraag staat als verlopen zonder knoppen; een nieuw voorstel zegt "Het vorige voorstel is eerder voorgelegd, niet op tijd beoordeeld" | WERKT | 29, 30 |
| Betaalbestand halen; daarna het voorstel intrekken: Nederlandse weigering dat het bestand eenmalig is | WERKT | 31 tot 33 |

**Opmerkingen van de acceptant en wat ermee is gedaan:**

1. Na het intrekken van een voorstel blijft de regel in de Geschiedenis op "Goedgekeurd" staan met de knop "Goedkeuring intrekken" (een tweede poging geeft een weigering). **Open punt:** het scherm kan een ingetrokken voorstel niet zien zonder een nieuw veld in `tool_input`/het antwoord.
2. Een goedkeuring die niet is uitgevoerd telt mee onder "Vandaag goedgekeurd" en staat als Goedgekeurd in de Geschiedenis. **Open punt, bestaand gedrag** (`consumed`): het besluit is wel genomen, de uitvoering niet.
3. De toast noemde een ticketnummer en zei "is goedgekeurd" naast "er is niets goedgekeurd". **Hersteld** (commit na deze acceptatie): bij een vaste zin van de server toont de toast alleen "Het besluit is vastgelegd, maar de actie is niet uitgevoerd. <zin>", zonder ticketnummer; getoetst in `useHITL.toasts.test.tsx`.
4. "Op dit moment is er niets aan de beurt" staat naast "legt 3 facturen voor": klopt (de facturen staan al in een open voorstel), maar de zin wordt niet toegelicht. Open punt, bestaand gedrag van `BetaalSectie`.
5. Verlopen aanvragen zijn alleen te zien onder het filter "Alles"; de standaardweergave "Wachtend" telt ze niet mee. Open punt, bestaand gedrag (de brief vroeg "zichtbaar als verlopen in de wachtrij"; het standaardfilter verbergt ze).
6. Na het ophalen van het bestand staat "Er zijn nog geen goedgekeurde facturen"; logisch, wel een vreemde combinatie met de melding. Bestaand.
7. Engelse koppen op het Dashboard ("Live Activity", "Pending Approvals", "Agent Reasoning"). Bestaand, buiten deze brief.
8. Smal venster (circa 750 px): horizontaal scrollen en afgeknipte kolommen; niet op een breed scherm gemeten.

**Niet gemeten:** het gedownloade XML-bestand zelf (inhoud niet geopend door de acceptant; het XSD-bewijs staat in review-BE-CRD-003), schermen op een breed scherm, een telefoon.

## Volledige testronde met het slot

Volgt.
