# Backend Feature Review -- BE-DEB-005

## Metadata

- **Review ID:** review-BE-DEB-005
- **Feature ID:** BE-DEB-005
- **Feature naam:** Debiteuren nazorg -- vier ogen en termijn alleen via de eigen route, besloten tickets zichtbaar, geen dubbel voorstel
- **Reviewer:** security-reviewer (subagent, Gate 2, een ronde). De code-reviewer is voor deze dag NIET ingezet: de brief vroeg de security-reviewer.
- **Datum:** 2026-10-22
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED

Ronde 1 (sha eee90cc6, bereik d054a114..eee90cc6): GO. Geen CRITICAL of HIGH, twee LOW. Er is geen tweede ronde nodig
geweest; de LOW-punten zijn bewust blijven liggen (sectie C).

## B. Bevindingen en wat ermee is gedaan

| Bevinding | Ernst | Afhandeling |
|---|---|---|
| Twee gelijktijdige voorstel-verzoeken kunnen allebei langs `scheid_bestaande_voorstellen` komen (geen lock of unieke index) | LOW | Bewust gelaten, zie C |
| `/decided` toont `requested_by_email` en de vrije tekst van afwijsnotities aan elke goedkeurder van die tool in de eigen tenant | LOW | Bewust gelaten, zie C |

De reviewer controleerde onder meer: alle schrijvers van `tenants.settings` (de eigen route, `debiteuren_instellingen.py`,
`update_tenant`, `create_tenant`, en het oude `crud_router.py` dat niet gemonteerd is), het tenantfilter en de rechtencontrole
van `/decided`, de projectie (`tool_input` altijd leeg), paginering en rate limit, en dat de dubbelcontrole geen
gegevens van een andere tenant prijsgeeft (vaste weigertekst, bindparameters, `receivable_ids` is `list[int]` met een maximum
van 20).

## C. Bewust gelaten

- **Gelijktijdig voorstellen (LOW).** Een oplossing (partiele unieke index op pending-tickets per tenant en vordering, of een
  advisory lock) vraagt een migratie en de brief sluit die uit. Het gevolg is een dubbele herinneringsbrief in de
  wachtrij, die de goedkeurder ziet en kan afwijzen; geen lek en geen autorisatieprobleem.
- **Vrije tekst in een afwijsnotitie (LOW).** Bedoeld gedrag binnen de eigen tenant; zonder de notitie weet de collega niet
  waarom een voorstel is afgewezen.

## D. Mutatiebewijs

In een wegwerp-worktree (detached op eee90cc6), een mutatie per element, steeds de bewakende test draaien en daarna
`git checkout --` in die worktree. Controlegroep ongemuteerd: 13 geslaagd. Alle 20 mutaties werden gevangen (ROOD):

- N01 `four_eyes_actions` uit de vergrendelde lijst; N02 onbekende sleutel niet verwijderd; N03 oude waarde niet behouden;
  N04 genegeerde sleutels niet gemeld; N05 geen logregel in `update_tenant`; N14 tenant-PUT zonder `behoud_beheerde_instellingen`.
- N06 toolfilter weg op `/decided`; N07 `tool_input` lekt; N08 statusfilter weg (beide plekken tegelijk).
- N09 besloten voorstel blokkeert; N10 tenantfilter weg bij de dubbelcontrole; N11 verlopen voorstel blokkeert; N12 route
  start ook de al voorgestelde vorderingen; N13 dubbel meegestuurd id niet ontdubbeld.
- Frontend (FE-PGS-035): F01 t/m F06, zie review-FE-PGS-035.

Niet gemuteerd: de rate limit en de paginering op `/decided` (niet nieuw gedrag van deze dag).

## E. Niet getoetst

- Of de debiteurenagent `receivable_id` in elke payload schrijft; de reviewer vertrouwt op het bestaande gebruik van
  `payload["receivable_id"].astext` in `hitl_repository.py` en las de agentcode niet.
- De redactiecode die na een besluit de payload opschoont (OP-47), de testbestanden en de draaiende applicatie (de
  acceptatie is apart gedaan, zie de spec).
- Of een beheerder via `PUT /tenants` een extern model kan kiezen terwijl `data_residency` op eu-only staat.
