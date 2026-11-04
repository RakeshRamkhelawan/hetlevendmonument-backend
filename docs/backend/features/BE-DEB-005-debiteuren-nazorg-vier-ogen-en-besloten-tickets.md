# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-005
- **Feature naam:** Debiteuren nazorg -- vier ogen en termijn alleen via de eigen route, besloten tickets zichtbaar, geen dubbel voorstel
- **Status:** Geimplementeerd (Gate 2 ronde 1: GO, zie review-BE-DEB-005)
- **Auteur:** bouwer debiteuren nazorg (tak `iter/debiteurennazorg`)
- **Reviewer:** security-reviewer (subagent, Gate 2, een ronde)
- **Datum:** 2026-10-22
- **Gerelateerde user story / ticket:** meetlat Keten B; brief `docs/agent-briefs/generated/2026-10-22-sprint-dag-debiteuren-nazorg-vier-ogen-en-goedkeuringen.md`
- **Gerelateerde router / module:** `src/core/shared/tenant_instellingen.py`, `src/core/services/tenant_service.py`, `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/tool_broker/hitl_repository.py`, `src/core/tool_broker/hitl_store.py`, `src/core/api/v1/receivables/` (`router.py`, `dependencies.py`)
- **Gerelateerde frontend endpoints:** FE-PGS-035
- **Gerelateerde database tabellen:** `tenants.settings`, `hitl_tickets`. Geen migratie.

---

## Doel en scope

### Doel

Drie gaten dichten die de security-nakijk en de acceptatie van 2026-10-21 op BE-DEB-004 vonden:

1. Een tenantbeheerder kon `four_eyes_actions` en `escalatie_na_dagen` uitdrukkelijk meegeven in
   `PUT /api/v1/tenants/{id}`. Dan won de nieuwe waarde en ging vier ogen uit zonder de controles van de eigen route
   (`PUT /api/v1/tools/hitl/four-eyes`: lijst uit de catalogus, CSRF, rate limit, auditregel `four_eyes_settings_changed`).
2. `/hitl` toonde geen besloten tickets: de geschiedenis kwam alleen uit de beheeraudit, dus een goedkeurder zag niets.
3. Dezelfde vordering kon twee keer worden voorgesteld.

### In scope

- `update_tenant`: de sleutels in `ALLEEN_EIGEN_ROUTE` (`four_eyes_actions`, `four_eyes_explanation_pending`,
  `escalatie_na_dagen`) komen ALTIJD uit de oude waarde. Een meegestuurde waarde wordt genegeerd en gelogd (alleen de
  sleutelnamen en het tenant-id, geen waarden); er komt geen foutmelding. `llm_provider` blijft behouden als hij ontbreekt
  (een uitdrukkelijke waarde wint; zie "Afwijking van de brief").
- `GET /api/v1/tools/hitl/decided`: besloten tickets (approved, consumed, rejected) van de EIGEN tenant, alleen voor de tools
  die de gebruiker mag beslissen, nieuwste besluit eerst, met wie besloot en wanneer. `tool_input` is altijd leeg.
- `POST /api/v1/receivables/reminder-proposals`: een vordering met een openstaand, niet verlopen voorstel krijgt geen
  tweede; de melding is Nederlands en staat in `uitkomsten` van het antwoord.
- Het oude pad `tenant_management/crud_router.py` is gemeten: 0 van 938 routes gemonteerd, en een architectuurtest
  (`test_tenant_management_is_niet_bereikbaar.py`) bewaakt dat. Er is dus niets aan veranderd.

### Out of scope

- Een unieke index of advisory lock tegen gelijktijdige voorstellen (vraagt een migratie; zie "Bewust laten liggen").
- Een nieuwe debiteurenfunctie.

---

## Technische beschrijving

### Architectuur

- `behoud_beheerde_instellingen(oud, nieuw)` en `genegeerde_beheerde_instellingen(oud, nieuw)` in
  `src/core/shared/tenant_instellingen.py`. `update_tenant` leest de tenant met `with_for_update()` en
  `populate_existing=True`, zodat het slot ook werkt op een rij die al geladen is.
- `/decided` gebruikt `get_by_tenant(..., statuses=..., nieuwste_besluit_eerst=True)` en `count_by_tenant(..., statuses=...)`.
  Het tenantfilter blijft altijd het eerste filter; `statuses` en de volgorde voegen alleen toe. Recht: `_require_approver`
  (een willekeurig procesrecht), daarna `tools_the_user_may_decide` per tool.
- `scheid_bestaande_voorstellen(db, tenant_id, receivable_ids)` in `receivables/dependencies.py` (lazy importlib, zodat
  `router.py` het domein governance niet rechtstreeks importeert, ADR-033). Een voorstel telt als openstaand bij status
  `pending`, niet verlopen, tool `send_payment_reminder` en dezelfde tenant.

