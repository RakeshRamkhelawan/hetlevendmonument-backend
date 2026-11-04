# ADR-039: Rollen en bevoegdheden in drie lagen -- beheer is niet hetzelfde als beslissen

## Status

Accepted (Rakesh, 2026-10-04)

## Datum

2026-10-04

## Auteur

Claude (rol architect), op verzoek van de regie, op basis van de besluitrichting van Rakesh
van 2026-10-04. Dit is een voorstel. Alleen Rakesh zet de status op `Accepted`.

**Review-datum:** 2026-11-03 (30 dagen). Staat dit dan nog op `Proposed`, dan vraagt het een
besluit of verwijdering.

**Geen juridisch advies.** Wat hieronder over de AI-verordening en de AVG staat, is een
technische lezing van openbare bronnen. Een jurist moet de open vragen in paragraaf 9
beoordelen voordat een klant erop vertrouwt.

---

## 1. Samenvatting in gewone taal (een halve pagina)

**Het probleem.** Vandaag is er in de applicatie in feite een soort sleutel: "beheerder".
Wie beheerder is, mag instellingen wijzigen, mensen toevoegen EN een brief van de agent
goedkeuren. Dat zijn drie verschillende dingen. In een bedrijf met 160 mensen is dat niet
te gebruiken: de ICT-afdeling die inlogt en koppelingen beheert, is niet de persoon die
beslist of een aanmaning de deur uit gaat. En er is nergens een bedragsgrens: iedereen met
de sleutel mag alles goedkeuren, groot of klein.

**Het voorstel: drie lagen.**

1. **Platformbeheer** -- ons eigen personeel. Staat buiten elke klant, zit niet standaard in
   een klantomgeving, en elke keer dat iemand van ons bij klantgegevens kijkt, staat dat
   in een logboek.
2. **Beheer door de klant** -- opgesplitst in *technisch* (ICT: inloggen, koppelingen,
   geheimen) en *functioneel* (de key-user: instellingen, sjablonen, drempels, rollen
   inrichten, agents aan of uit, en per agent een mens aanwijzen die erop toeziet).
   Iemand een rol geven is een beheerhandeling en wordt vastgelegd, inclusief WIE het deed.
3. **Procesrollen** -- wie mag in een proces (bijvoorbeeld debiteuren) iets voorstellen,
   uitvoeren, beslissen of alleen inzien, en tot welk bedrag. Goedkeuren is hier een
   bevoegdheid met een grens, en geen beheerrecht.

**De agent is een co-piloot.** Hij werkt altijd namens een medewerker en kan nooit meer dan
die medewerker. De mens beslist, tenzij de wet echt toestaat dat een agent het zelf doet.

**Vier ogen is een instelling, geen wet.** Een bedrijf met 160 mensen zet het aan vanaf een
bepaald bedrag. Een zzp'er (Fatima) kan het bewust uitzetten: dan bevestigt ze zelf, dat
staat in het logboek, de brief vertrekt pas na een wachttijd, en er is een grens per dag.

**Besluit Rakesh, 2026-10-04 (aanvulling, gaat voor waar het hierboven afwijkt).** Letterlijk:
"governance en compliance rust bij de gebruiker". Uitgewerkt en door hem akkoord bevonden:

1. **Mens-in-de-lus is altijd aan bij een riskante agentactie.** Wie de agent startte, mag
   die actie zelf goedkeuren. De applicatie ondersteunt de werkwijze van de gebruiker; zij
   legt geen werkwijze op.
2. **Vier ogen is een instelling die de gebruiker zelf zet**, per workflow of per actie, in
   de workflowmodule (die de gebruiker samen met de copilot opstelt). Staat het aan, dan
   moet een ANDER de beslissing nemen. In het mkb is dat vaak zo verdeeld: een medewerker
   doet de debiteuren, een collega accordeert. Bij een zzp'er is er geen tweede paar ogen.
   Sjablonen mogen het standaard aanzetten voor geldzaken (betalen, IBAN wijzigen,
   afboeken, overdracht aan incasso); de gebruiker beslist.
3. **Agent2Agent: altijd mens-in-de-lus.** Een agent keurt nooit het verzoek van een andere
   agent goed.
4. **Blijft altijd:** goedkeuren alleen binnen de eigen onderneming, met het recht daarvoor,
   en elke beslissing met tijdstip in het logboek.

Gevolg voor de code: `_refuse_self_approval` (`src/core/api/v1/tool_broker/hitl_router.py`)
weigert nu elke zelfgoedkeuring. Dat wordt: weigeren alleen als vier ogen voor die
workflow/actie aan staat, of als de aanvrager een agent is. De wachttijd en daglimiet voor
het eenmansbedrijf (hierboven) zijn daarmee geen eis meer, hooguit een instelling.

**Standaardinstelling vier ogen (Rakesh, 2026-10-05: "mee eens").** In de sjablonen staat
vier ogen standaard AAN voor HR-acties (Annex III), betalingen, IBAN wijzigen, afboeken en
overdracht aan incasso; standaard UIT voor herinneringen en aanmaningen. De gebruiker kan
elk van deze instellingen zelf wijzigen.

**Bestaande ondernemingen (Rakesh, 2026-10-05).** Ook bestaande ondernemingen krijgen deze
standaard, eenmalig, "zolang het bij het inrichten van de onderneming wel duidelijk wordt
gemaakt wat de keuzes zijn". Dus: bij het inrichten (en bij de eerste keer na deze
wijziging voor een bestaande onderneming) legt het scherm per actie in gewone taal uit wat
vier ogen betekent, wat de standaard is en dat een zzp'er het zelf kan uitzetten.
Er moeten nog veel gebruikersscenario's bij komen in `docs/meetlat.md`; de gebruiker
stelt zijn workflow zelf op, met of zonder AI, en de AI helpt alleen bij het opstellen.

