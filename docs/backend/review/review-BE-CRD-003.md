STATUS: APPROVED
# Backend Feature Review -- BE-CRD-003

**Gate 2 is GO en de toets tegen het XSD is groen (2026-10-27).** Het schemabestand komt niet van iso20022.org zelf (403 voor een script) maar is byte-voor-byte gelijk in vijf onafhankelijke projecten (OCA/bank-payment, hbci4java, php-sepa-xml, python-sepaxml, sepa.js; sha256 05440a7e84f695e7dbc6677082f43623cd7393881b76a5e8d648ae21d7d728e3). Zie "Wat open staat".

## Metadata

- Feature ID: BE-CRD-003
- Feature naam: Crediteuren dag 3: de agent stelt de betaling voor, een mens keurt goed (vier ogen boven het drempelbedrag), er komt een SEPA-betaalbestand
- Review datum: 2026-10-26
- Reviewers: security-reviewer en code-reviewer (subagents), twee rondes Gate 2 op de werkboom van `iter/crediteuren-dag3-wip` (alleen lezen); de bouwer mat elke bevinding na voordat hij haar overnam
- Spec locatie: `docs/backend/features/BE-CRD-003-crediteuren-dag3-betaalvoorstel-en-betaalbestand.md`

---

## Eindoordeel Gate 2

**GO** na ronde 2 van beide reviewers (geen CRITICAL, geen HIGH). Ronde 1: security NO-GO (een HIGH die bij nameting niet bleek te bestaan, zie hieronder, maar waarvan de verdediging in de diepte is gebouwd), code GO.

## Bevindingen ronde 1 en wat ermee is gedaan

| Bevinding | Gemeten | Afhandeling |
|---|---|---|
| Security 1, HIGH: iedere gebruiker kan via `POST /hitl/request` een eigen betaalvoorstel-ticket maken met `vier_ogen_vereist: false` en dat zelf goedkeuren | **Het pad bestaat niet.** `src/core/tool_broker/router.py` heeft nul importeurs (de docstring van `api/v1/tool_broker/hitl_router.py` zegt het zelf) en de andere ticketmakers (Co-Pilot, workflow-uitvoering, achtergrond- en bestuurspoort) werken met `HITLTicketRepository.create_hitl_request`, dat de toolpermissie van de uitvoerende identiteit toetst; `propose_payment_run` staat alleen in het profiel `crediteuren` en de identiteit komt uit `self.agent_id` van de skill, niet van een model | Toch hersteld wat goedkoop en nuttig was: (a) vier ogen wordt in de HITL-route uit de DATABASE bepaald (`payment_run_registry.vier_ogen_nodig`: bedragen en drempel, fail-secure), niet meer uit de vlag in het ticket; (b) `_controleer_regels` toetst naam en factuurnummer tegen de database; (c) een test dat de identiteit `copilot` geen betaalvoorstel kan maken (mutant M24 rood) |
| Security 2, MEDIUM: drempel per factuur, geen totaal (100 facturen net onder 2.500 EUR) | gemeten (ontwerp) | besluit regie 2026-10-26: vier ogen ook als het TOTAAL boven de drempel komt; gebouwd (selectie en `vier_ogen_nodig`), met tests en de mutanten M27 en M28 |
| Security 3, MEDIUM: `ontvangen` facturen komen ook in een voorstel | gemeten (ontwerp) | niet gewijzigd: de brief zegt "gecontroleerd of ontvangen"; open punt aan de regie |
| Security 4 / code 5, MEDIUM: een verlopen `pending` ticket houdt zijn facturen voor altijd vast | gemeten | hersteld: `_al_voorgesteld` telt `pending` alleen met `expires_at > nu` en `approved` alleen binnen 15 minuten; test en mutant M11 |
| Security 5, LOW: IBAN-bescherming bij het bestand steunt op `updated_at` | gemeten, geaccepteerd | een directe SQL-update zonder `updated_at` ligt buiten de app |
| Security 6, LOW: geen vingerafdruk van het bestand in het logboek | gemeten | hersteld: `bestand_sha256` in `payment_file_created`; test en mutant M14 |
| Code 2, MEDIUM: een gewijzigde leverancier blokkeert het bestand voor alle facturen en de factuur kan niet terug | gemeten | hersteld in twee stappen (ronde 1 en 2): alleen die factuur gaat niet mee; hij wordt teruggezet naar `gecontroleerd`, zodat de agent hem opnieuw kan voorstellen en een mens hem opnieuw goedkeurt met het nieuwe IBAN; alleen als niets overblijft is er geen bestand (dan wordt het terugzetten wel vastgelegd); tests en mutanten M12, M13 |
| Code 3, MEDIUM: de Nederlandse reden bij een mislukte uitvoering bereikt de goedkeurder niet | gemeten in de docstring van de HITL-route | niet gewijzigd in dag 3; opgelost in de nazorg (BE-CRD-004, vaste Nederlandse zin per code) |
| Code 4, MEDIUM: `checked_by` en `checked_at` worden overschreven, `ontvangen` slaat `gecontroleerd` over | gemeten | bewust: vastgelegd in de docstring van `keur_goed_voor_betaling`; de auditregel `payment_run_approved` bewaart wie goedkeurde |
| Code 6, LOW: `maak_tekst` laat o-slash, l-streep en sz stilletjes verdwijnen | gemeten | hersteld met een vertaaltabel (als `\u`-tekens); parametrische test en mutant M22 |
| Code 1/7/8 (frontend) | gemeten | hersteld: download niet meer afgebroken door een te vroege `revokeObjectURL` en een mislukte download meldt niet "niet gemaakt" maar biedt het laatste bestand opnieuw aan; "ten minste N" bij een volle lijst; overgeslagen facturen zichtbaar; zie review-FE-PGS-039 |