### Foutafhandeling

- Een genegeerde beheerde instelling is geen fout: de rest van de update gaat door en er staat een waarschuwing in het log.
- Een vordering met een openstaand voorstel krijgt de melding "Er staat al een voorstel klaar voor deze factuur. Beslis
  eerst bij Goedkeuringen." in `uitkomsten`; de andere vorderingen in dezelfde aanvraag gaan gewoon door.

## Acceptatiecriteria

- PUT `/tenants/{id}` met `four_eyes_actions: []` laat vier ogen AAN staan (test: `TestTenantPutLaatBeheerdeInstellingenStaan`).
- `/hitl/decided` geeft besloten tickets van de eigen tenant en niet van een andere, en alleen voor tools die de gebruiker
  mag beslissen (`TestBeslotenTickets`).
- Een tweede voorstel voor dezelfde vordering wordt geweigerd; een besloten, verlopen of vreemd (andere tenant) voorstel
  blokkeert niet (`TestGeenDubbelVoorstel`).

Tests: `tests/integration/test_debiteuren_nazorg_vier_ogen.py` (23), `tests/unit/test_update_tenant_behoudt_beheerde_instellingen.py`.

## Trainingssamenvatting

### Een herinnering voorstellen voor een factuur waar al een voorstel voor klaarstaat

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met het recht om voor te stellen; bij de factuur staat al een voorstel dat nog niet besloten is
- Actie: stelt een betalingsherinnering voor
- Systeemreactie: er komt geen tweede voorstel; de andere facturen in dezelfde aanvraag gaan door
- Succes: bij de factuur staat "Er staat al een voorstel klaar voor deze factuur. Beslis eerst bij Goedkeuringen."
- Fout: zonder het recht om voor te stellen of zonder geldig CSRF-token wordt de aanvraag geweigerd (bestaand gedrag, niet gewijzigd)
- Uitzonderingen: een voorstel dat besloten of verlopen is blokkeert niet; dan mag opnieuw worden voorgesteld

### De besloten goedkeuringen bekijken

- Actor: goedkeurder
- Voorwaarde: ingelogd met een goedkeurrecht voor minstens een soort actie
- Actie: opent de geschiedenis van de goedkeuringen
- Systeemreactie: de besloten tickets van het eigen bedrijf voor de soorten actie die hij mag beslissen, nieuwste eerst
- Succes: wie besloot en wanneer is zichtbaar; de inhoud van de aanvraag niet
- Fout: zonder goedkeurrecht: geen toegang (403)
- Uitzonderingen: tickets van een ander bedrijf komen er nooit in

### Vier ogen of de escalatietermijn wijzigen

- Actor: beheerder
- Voorwaarde: ingelogd als beheerder van het eigen bedrijf
- Actie: past vier ogen aan via de eigen route (`PUT /api/v1/tools/hitl/four-eyes`) of de termijn via de debiteureninstellingen
- Systeemreactie: de wijziging wordt vastgelegd met controle en auditregel
- Succes: de instelling is gewijzigd
- Fout: een wijziging van deze sleutels via de bedrijfsgegevens (`PUT /api/v1/tenants/{id}`) wordt stil genegeerd en in het log gemeld
- Uitzonderingen: andere bedrijfsgegevens in dezelfde aanvraag worden wel bijgewerkt

## Afwijking van de brief

De brief noemt `llm_provider` bij de gemeten sleutels (punt 1) en het besluit spreekt van "sleutels uit
`BEHEERDE_INSTELLINGEN`", waar `llm_provider` bij hoort. Toch is `llm_provider` hier NIET vergrendeld: de beheerder kiest
zijn taalmodel juist via `PUT /tenants/{id}` (er is geen eigen route voor), dus vergrendelen zou die keuze afsluiten. Dit
is een bewuste afwijking van de bouwer, gemeld aan de regie. Een ontbrekende sleutel blijft wel behouden (een PUT
zonder het veld wist hem niet) en een uitdrukkelijke waarde wint, na de bestaande validatie in `tenant_schemas.py`.

## Bewust laten liggen

| Punt                                                                                                              | Reden                                                                                                                                                                                                                                                                                   |
| ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Twee gelijktijdige voorstel-verzoeken kunnen allebei langs de dubbelcontrole komen (LOW, security-review)         | Een echte oplossing is een unieke index of advisory lock per (tenant, vordering); de index vraagt een migratie en die valt buiten de grens van deze dag. Gevolg: een dubbele brief in de wachtrij, geen lek en geen autorisatieprobleem; de goedkeurder ziet beide en kan een afwijzen. |
| Vrije tekst in een afwijsnotitie is zichtbaar voor andere goedkeurders van dezelfde tenant (LOW, security-review) | Bedoeld: de notitie is voor de collega die het besluit leest, en ze blijft binnen de tenant. Het risico is dat iemand persoonsgegevens in de notitie typt; daar is niets technisch aan te beperken zonder de notitie nutteloos te maken.                                                |