**Een model, drie maten.** We bouwen niet drie systemen. We bouwen een model voor het
middelgrote bedrijf en leveren standaardinstellingen voor zzp (een persoon, rol Eigenaar),
klein (Jeroen, 6 mensen) en middelgroot. Afschalen kan altijd beter dan opschalen.

**Identiteit blijft bij de klant.** Heeft het bedrijf Microsoft 365 (Entra), dan vertalen we
hun groepen naar bevoegdheden. Wij bouwen geen personeelsadministratie. Kleine klanten
loggen in met Google of Microsoft.

**Waar beginnen we.** Bij wat de debiteurenagent (dag 2) het eerst nodig heeft: de
goedkeurcontrole verandert van "is dit een beheerder?" naar "heeft deze persoon de
bevoegdheid voor dit bedrag in dit proces?". Dat raakt het bewust omheinde werk niet. Twee
stappen raken dat wel (het opsplitsen van platform- en klantbeheer, en het samenvoegen van
de drie rechtenstelsels); die starten pas op Rakesh zijn woord.

**Twee mogelijke gaten** (A en B in paragraaf 2) zijn gelezen maar niet getest. Een
testspecialist toetst ze nu. Dit ADR trekt daar geen conclusie over.

---

## 2. Context en probleem (alleen wat in deze sessie is nagelezen)

Peildatum: commit `42e79df0` (2026-10-04). "Gelezen" betekent: de code is geopend en de
regel bekeken. Er is in deze sessie NIETS uitgevoerd tegen een draaiende applicatie.

### 2.1 Bevindingen die ik zelf heb gecontroleerd

| Bevinding | Bewijs (commando of plek) |
|---|---|
| `is_admin` is waar bij superuser-vlag OF rolnaam in `{admin, system_admin, tenantadmin}`, hoofdletterongevoelig. Laag 1 en laag 2 zijn dus dezelfde vraag. | `src/core/auth/dependencies.py:540` (`ADMIN_ROLE_NAMES`), `:543-` (`is_admin`), `:664-669` (`_has_admin_role_name`). Lezen. |
| Goedkeuren van een HITL-ticket is een beheerrecht. De docstring zegt zelf: "Dit is de beheerdersrol en niet een echte goedkeurdersrol, en dat is een tekort." Zelfgoedkeuring wordt wel geweigerd. | `src/core/api/v1/tool_broker/hitl_router.py:102-135` (`_require_approver` roept `is_tenant_admin` aan), `:141-` (`_refuse_self_approval`). Lezen. |
| Die router wordt WEL gemount, ondanks de docstring ("wordt vandaag niet geserveerd"). De docstring is verouderd. | `src/core/api/registries/optional.py:14-17`. Lezen; niet gedraaid. |
| Een vast woordenboek met rechten per rolnaam, los van de database. | `src/core/auth/rbac.py:66-95` (`ROLE_PERMISSIONS`: user, moderator, admin, system_admin). Lezen. **Bijgewerkt 2026-10-09 (OP-143): de vaste matrix bestaat niet meer; tools lezen `role_permissions`.** |
| De configuratie zegt zelf dat de `role_permissions`-tabel daar niet gelezen wordt. | `src/core/config/tool_risk_levels.yml:99-101` (let op: het pad is `src/core/config/`, niet `config/`). Lezen. **Bijgewerkt 2026-10-09 (OP-143): de vaste matrix bestaat niet meer; tools lezen `role_permissions`.** |
| Het token krijgt scopes afgeleid van de rolnaam. | `src/core/api/auth/router_login.py:134-161` (`_get_user_scopes`). Lezen. |
| Rollen worden per tenant gemaakt door de tenant zelf, en `create_role` kent geen lijst van gereserveerde namen. | `src/core/api/v1/rbac/roles_router.py:66-103`; `src/core/services/rbac_service.py:~535-557` (`Role(tenant_id=..., name=name, ...)` zonder naamcontrole). Lezen. |
| Een roltoekenning wordt gelogd met de DOEL-gebruiker als `user_id`, niet de uitvoerder. | `src/core/services/rbac_service.py:~419-430`. Lezen. |
| De gezaaide platformbeheerder krijgt de tenant-rol `admin`. | `src/core/app_lifespan.py:~186-230`. Lezen. |
| `system_admin` mag via `?override_tenant_id=` een andere tenant lezen. | `src/core/api/admin_digital_twin.py:37-51` (let op: het pad is `src/core/api/`, niet `v1/admin/`). Lezen. |
| De drempels en goedkeurdersrollen in `governance_v2/intelligence_levels.py` worden buiten het pakket alleen her-geexporteerd, niet aangeroepen. | `git grep -n "intelligence_levels\|APPROVER_ROLES" -- src` geeft alleen `governance_v2/__init__.py:13`. Of er aanroepers in `tests/` zijn, is niet nagelopen. |
| Er is geen bedrag- of aantallimiet op een mens of rol in het goedkeurpad. | Afgeleid uit het lezen van `hitl_router.py`; geen zoekopdracht naar alle limietbegrippen gedaan. Beschouw als "niet gevonden", niet als "bewezen afwezig". |
| De open punten staan in het register. Totaal open op 2026-10-04: 78. | `python scripts/list_adr036_open_items.py` (laatste regel: "Totaal open: 78"). |

### 2.2 Volgens de verkenner, NIET nagemeten door mij

- 333 endpointaanroepen via `require_scopes`/`user_has_permission`; 308 tekstgrep-treffers
  op `is_admin|is_tenant_admin|require_admin|admin:*|ADMIN_ALL` in 67 bestanden.