## Ronde 2

Beide reviewers: GO. Open uit ronde 2, niet gewijzigd: (1) security 1 MEDIUM, een model-gestuurde `agent_id` "crediteuren" in het achtergrondpad: gemeten dat beide aanroepers `self.agent_id` meegeven (de sleutel van de skill uit de catalogus) en dat `_prepare_tool_params` elke parameter vervangt door de selectie uit de database; (2) `src/core/tool_broker/main.py` hangt het ongemonteerde router-bestand aan een eigen app, die nergens wordt gestart (geen verwijzing in compose, CI of Dockerfile); (3) vier ogen wordt bij goedkeuren bepaald en niet opnieuw bij uitvoeren: een tijdvenster waarvoor schrijfrecht op de factuur en een vals ticket nodig zijn; (4) code 4 en 5 LOW: een naam of factuurnummer dat de inhoudswachter zou maskeren (gemeten: de wachter blokkeert alleen IBAN's en kaartnummers, geen namen) en het venster van 15 minuten voor `approved`.

## Metingen

- Integratie (eigen database `crd_agent`, `-p no:xdist`): 65 geslaagd (laatste volledige run 63, twee mislukt door een technisch veto van de Council onder last, los groen) (`test_crediteuren_betaalvoorstel_en_betaalbestand.py`), na twee eerdere runs met een enkele mislukte test door een databaseverbinding die onder de last van een meting van een andere sessie wegviel (los groen).
- SEPA-unit 43, repository 19 (isolatie per methode), gerichte vitest 252 en 38 voor de betaalsectie.
- Gate 3: ruff, pyright (0), mypy-audit (0 na herstel van drie eigen fouten), Any-ratel gelijk aan de baseline, tsc 0, eslint 0 fouten.
- Mutatiebewijs op een wegwerp-werkboom (kopie als terugweg): 24 mutanten die het slot moeten laten houden (horizon, statusfilter, grens van vier ogen in beide plekken, fail-secure, IBAN-digest, bedrag, naam, factuurnummer, verlopen ticket, leverancier gewijzigd, terugzetten, vingerafdruk, repositoryfilters, tenantfilters, bedragnotatie, IBAN-controle, controlesom, tekenvertaling, vier ogen in de route, het profiel van de Co-Pilot) en 4 mutanten die een legitiem geval niet mogen weigeren: alle 28 rood; basis 121 groen zonder mutatie. Na de laatste reparatie (teruggezette facturen) zijn M12 en M13 opnieuw gemeten (rood) en twee nieuwe mutanten toegevoegd: M25 (het terugzetten wordt niet vastgelegd als er geen bestand komt) en M26 (een teruggezette factuur kan niet opnieuw worden voorgesteld): beide rood. Daarna het totaal-criterium voor vier ogen (besluit regie 2026-10-26): M27 en M28 (het totaal telt niet mee, in de selectie en in de route) en M29 en M30 (een totaal exact op de drempel vraagt vier ogen): alle vier rood. Totaal 34 rood.
- Acceptatie door een onafhankelijke acceptant in een echte browser, met beeld in `D:\tmp\crd-acceptatie3\`: ronde 1 AFGEKEURD om een omgevingsfout (de ontwikkeldatabase mist `tenant_noodstop`, waardoor de Council dichtklapte), ronde 2 op een eigen schone database GOEDGEKEURD MET OPMERKINGEN: voorstel, tweede voorstel geweigerd, de crediteur kan niet goedkeuren, goedkeurkaart met afgeschermde IBAN's en gele vier-ogenmelding, goedkeuren, fout eigen IBAN geweigerd en facturen blijven goedgekeurd, bestand gedownload en van schijf gelezen (3 transacties, juiste bedragen en IBAN's, geen adres), facturen op `in_betaalbestand`, afwijzen met reden van minstens 10 tekens.

## Wat open staat

1. **De XSD-toets** (`tests/integration/test_pain001_valideert_tegen_xsd.py`): 7 tests groen (2026-10-27, eigen database `crd_agent`); mutatie (volgorde `NbOfTxs`/`CtrlSum` in `PmtInf` omgedraaid) maakt er 4 rood, daarna teruggezet. `xmlschema` 4.3.2 en `elementpath` 5.1.4 staan gepind in `requirements-test.txt`.
2. Volledige ronde na de merge met develop `4e6f0ef7` (met het testslot, 2026-10-27): `tests/unit tests/architecture tests/core tests/contracts` 28386 geslaagd, 20 gefaald in 2 u 20 onder zware belasting van andere sessies; 18 los herhaald: 17 geslaagd (werkers gecrasht, of een test die in een worktree niet kan werken omdat `.git` daar een bestand is), 1 echt: `test_vier_ogen_instelling_api` telde 9 vier-ogenacties en dag 3 voegt `propose_payment_run` toe (10): hersteld. Integratie 65: 62 en 64 geslaagd in twee volle runs (3 resp. 1 mislukt onder belasting, alle los groen). Vitest 987 bestanden, 15408 tests geslaagd.

## Open ontwerppunten voor de regie

Bestand eenmalig en niet te herbouwen (geen migratie; `HITLTicketRepository.approve` vervangt de payload); `ontvangen` facturen in een voorstel (bevestigd door de regie); de reden van een mislukte uitvoering bereikt de goedkeurder niet (opgelost in BE-CRD-004); een afwijs- of herbeoordeelpad voor een goedgekeurde factuur ontbreekt (opgelost in BE-CRD-004: intrekken); welke bank welke pain.001-versie accepteert is niet gemeten; de ontwikkeldatabase mist de noodstop-migratie.

## Niet gemeten

- Dat een bank het bestand inleest (banken kunnen strenger zijn dan het schema).
- Echte gelijktijdigheid met meerdere API-workers (de atomaire UPDATE is getoetst met twee gelijktijdige aanvragen in een proces).
- Vier ogen als dezelfde persoon in het scherm probeert goed te keuren (alleen in de integratietest, niet in de browser) en een drempel die afwijkt van de standaard in het scherm.