## Acceptatie (2026-10-22, onafhankelijke acceptant, met beeld)

Opstelling: backend en Vite uit deze worktree (eee90cc6 plus de menureparatie hieronder), drie accounts in dezelfde tenant
(debiteuren, goedkeurder, beheerder), browser via chrome-devtools. Beelden: `D:\tmp\nazorg-acc\bewijs\` (buiten de repo).
Eindoordeel: **GOEDGEKEURD MET OPMERKINGEN**.

| Punt                         | Uitslag                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Zijbalk per rol           | Eerste ronde: WERKT NIET voor de beheerder (zag ook Goedkeuringen). Oorzaak gemeten: de echte beheerder heeft `['*:*', 'config:approve']` en het menu telde `config:approve` als goedkeurrecht; de test gebruikte alleen `*:*`. Gerepareerd (`heeftEenProcesrechtVoorTickets`, test eerst rood). Herkeuring: beheerder ziet Debiteuren en Instellingen debiteuren maar geen Goedkeuringen, in standaard- en zakelijk menu; debiteuren ziet geen Goedkeuringen; goedkeurder ziet Goedkeuringen in het standaardmenu (het zakelijke menu is in de herkeuring niet opnieuw bekeken). WERKT |
| 2. Geen dubbel voorstel      | Tweede voorstel voor dezelfde factuur gaf "Er staat al een voorstel klaar voor deze factuur. Beslis eerst bij Goedkeuringen."; in /hitl stonden precies twee tickets voor twee facturen. WERKT                                                                                                                                                                                                                                                                                                                                                                                          |
| 3. Besloten tickets op /hitl | Goedgekeurd en afgekeurd (met reden) door de goedkeurder; tellers 0 wachtend, 1 goedgekeurd, 1 afgekeurd; Geschiedenis toont status, wie besloot en de datum; de tijdlijn van de factuur toont wie besloot. WERKT, met opmerkingen hieronder                                                                                                                                                                                                                                                                                                                                            |
| 4. Meldingenscherm           | Kop, knoppen en lege staat in het Nederlands. Er waren geen meldingen, dus "Bekijk details" en de nl-NL-datum zijn NIET met beeld gezien (wel in vitest). Gedeeltelijk getoetst                                                                                                                                                                                                                                                                                                                                                                                                         |

Opmerkingen van de acceptant, niet opgepakt (de brief begrenst tot de vier punten):

- De Geschiedenis toont de ruwe actienaam `send_payment_reminder` en het ruwe ticketnummer `hitl_...`, en bij "wanneer" alleen de
  datum zonder tijdstip.
- De tabbladen Goedgekeurd, Afgekeurd en Alles bestaan niet meer apart: er zijn Wachtende aanvragen en Geschiedenis. Niet
  vastgesteld of dat al zo was voor deze dag; de besloten tickets zijn wel zichtbaar.
- Na goedkeuren stond de factuur nog op Open ("Herinnering klaargezet voor verzending") en kwam er in de paar minuten daarna
  geen mail in Mailpit. In deze opstelling is niet vastgesteld of er een achtergrondwerker draait, dus de oorzaak is niet
  gemeten. Dat de brief echt verstuurd wordt valt onder de meetlat van Keten B, niet onder deze dag.
- Een debiteur toevoegen met een e-mailadres op `.test` geeft 422 en de schermmelding noemt het adres niet; het zakelijke
  dashboard meldt "KPI data kon niet worden geladen" voor het debiteuren-account. Beide buiten de brief.

## Regressierisico's

- Een beheerder die `four_eyes_actions` via `PUT /tenants` wilde wijzigen merkt dat de waarde stil wordt genegeerd (met
  een logregel); de eigen route blijft de weg.
- `get_by_tenant` en `get_tickets_by_tenant_async` kregen nieuwe kwargs; de oude aanroepen zijn ongewijzigd (de kwargs
  worden alleen doorgegeven als ze gebruikt worden, anders breekt de Mock-repository in `test_tool_broker_hitl.py`).

## Niet gemeten

- Of de debiteurenagent de sleutel `receivable_id` altijd in de payload van het ticket schrijft (de dubbelcontrole leest
  die sleutel); gemeten met een ticket dat in de integratietest wordt aangemaakt, niet over alle producenten.
- Of een beheerder via `PUT /tenants` met `llm_provider` een extern model kan kiezen terwijl `data_residency` op eu-only
  staat (de validatie in `tenant_schemas.py` is bestaand gedrag en niet nagelopen).
- Gedrag onder echte gelijktijdigheid (zie het eerste punt bij "Bewust laten liggen").