- Standaardrollen admin/editor/user voor elke tenant (`rbac_service.py:809-909`), niet per
  pakket; `user_roles` heeft geen `tenant_id`; de RLS-policy van migratie
  `20261004_user_roles_rls` werkt alleen onder een niet-eigenaar-verbinding (OP-151).
- Identiteit: alleen wachtwoord plus eigen JWT's; geen Google/Microsoft/SAML/OIDC, geen
  groepskoppeling, geen SCIM; MFA bestaat als model maar hangt niet aan login; geen
  uitnodigingsflow; twee gebruikersrouters (OP-224).
- Toolprofielen zijn globaal (2 profielen); `execute_tool` toetst de agent, niet de gebruiker;
  na goedkeuring gebruikt de broker de agent-identiteit (`hitl_repository.py:462-520`).
- Geen toezichthouder per agent, geen vastlegging van AI-geletterdheid, geen inzagerol.
- Baseline: 552 tests geslaagd; hotspots `auth/dependencies.py` (59 commits),
  `auth_service.py` (52), `rbac_service.py` (45), `rbac_models.py` (46), `app_lifespan.py` (50).

### 2.3 Twee mogelijke ernstige gaten -- WORDT GETOETST, geen conclusie

- **A.** `src/core/api/v1/feature_flags/admin_router.py:40-97` neemt `target_tenant_id` uit
  een queryparameter, zet `app.current_tenant` op die waarde en schrijft onder
  `TenantFilterBypass`, met als enige toegangscontrole `require_admin`. Gelezen. Of een
  tenantbeheerder hiermee werkelijk een andere tenant kan wijzigen, is NIET gemeten.
- **B.** Omdat `create_role` geen gereserveerde namen kent (hierboven) en `is_admin` op de
  rolnaam `system_admin` vertrouwt, KAN een tenantbeheerder mogelijk een rol met die naam
  aanmaken. Of de rest van de keten dat doorlaat, is NIET gemeten.

Een testspecialist toetst beide apart. De fasering (paragraaf 6, F0) wacht op die uitslag.

### 2.4 Waarom een ADR en niet gewoon bouwen

Er ligt geen ADR over het rollenmodel (`docs/adr/000-adr-index.md`). De keuze raakt
identiteit, autorisatie, de agent-broker, audit en de klantopzet, en bouwt voort op het
vastgelegde "tenant_id uit de JWT" zonder daarvan af te wijken. Daarom is het geen
binnen-een-domein wijziging.

---

## 3. Besluit

### Kernprincipe

**Beheer van de applicatie en uitvoering van een proces zijn twee verschillende werelden met
twee verschillende soorten rechten; wie een agent of rol mag inrichten, mag daarmee nog niets
goedkeuren, en een agent kan nooit meer dan de mens voor wie hij werkt.**

### 3.1 Drie lagen

**Laag 1 -- Platformbeheer (ons personeel).**
- Is een eigenschap van het account (`platformbeheerder`), en GEEN rolnaam in de rolnamen van
  een tenant. Daarmee verdwijnt de naam `system_admin` als vertrouwde tekst in klantrollen.
- Zit niet standaard in een klantomgeving en komt niet voor in klantbesluiten (bevoegdheden,
  goedkeuringen).
- Toegang tot klantgegevens loopt via een bewuste, tijdelijke toegangssessie met reden;
  elke sessie en elke handeling erin staat in het auditlog (SHA-256-keten, zoals nu).
- `override_tenant_id` en gelijkaardige doorgangen verdwijnen op termijn naar die sessie.
- In een single-tenant opzet (ADR-035) op de server van de klant is de klant zelf de
  beheerder; laag 1 bestaat daar alleen als wij op afstand ondersteunen.

**Laag 2 -- Beheer door de klant, in twee delen.**
- *Technisch beheer* (ICT): inloggen en SSO, koppelingen (Exact Online, AFAS, TOPdesk),
  geheimen, verbindingsinstellingen. Geen inhoudelijke bevoegdheid in processen.
- *Functioneel beheer* (key-user): instellingen, sjablonen, drempels, rollen inrichten,
  agents aan/uit, de bevoegdhedenmatrix invullen, en per agent een **toezichthouder** (een
  met naam aangewezen mens) vastleggen.
- Een roltoekenning of wijziging van de bevoegdhedenmatrix is een beheerhandeling:
  geauditeerd met de **uitvoerder** (actor) en het **doel**, met oude en nieuwe waarde. De
  lijst van beheerders mag nooit leeg raken en de laatste beheerder kan zichzelf niet
  verwijderen.
- Een beheerder die zichzelf bevoegdheden in een proces geeft, is mogelijk (bij zzp
  noodzakelijk), maar wordt als zodanig gemarkeerd in het logboek.

**Laag 3 -- Procesrollen en bevoegdheden.**
Per processtap een bevoegdheid met een handeling:

| Handeling | Betekenis |
|---|---|
| inzien | de gegevens zien, niets beslissen |
| voorstellen | een actie klaarzetten (dit is wat de agent altijd doet) |
| uitvoeren | een goedgekeurde of onschuldige actie laten gebeuren |
| beslissen | goedkeuren of afkeuren, met een **limiet** |

De bevoegdheid hangt aan een **rol** (of een gekoppelde groep) en heeft een **limiet**
(bedrag, eventueel aantal per dag) uit de bevoegdhedenmatrix van de klant. Standaard is
alles wat niet is toegekend **verboden** (default-deny). Een inzagerol (controleur, FG, externe
accountant) heeft alleen "inzien" en beslist nooit iets.

### 3.2 Vier begrippen die nu door elkaar lopen

| Begrip | Vraag die het beantwoordt | Voorbeeld |
|---|---|---|
| **Recht (scope)** | Mag deze code/dit scherm bereikt worden? | `agents:write` |
| **Rol** | Welke bundel rechten en bevoegdheden hoort bij een functie? | Debiteurenadministrateur |
| **Bevoegdheid met limiet** | Mag deze persoon DIT in DIT proces tot DIT bedrag? | Aanmaning goedkeuren tot 5.000 euro |
| **Toezichthouder** | Wie is de met naam aangewezen mens die op deze agent let? | De controller voor de debiteurenagent |

Een recht opent een deur; een bevoegdheid bepaalt wat je daarbinnen mag beslissen. Dat zijn
twee controles, en de tweede is de nieuwe.

### 3.3 Wat een agent mag

1. Een agent werkt altijd **namens** een medewerker (on-behalf-of). Zijn bevoegdheid is het
   **minimum** van (a) wat die medewerker mag en (b) wat het toolprofiel van de agent
   toestaat. Meer dan de mens kan hij niet.
2. Een agent **stelt voor**; een mens **beslist**. Uitzondering: handelingen waarvan de klant
   expliciet heeft vastgelegd dat ze zonder mens mogen EN die volgens de wet zonder mens mogen
   (paragraaf 9). Zonder zo'n vastlegging: nooit.
3. Bij een voorstel worden zowel de aanvrager (mens) als de agent vastgelegd. Bij de
   goedkeuring wordt opnieuw gecontroleerd of de aanvrager de bevoegdheid nog heeft (een recht
   dat is ingetrokken tussen voorstel en uitvoering, geldt niet meer).
4. De goedkeurder krijgt de **volledige inhoud** te zien (wat, aan wie, welke tekst).
   Een goedkeuring zonder zicht op de inhoud is een formaliteit en wordt niet als beslissing
   gerekend (zie AVG art. 22 en meetlat scenario 5).
5. Een agent zonder aangewezen toezichthouder kan niet worden aangezet.

### 3.4 Functiescheiding (vier ogen) is een instelling

Per actie en per bedragsklasse stelt de klant in: *vier ogen vanaf bedrag X*, *altijd*, of
*nooit*. De standaard hangt af van de grootte (3.6). Zelf-beslissen door de aanvrager is
alleen toegestaan als de instelling dat zegt, en dan gelden vier voorwaarden:

1. een **expliciete bevestiging** met reden, vastgelegd in het logboek;
2. een **wachttijd** voordat een brief of betaling werkelijk vertrekt, met annuleren mogelijk;
3. een **limiet per dag** (aantal en bedrag);
4. de boekhouder of een andere aangewezen persoon kan **optioneel meekijken**.

Dit is een bewuste uitzondering voor het eenmansbedrijf, geen standaard voor wie meer mensen
heeft. Is er in de organisatie meer dan een persoon met beslisbevoegdheid, dan staat vier ogen
standaard aan boven een instelbaar bedrag.

### 3.5 Identiteit: hun systeem is de bron

- Microsoft 365 / Entra ID: inloggen via OIDC; groepen worden vertaald naar rollen en
  bevoegdheden via een koppeltabel `groep -> rol` per tenant. Bij inloggen wordt de rol
  bijgewerkt (just-in-time). Zo vervalt een rol zodra de groep vervalt.
- Klein en zzp: inloggen met Google of Microsoft; zonder bedrijfsmap kent de beheerder rollen
  met de hand toe.
- Wij bouwen **geen** personeelsadministratie: geen afdelingen, contracten of
  organogram-bron. De bron is de klant.
- Aanname (zie paragraaf 8): SCIM is voor de pilot niet nodig; groepskoppeling bij inloggen is
  genoeg.

### 3.6 Standaardinstellingen per grootte -- configuratie, geen aparte code

Een profielbestand per grootte vult bij het aanmaken van de omgeving de rollen, de matrix en
de instellingen. De code is overal dezelfde.

| Instelling | zzp (Fatima) | Klein (Jeroen, 6) | Middelgroot (Hoogland, 160) |
|---|---|---|---|
| Rollen | Eigenaar (een persoon, alle lagen) | Eigenaar, Medewerker, Boekhouder (extern, inzien) | Volledige set: directeur-eigenaar, financieel manager, controller, debiteurenadministrateurs, ... key-users per afdeling, ICT-manager, applicatiebeheerders, security officer, inzagerollen |
| Technisch vs. functioneel beheer | samengevoegd in Eigenaar | samengevoegd in Eigenaar | gescheiden |
| Vier ogen | uit, met bewuste uitzondering (3.4) | aan vanaf een bedrag | aan vanaf bedrag per processtap |
| Wachttijd voor externe brief | aan | aan | optioneel |
| Toezichthouder per agent | Eigenaar | Eigenaar | aangewezen per agent, met instructie |
| Inloggen | Google/Microsoft | Google/Microsoft | Entra-groepen |
| Limiet per dag | strikt | strikt | per rol |

De exacte rolnamen en bedragen zijn startwaarden. Hoogland (160 medewerkers) is een
verzonnen voorbeeldbedrijf om het model aan te toetsen, geen echte klant.

### 3.7 Gevolg voor de debiteurenagent

Debiteuren komen binnen via zelf invoeren, import of boekhoudkoppeling. Het model kijkt niet
naar de herkomst voor de bevoegdheid, maar de herkomst wordt per debiteur vastgelegd, want
een handmatig ingevoerde schuld is minder betrouwbaar dan een uit de boekhouding
gesynchroniseerde. Processtappen en bevoegdheden voor dat proces:

| Stap | Agent | Mens |
|---|---|---|
| Overzicht verlopen facturen | voorstellen/inzien | inzien |
| Herinnering versturen | voorstellen | beslissen tot limiet, of "uitvoeren" zonder beslissing onder de klein-drempel |
| Aanmaning / dreigbrief | voorstellen | beslissen (hoger niveau), vier ogen volgens instelling |
| Betalingsregeling treffen | voorstellen | beslissen |
| Afboeken / kwijtschelden | voorstellen | beslissen, aparte (hogere) bevoegdheid |
| Uit handen geven aan incasso | voorstellen | beslissen, aparte bevoegdheid |

---

## 4. Kwaliteitsattributen (ISO 25010)

| Attribuut | Gewicht | Toelichting en spanning |
|---|---|---|
| Beveiliging (vertrouwelijkheid, onweerlegbaarheid) | Hoog | Splitsen van lagen en default-deny sluit de brede beheerderssleutel. Kost: meer te configureren, dus meer kans dat een klant te veel of te weinig toekent. |
| Bruikbaarheid | Hoog | Een zzp'er mag niet door een matrix heen hoeven. Daarom profielen met standaarden. Spanning: elke extra instelling is voor Fatima ruis. |
| Onderhoudbaarheid | Hoog | Een model met profielen in plaats van drie code-takken. Kost: het model moet generiek genoeg zijn voor 160 medewerkers en toch klein beginnen. |
| Functionele geschiktheid | Hoog | Het debiteurenproces kan niet tegen een klant verkocht worden zonder een bedraggrens op goedkeuren. |
| Compatibiliteit (inpassing) | Midden | Entra-groepen en Google/Microsoft-login betekenen dat de klant niets dubbel hoeft te beheren. |
| Betrouwbaarheid / migreerbaarheid | Midden | Het huidige gedrag (`is_admin` overal) mag niet breken; expand-en-contract (paragraaf 5.2). Kost: tijdelijk twee systemen naast elkaar. |
| Prestatie | Laag | Een bevoegdheidscontrole is een opzoeking per aanvraag; met de bestaande cache/RLS-context geen verwacht probleem. Niet gemeten. |

Kernspanning: **meer scheiding betekent meer te configureren.** We kopen dat af met
standaardprofielen, en met "afschalen" als ontwerpregel: begin met een persoon die alles mag
en haal alleen wat nodig is uit elkaar.

---

## 5. Alternatieven

### 5.1 Overwogen en afgewezen

| Alternatief | Waarom niet |
|---|---|
| **Alleen de huidige beheerdersrol houden** | Goedkoopst op korte termijn, en juist daarom aantrekkelijk. Maar: goedkeuren valt dan samen met beheren (de eigen docstring noemt dit een tekort), er is geen bedraggrens, en een middelgroot bedrijf kan de ICT-afdeling niet scheiden van de financieel manager. Eerste klant is middelgroot-achtig en het debiteurenproces vraagt een bedraggrens. |
| **Een vaste goedkeurdersrol zonder limiet** | Lost "beheerder is niet goedkeurder" op, maar niet "wie mag welk bedrag". Een directeur en een stagiair-met-goedkeurrol zijn dan even machtig. Mist ook de uitzondering voor het eenmansbedrijf: die heeft er een rol bij nodig die niet bestaat. |
| **Per grootte een eigen model bouwen** | Drie codepaden, drie testsets, en de overstap van klein naar middelgroot wordt een migratie. Rakesh zijn uitgangspunt is expliciet: afschalen vanuit een model. Profielen als configuratie bereiken hetzelfde met een derde van de kosten. |
| **Eigen personeelsadministratie bouwen** | Dubbel beheer voor de klant (HR-systeem en onze lijst lopen uit elkaar), veel scope, en AVG-last voor gegevens die we niet nodig hebben. Hun identiteitssysteem is al de bron; groepen vertalen is genoeg. |
| **Vier ogen als vaste regel** | Een zzp'er heeft niemand voor het tweede paar ogen; de regel zou het product onbruikbaar maken en vragen om omzeilen met een tweede account. Een instelling met bewuste uitzondering (bevestiging, wachttijd, daglimiet) behoudt de bescherming waar die kan en maakt de uitzondering zichtbaar waar die moet. |
| **Alle rechten in de bestaande `role_permissions`-tabel stoppen en daarbij blijven** | Een rij met alleen een scope kan geen limiet en geen processtap uitdrukken. Het zou drie stelsels in een tabel proppen zonder het probleem op te lossen. Dat is wel de bestemming voor het samenvoegen in F8, niet het antwoord op de goedkeurvraag. |

### 5.2 Hoe we migreren zonder de huidige beheerders te breken (expand en contract)

1. **Uitbreiden:** de nieuwe bevoegdheidscontrole komt ERNAAST. In een overgangsstand geldt:
   `is_admin` => alle bevoegdheden zonder limiet. Zo verandert er voor bestaande beheerders
   niets, en de nieuwe tabellen zijn leeg en onschadelijk.
2. **Omschakelen per proces:** een proces (eerst debiteuren) gaat over op de nieuwe controle,
   ingeschakeld met een instelling per tenant. Terugdraaien is een instelling, geen
   migratie.
3. **Versmallen (contract):** pas als alle processen de nieuwe controle gebruiken en de
   klanten hun matrix hebben ingevuld, wordt de overgangsregel (`is_admin` => alles) per
   proces verwijderd.

Elke stap is afzonderlijk omkeerbaar. Migraties krijgen een werkende `downgrade()`;
tabelwijzigingen zijn een interlock-1-onderwerp en worden vooraf aangekondigd.

---

## 6. Gefaseerd plan

Legenda: **BINNEN** = raakt het omheinde werk niet; **RAAKT HET OMHEIDE** = raakt het
P0-autorisatiecluster of het RLS/applicatierol-cluster (OP-190, OP-192, OP-193, OP-143, OP-174,
OP-151, OP-113, OP-224) en start pas op Rakesh zijn woord. Rolverdeling volgt de sprint-dag:
testspecialist schrijft eerst rode tests, bouwer bouwt, database doet migraties.

| Fase | Wat | Omheind? | Klaar als (meetbaar) | Rollen |
|---|---|---|---|---|
| **F0** | Uitslag van de toets op gat A en B afwachten. Bij bevestiging: gereserveerde rolnamen (`system_admin` kan niet door een tenant worden aangemaakt) en doel-tenant niet meer uit een queryparameter. | **RAAKT HET OMHEIDE** als bevestigd (valt in het P0-cluster en bij OP-192). Zolang niet getoetst: niets bouwen. | Rode tests uit de toets worden groen; `git grep` toont geen nieuwe tenant-uit-queryparameter. | testspecialist, dan bouwer na Rakesh zijn woord |
| **F1** | Bevoegdheidsvocabulaire en -controle: tabel/model voor (rol, proces, stap, handeling, limiet), een functie `heeft_bevoegdheid(...)`, overgangsregel `is_admin` => alles. Alleen toevoegen. | **BINNEN** | Unit-tests: default-deny, limiet-grens, overgangsregel; isolatietest tenant A vs B; `python -m pyright` blijft 0; migratie met werkende `downgrade()`, `alembic heads` toont 1. | testspecialist, database, bouwer |
| **F2** | **Debiteurenagent dag 2:** de goedkeurcontrole in de HITL-keten verandert van `_require_approver` (is beheerder) naar `heeft_bevoegdheid(beslissen, debiteuren, stap, bedrag)`, plus vier-ogen-instelling en controle van de aanvrager bij uitvoering. Achter een instelling per tenant. Alleen debiteurenstappen. | **BINNEN**, met grens: de negen aanroepplekken zonder ticket (OP-174) en de RLS-context na commit (OP-113) worden niet aangeraakt; raakt de wijziging die toch, stoppen en melden. | Rode test eerst: een niet-beheerder met bevoegdheid tot 5.000 kan 4.999 goedkeuren en 5.001 niet; een beheerder zonder bevoegdheid kan niet goedkeuren (zodra de instelling aan staat); afkeuren stopt de actie echt (meetlat scenario 5). | testspecialist, bouwer |
| **F3** | Auditregel met actor voor roltoekenning, rolwijziging en matrixwijziging. | **BINNEN** | Test toont dat het auditveld de uitvoerder bevat (niet het doel) en dat een rechtwijziging van een rol een auditregel geeft (gelezen: nu niet). | testspecialist, bouwer |
| **F4** | Standaardprofielen zzp / klein / middelgroot als configuratiebestanden; toepassen bij het aanmaken van een omgeving en bij single-tenant opstart (ADR-035). | **BINNEN**, let op het opstartpad (`app_lifespan.py`, hotspot) | Test: elk profiel levert de verwachte rollen en matrix op; een zzp-omgeving heeft een Eigenaar die kan beslissen met bevestiging, wachttijd en daglimiet. | testspecialist, bouwer |
| **F5** | Toezichthouder per agent met vastgelegde instructie en datum van kennisname; agent aanzetten kan niet zonder. | **BINNEN** | Test: een agent zonder toezichthouder weigert te starten; de vastlegging staat in het auditlog. | testspecialist, bouwer |
| **F6** | Identiteit: Microsoft/Google-login en groepskoppeling Entra -> rol (JIT). | **BINNEN**, behalve het afleiden van scopes uit rolnaam (`router_login.py`), dat grenst aan OP-143 | Een testgebruiker met Entra-groep krijgt de verwachte rol; een verwijderde groep ontneemt de rol bij volgende login. Niet voor de pilot als dat niet past (paragraaf 8). | bouwer, testspecialist |
| **F7** | Laag 1 en laag 2 echt splitsen: `platformbeheerder` als accounteigenschap, geen tenant-rol `admin` voor het platformaccount, toegangssessie met reden en audit, `override_tenant_id` erin opnemen. | **RAAKT HET OMHEIDE** (OP-192, OP-190, OP-151) | Het platformaccount heeft geen tenant-rol; elke cross-tenant lezing geeft een auditregel met reden. | testspecialist, database, bouwer, op Rakesh zijn woord |
| **F8** | Drie rechtenstelsels (DB-tabel, vast woordenboek, token-scopes) samenvoegen; overgangsregel `is_admin` => alles per proces verwijderen (contract). | **RAAKT HET OMHEIDE** (OP-143, OP-192) | Een bron van waarheid; `git grep` op tekstliteralen voor adminschap daalt gemeten naar de goedgekeurde uitzonderingen. | alle rollen, op Rakesh zijn woord, na de pilot |

**Stand 2026-10-09 (besluit Rakesh: "een beheerder heeft niets te maken met een proces dat geaccordeerd
moet worden" en "in een klein bedrijf mag 1 persoon alle rollen beslaan").** Gebouwd, in de eenvoudigste
vorm die dat besluit dekt; de tabel hierboven blijft het eindbeeld.

- **F1 (deels):** geen aparte bevoegdhedentabel maar een goedkeurrecht per proces in de bestaande
  database-RBAC: `receivables:approve` en `hr:approve` (`src/core/auth/approval_rights.py`). De actie
  `approve` is EXPLICIET (`EXPLICIT_ACTIONS` in `rbac_service.py`): `*:*` van de beheerder geeft het niet.
  Standaardrol `goedkeurder` (`receivables:read`, `receivables:approve`, `tools:read`); er is nog GEEN
  standaardrol met `hr:approve` en geen limiet per bedrag (nog open).
- **F2 (deels):** `_require_approver` in `tool_broker/hitl_router.py` en `gatekeeper/gatekeeper_hitl_router.py`
  toetst dat recht, per actie (tool of agent van het ticket); een onbekende actie wordt geweigerd. Zelfgoedkeuring
  en vier ogen zijn ongewijzigd. Open: bedragslimiet, stap-per-stap bevoegdheid, instelling per tenant.
- **F7 (deels):** een platform-superuser of `system_admin` keurt niets goed via `is_admin`; alleen een
  procesrecht in DE tenant telt. Open: het platformaccount zelf zonder tenant-rol, toegangssessie met reden.
- **Besluit Rakesh 2026-10-10 voor de vier HIGH-tools zonder proces:** `serena__admin_config` gaat naar de
  BEHEERDER (inrichten, geen proces): expliciet recht `config:approve`, alleen aan de rol `admin` gezaaid
  en niet via `*:*`. `local__send_email`, `serena__delete_document` en `delete_task` gaan naar de rol
  `goedkeurder` via het algemene recht `governance:approve`. Tweede standaardrol `goedkeurder_hr`
  (`hr:approve`) voor personeel. Een ticket voor een HIGH-tool of agent zonder regel in
  `approval_rights.py` is voor NIEMAND beslisbaar (fail-closed); de bewaker kent geen uitzonderingslijst.
- **Bekende gevolgen (Gate 2, 2026-10-10):** (1) zie hierboven. (2) Een toewijzing van een rol komt nu met
  de TOEWIJZER in de auditregel (`role_assigned`, `assigned_by`). (3) Bestaande beheerders verliezen het goedkeuren bij uitrol tot iemand de rol
  `goedkeurder` krijgt; geen migratie die dat koppelt. (4) `/hitl/audit` blijft beheerders-leesroute.
  (5) De missiestap-goedkeuring (`missions/lifecycle_router.py`) is scope-gebaseerd en niet aangeraakt.
- Bewaker: `tests/architecture/test_goedkeurrecht_per_actie.py`; gedrag: `tests/integration/test_goedkeuren_is_een_procesbevoegdheid.py`.

**Volgorde voor de pilot (december 2026).** F1, F2, F3, F4 en F5 zijn BINNEN en vormen het
minimum voor de debiteurenpilot. F6 is gewenst als de pilotklant Entra heeft. F0, F7 en F8
wachten op Rakesh. Tijdschattingen heb ik niet gemaakt: er is geen meting van doorlooptijd per
fase, dus de regie moet die per brief inschatten.

---

## 7. Gevolgen en risico's

- **Hotspots.** `auth/dependencies.py` (59 commits), `rbac_service.py` (45), `auth_service.py`
  (52), `rbac_models.py` (46) en `app_lifespan.py` (50) zijn volgens de verkenner de meest
  gewijzigde bestanden; het zijn precies de bestanden die F1-F4 raken. Verwacht samenloop en
  werk in een eigen worktree. Het aantal commits is niet door mij nagemeten.
- **Impacttests.** De verkenner meldt 68 impacttests voor de omschakeling en 552 geslaagde
  tests in de baseline. Ik heb dat niet nagemeten. Het expand-en-contract-pad is gekozen
  juist zodat deze tests in F1-F5 niet breken.
- **Het opstartpad.** Het opstarten zaait nu een beheerder met de rol `admin`
  (`app_lifespan.py`). F4 verandert wat een nieuwe omgeving bevat. Een fout daar maakt een
  omgeving onbruikbaar na een herstart: een test op een verse database is verplicht.
- **Migraties.** Nieuwe tabellen en kolommen vallen onder interlock 1 (migratie): vooraf
  aankondigen en een werkende `downgrade()`.
- **Meer configuratie, meer fouten.** Een te ruime matrix is nog steeds een gat. Mitigatie:
  default-deny, profielen, en een controlescherm "wie mag wat" (later; geen aanname dat het in
  de pilot past).
- **Voorrang van het omheinde werk.** F7 en F8 lossen de kern van het probleem pas helemaal op.
  Tot dan blijft de wereld dubbel: nieuw model voor processtappen, oude beheerderssleutel
  voor de rest. Dat is een bewust, tijdelijk risico.
- **Schaal.** Een middelgroot bedrijf heeft veel rollen; de matrix kan groot worden.
  Niet gemeten op omvang of snelheid.

---

## 8. Wat niet gemeten is (en aannames met toets)

Niet gemeten of niet nagelezen:

- Gat A en gat B zijn niet getest (paragraaf 2.3).
- De getallen 333, 308, 67, 68, 552 en de hotspottellingen komen van de verkenner.
- Of tests in `tests/` `intelligence_levels` aanroepen, is niet nagelopen.
- Of een bedragslimiet nergens in het goedkeurpad bestaat, is gelezen, niet uitputtend gezocht.
- De werking van `user_roles` onder RLS en alle identiteitsbevindingen (2.2) zijn niet door mij
  herhaald.
- De regelnummers staan op commit `42e79df0`; `rbac_service.py` is met `~` aangegeven omdat
  ik het fragment per bereik las.
- Prestatie, doorlooptijd van de fasen en het aantal impacttests per fase.
- Juridische uitleg (paragraaf 9) en de actuele stand van de Digital Omnibus: ik heb de bronnen
  NIET zelf opnieuw geraadpleegd; ze komen via de regie (zie 9).

Aannames, elk met toets:

```
Aanname: de bevoegdheidsvorm (rol, proces, stap, handeling, limiet) is genoeg voor het
debiteurenproces en voor Hoogland; er hoeft geen voorwaarde "alleen voor deze debiteurgroep".
Toets: bouw F2 voor het debiteurenproces en laat een key-user de matrix invullen met de
echte stappen; ontbreekt een voorwaarde, dan vooraf aanvullen. Review: 2026-11-03.

Aanname: groepskoppeling bij inloggen (just-in-time) is voor de pilot genoeg; SCIM is niet
nodig.
Toets: vraag de pilotklant hoe vaak rollen veranderen en of mensen uit dienst direct
geblokkeerd moeten zijn; zo ja, een intrekkings-pad bij de IdP (of kortere tokens) toevoegen.
Review: voor F6 start.

Aanname: een wachttijd plus daglimiet plus logboekbevestiging is voor een zzp'er voldoende
vervanging voor "vier ogen".
Toets: een jurist/accountant leest de bevestiging en de logregel (paragraaf 9); en een
acceptatietest vanuit Fatima (meetlat persona). Review: 2026-11-03.

Aanname: de debiteurenagent valt volgens bijlage III van de AI-verordening niet onder
hoog risico zolang hij geen kredietwaardigheid of -score beoordeelt.
Toets: een jurist beoordeelt de feitelijke werking. Wordt kredietwaardigheid ooit een
onderdeel, dan wijzigt het regime. Review: voor de pilot.

Aanname: het hergebruik van de bestaande goedkeurwachtrij (HITL-tickets) en het bestaande
auditlog is sterk genoeg voor limiet en vier ogen.
Toets: F2-tests; blijkt de wachtrij niet te dragen, dan niet verder bouwen en opnieuw wegen.
Review: na F2.
```

---

## 9. Juridische kaders en open vragen (geen juridisch advies)

**Wat de bronnen zeggen** (via de regie aangeleverd; ik heb ze niet zelf opnieuw geopend):

| Bron | Gebruik hier | Soort bron |
|---|---|---|
| AI-verordening art. 26: een gebruiker wijst menselijk toezicht toe aan natuurlijke personen met de nodige competentie, training en gezag, en de nodige ondersteuning (ai-act-service-desk.ec.europa.eu) | Toezichthouder per agent met vastgelegde instructie | Officieel (EU) |
| AI-verordening art. 14: toezichthouders moeten de output kunnen begrijpen, negeren en terugdraaien en het systeem kunnen stoppen; twee personen alleen bij biometrische identificatie | Goedkeurder ziet de inhoud en kan afkeuren; vier ogen is dus geen eis van deze verordening | Secundair (artificialintelligenceact.eu) |
| Bijlage III: kredietwaardigheid en HR zijn hoog risico; betalingsherinneringen en incasso staan er niet in | Debiteurenagent waarschijnlijk niet hoog risico; HR-agents wel | Secundair |
| Digital Omnibus: hoog-risico-verplichtingen uitgesteld naar 2 december 2027; art. 50 (transparantie) en art. 4 (AI-geletterdheid) niet uitgesteld | AI-geletterdheid en transparantie gelden dus al in de pilot | Secundair (Gibson Dunn); formele publicatie NIET bij een officiele bron bevestigd |
| AVG art. 22: uitsluitend geautomatiseerd besluit met rechtsgevolgen verboden tenzij uitzondering; menselijke tussenkomst moet echte beslisbevoegdheid hebben | Een goedkeuring is een beslissing en geen klik; zie 3.3 punt 4 | Wettekst, via regie |
| OWASP AI Agent Security Cheat Sheet: hoge impact en externe communicatie met menselijke of dubbele goedkeuring; minimale rechten | Basis voor de risicoklassen en "agent nooit meer dan de mens" | Secundair |
| Maker-checker (vier ogen) | Functiescheiding tegen fraude en fouten; bedrijfskundig, geen wettelijke eis | Algemeen |

**Vragen voor een jurist** (niet door mij te beantwoorden):

1. Is een aanmaning of dreigbrief die de agent voorstelt en een mens goedkeurt, een
   "besluit met rechtsgevolg" in de zin van AVG art. 22? Telt een bevestiging door de mens
   als echte tussenkomst of als formaliteit?
2. Welke Nederlandse regels gelden voor het sturen van incasso-aanmaningen en
   dreigbrieven (bijvoorbeeld bij consumenten versus bedrijven, termijnen, kosten)?
3. Geldt artikel 50 (transparantie) voor brieven en berichten die door een agent zijn opgesteld
   en wat moet er dan in staan?
4. Is de bewuste uitzondering voor het eenmansbedrijf (zelf beslissen met bevestiging,
   wachttijd, daglimiet) aanvaardbaar als "menselijk toezicht"?
5. Wat betekent "voldoende AI-geletterdheid" (art. 4) voor de vastlegging van een
   toezichthouder-instructie, en is een datum van kennisname genoeg bewijs?

---

## 10. Wat alleen Rakesh kan beslissen (maximaal drie)

1. **Krijgt de pilotklant een toezichthouder-instructie** (een kort document waarin staat wat
   de aangewezen persoon moet kunnen en doen), en wil je dat die voor de pilot al verplicht
   is? Dit gaat over wat je de klant belooft en hoeveel moeite je hem vraagt.
2. **Welk pakket koppelt de pilotklant eerst** (Exact Online, AFAS of TOPdesk) en gebruikt
   hij Microsoft 365 / Entra voor inloggen? Dit bepaalt of F6 in de pilot zit.
3. **Het woord om het omheinde werk te openen**: F0 (na de toets op gat A/B), F7 en F8.

Alle technische keuzes in dit document zijn door de architect gemaakt en staan voor Rakesh
niet ter beoordeling.

---

## 11. Verwijzingen

- ADR-035 (single-tenant), ADR-036 (register: OP-113, OP-143, OP-151, OP-174, OP-190, OP-192,
  OP-193, OP-224), ADR-015 (vier-ogen in de goedkeuring, zoals aangehaald in `hitl_router.py`).
- `docs/meetlat.md`: persona's Fatima, Jeroen, Sanne, Mark; scenario 5 (goedkeuren) en 6
  (medewerkers en rechten).
- `src/core/auth/dependencies.py`, `src/core/auth/rbac.py`,
  `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/services/rbac_service.py`,
  `src/core/api/v1/rbac/roles_router.py`, `src/core/api/v1/feature_flags/admin_router.py`,
  `src/core/config/tool_risk_levels.yml`.
