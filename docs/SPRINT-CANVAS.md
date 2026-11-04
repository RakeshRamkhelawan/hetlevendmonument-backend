# SPRINT-CANVAS

**Dit is het bord. Er is er maar een.**

Bijgewerkt: 2026-09-27 | Branch: `develop` | Eigenaar: Rakesh Ramkhelawan

Alle openstaande werkvoorraad staat hieronder. Stond het ergens anders, dan is dat nu
archief -- zie "Wat hiervoor in de plaats komt" onderaan.

---

## Hoe dit bord werkt

1. **De status is de vergrendeling.** `LOPEND` betekent bezet: een andere sessie slaat die
   rij over. Zet je een rij op `LOPEND`, zet er dan je sessienaam bij.
2. **Een rij gaat pas naar `CLOSED` met bewijs erbij**: de commit-hash, of het commando en
   de uitkomst waarmee je het hebt vastgesteld. Een rij zonder bewijs is niet gesloten.
3. **De persona-kolom zegt welke rol het werk doet.** Die rollen staan in
   `.claude/agents/`. Is de kolom leeg, dan is de rol nog niet bepaald.
4. **Claim fijnmazig werk met `python scripts/claim_op.py claim OP-NNN --session <naam>`.**
   Dat werkt over worktrees heen zonder commit; dit bord kan dat niet.
5. **Geen nieuwe rijen voor gevonden werk.** Een bevinding tijdens een taak krijgt direct
   een sprint-dag-brief in `docs/agent-briefs/generated/`. Zie de NOOIT-lijst in
   `.claude/rules/quality-gates.md`.

Statussen: `GEPLAND` -> `LOPEND` -> `CLOSED`.

---

## Deel 1 -- Wat een klant merkt

Elke sprint hieronder brengt een scenario uit `docs/meetlat.md` dichter bij werkend. De
volgorde is de aanbevolen volgorde; de nummering is geen prioriteit.

| Sprint | Scenario uit de meetlat | Punten | Status | Persona | Sessie |
|---|---|---|---|---|---|
| SP-KLANT-01 | 6 + keten D: rechten en isolatie tussen klanten (2026-10-09: OP-265, OP-143 en OP-190 dicht) | 8 | LOPEND | regie | sanskritisetu-org-07 |
| SP-KLANT-02 | 5: menselijke goedkeuring bij riskante acties (debiteuren Keten B stap 4-6 af 2026-10-07, 113acd97) | 8 | LOPEND | regie | f81c3ed0 |
| SP-KLANT-03 | 7: inzage, export, verwijderen en de auditketen | 6 | GEPLAND | | |
| SP-KLANT-04 | 4 + 12: workflows die echt draaien (2026-10-09: workflowbuilder dag 1 af, d3b622be) | 5 | GEPLAND | | |
| SP-KLANT-05 | 8: controle over wat de agents mogen | 5 | GEPLAND | | |
| SP-KLANT-06 | 3: de agent leest je eigen documenten | 3 | GEPLAND | | |
| SP-KLANT-07 | 1: registreren, inloggen, uitloggen | 2 | GEPLAND | | |
| SP-KLANT-08 | 13: agenda zonder handwerk | 2 | GEPLAND | | |

### SP-KLANT-01 -- Rechten en isolatie tussen klanten

Meetlat: scenario 6 en keten D. Keten D is het scherpste punt van de hele meetlat: geen
enkel pad mag data van de ene klant bij de andere tonen.

| OP | Prio | Wat er mis is |
|---|---|---|
| ~~OP-190~~ | P1 | GESLOTEN 2026-10-09: deel 1 (schrijfpaden onder de applicatierol) en deel 2 (f75e35a6, kolom `tenant_id` + samengestelde sleutels; interlock 1 met akkoord Rakesh, telling ontwikkeldatabase 12/0/0). Ontwikkeldatabase nog migreren na de push |
| ~~OP-143~~ | P1 | GESLOTEN 2026-10-09 (78293f26): een rolsysteem, tools lezen `role_permissions` |
| OP-151 | P2 | RLS beschermt vandaag niets: de applicatie verbindt als eigenaar van de tabellen |
| OP-192 | P2 | Eenentwintig plekken beslissen adminschap op een tekstliteraal |
| OP-113 | P2 | `SET LOCAL app.current_tenant` valt weg na de eerste commit |
| OP-62 | P2 | 155 van de 839 routes hebben geen eigen authenticatie-dependency |
| OP-224 | P2 | Tien functies in twee legacy CRUD-bestanden hangen aan de verbrede grens |
| OP-225 | P3 | De ADMIN_CHECK-guard herkent een aanroep op naam, niet op resolutie |

### SP-KLANT-02 -- Menselijke goedkeuring bij riskante acties

Meetlat: scenario 5. Afkeuren moet de actie echt stoppen; goedkeuren moet exact de
getoonde actie uitvoeren.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-264 | P1 | Een HITL-goedkeuring wordt bewaard in een Python-lijst in het geheugen |
| OP-221 | P2 | De tabel `hitl_requests` heeft geen enkel productieschrijfpad |
| OP-222 | P2 | De zelf-goedkeuringscheck is fail-open bij een onbekend geval |
| OP-174 | P2 | `require_council_approval()` geeft `executing_identity` niet door |
| OP-142 | P2 | Drie copilot-actienamen overschaduwen het rechtenniveau van een tool |
| OP-233 | P2 | De MCP-poort is langs twee wegen te omzeilen, beide in het ontwerp |
| OP-25 | onbepaald | De Council beoordeelt de vorm van een actie, niet de inhoud |
| OP-52 | P3 | `require_council_approval` documenteert tenant-herkomst maar dwingt die niet af |

**Debiteurenagent (de klantroute voor scenario 5), plan van 4 dagen.** Dag 1 (2026-10-04,
brief `docs/agent-briefs/generated/2026-10-04-sprint-dag-debiteurenagent-dag-1-databron.md`):
tabel `receivables` met RLS, model en repository staan in een worktree-commit, nog niet op
develop. **Na dag 2 wordt de schatting van 4 dagen herzien**: niet gemeten zijn wat
onboarding aanmaakt, of `POST /packs/execute` te repareren is, en hoeveel werk de leesbare
goedkeurkaart is.

### SP-KLANT-03 -- Inzage, export, verwijderen en de auditketen

Meetlat: scenario 7. Hier hoort ook de oude sprint **SP-DLP-001** bij (GDPR-handhaving,
116 bevindingen waarvan 8 kritiek, audit: `docs/reports/AUDIT-ADR-DLP-2026-06-25.md`).

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-108 | P1 | Rauwe `INSERT INTO audit_logs` zonder hashketen |
| OP-246 | P1 | `audit_logs` is uitgezonderd van de afscherming voor alle commando's |
| OP-36 | P1 | De art.-17-wisroute bereikt `tool_audit_logs` noch `council_decisions` niet |
| OP-226 | onbepaald | De art.-17-keten loopt over vier onderling ontkoppelde delen |
| OP-115 | P2 | Vijf opgeruimde categorieen hebben geen doeltabel |

### SP-KLANT-04 -- Workflows die echt draaien

Meetlat: scenario 4 en 12. Een workflow moet 24 uur onbeheerd draaien en achteraf
navolgbaar zijn.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-13 | onbepaald | `workflow_worker.py` roept `dramatiq.set_broker()` aan op moduleniveau |
| OP-09 | onbepaald | `POST /packs/execute` bouwt een pack met hardgecodeerde agents |
| OP-21 | onbepaald | Het OODA-pad kan geen initiator meegeven; 134 skills voeren daar geen tools uit |
| OP-10 | onbepaald | `orient()` gebruikt `config["system_prompt"]` niet voor 134 skills |
| OP-01 | onbepaald | Relatie tussen de nieuwe Manager-laag en `MasterOrchestratorAgent` (ADR-023) |

**Workflowbuilder (ActivePieces), analyse `docs/workflowbuilder-debiteuren.md`.** Dag 1 af
(2026-10-08, d3b622be): de builder stuurt niets meer naar buiten, recht `workflows:publish`,
`herinnerd` alleen na een verzonden brief. Open: stap 3-8 (een AP per klant -- B2/B4, interlock 2
bij uitrol --, het blok Debiteuren, een sleutel per flow, logboek per run). Nog geen brief.

### SP-KLANT-05 -- Controle over wat de agents mogen

Meetlat: scenario 8. De klant moet bevoegdheden kunnen begrenzen en elk besluit moet een
naleesbare reden hebben.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-173 | onbepaald | `ExecutorAgent` voert acties direct uit, buiten de broker om |
| OP-38 | P2 | `message` en `reasoning` zijn vrije modeltekst en gaan verbatim de council-ring in |
| OP-208 | P3 | Geen enkel permissieprofiel geeft een `local__*`-tool |
| OP-12 | onbepaald | De autonomie-ladder is voorwaarde voor `autonomous_breakthrough` in productie |
| OP-03 | onbepaald | Platformbrede noodstop: alle agents van een klant in een keer pauzeren |

### SP-KLANT-06 -- De agent leest je eigen documenten

Meetlat: scenario 3. Het antwoord moet aantoonbaar uit het geuploade document komen.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-07 | onbepaald | `src/core/knowledge/` (circa 3.800 regels) is live bedraad maar ongetoetst |
| OP-179 | P2 | `tenant_vector_manager.py:203` bouwt een ChromaDB-client op moduleniveau |
| OP-220 | P2 | Een productiemodule importeren maakt een ChromaDB-database op schijf aan |

### SP-KLANT-07 -- Registreren, inloggen, uitloggen

Meetlat: scenario 1. Een nieuwe klant moet binnen tien minuten zonder hulp binnen zijn.

| OP | Prio | Wat er mis is |
|---|---|---|
| ~~OP-265~~ | P1 | GESLOTEN 2026-10-09 (a899edc4). Vervolg (negen plekken sturen een klantnummer mee) af 2026-10-09 (96a7e6b7). Gevonden: `POST /api/v1/domain-packs/{id}/execute` bestaat niet (pakket uitvoeren geeft 404); klantnummer in twee URL's van `DomainPackService` -- nog geen brief |
| ~~OP-229~~ | P2 | **CLOSED 2026-09-28** -- vier gaten dicht: het canonieke pad, een tweede aanmaakpad zonder validator, de naam-afgeleide slug, en de hoofdletter-omzeiling. 57 tests groen |

### SP-KLANT-08 -- Agenda zonder handwerk

Meetlat: scenario 13.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-238 | onbepaald | De Outlook-koppeling gooit de tijdzone uit de payload weg |
| OP-239 | onbepaald | De Outlook-koppeling zet een ongecodeerde `+` in de querystring |

---

## Deel 2 -- Onder de waterlijn

De klant ziet dit niet, maar zonder deze sprints is "het werkt" niet vast te stellen.

| Sprint | Wat | Punten | Status | Persona | Sessie |
|---|---|---|---|---|---|
| SP-POORT-01 | Tests die uitstaan weer aanzetten | 2 | GEPLAND | | |
| SP-POORT-02 | Testinfrastructuur stabiel maken | 12 | GEPLAND | | |
| SP-POORT-03 | De rookmeldersaudit afmaken | 7 | GEPLAND | | |
| SP-BASIS-01 | Database-integriteit: model tegen migraties | 7 | GEPLAND | | |
| SP-BASIS-02 | De werkwijze en het gereedschap zelf | 10 | GEPLAND | | |
| SP-ORG-01 | Organisatorisch: DPIA, noodstop, uitrolbeleid | 3 | GEPLAND | | |

### SP-POORT-01 -- Tests die uitstaan weer aanzetten

**Dit is de belangrijkste sprint van het hele bord.** Zolang de poort tests overslaat, zegt
"groen" niets, en dan is geen enkele andere sprint af te ronden op bewijs.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-196 | P1 | 180 tests staan in de blokkerende poort onvoorwaardelijk uit |
| OP-194 | P2 | Twintig testmappen met 4.269 tests staan buiten de blokkerende poort |

### SP-POORT-02 -- Testinfrastructuur stabiel maken

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-18 | P2 | Vier unit-tests openden een echte databaseverbinding, samen circa 228 seconden |
| OP-20 | P2 | Een test registreert een globale, onverwijderbare SQLAlchemy-listener |
| OP-44 | P2 | `tests/conftest.py` definieert `pytest_collection_modifyitems` twee keer |
| OP-146 | P2 | Een `isinstance`-test faalt in ongeveer de helft van de volledige runs |
| OP-175 | P2 | Unittests openen echte Redis-verbindingen naar poort 6380 |
| OP-177 | P2 | Unittests openen echte Redis-verbindingen naar poort 6379 |
| OP-217 | P2 | De poort onderrapporteert de omvang van een falen |
| OP-218 | P2 | Een testmodule toetst zijn eigen kerneigenschap niet |
| OP-219 | P2 | Een testmodule overschrijft `DATABASE_URL` op moduleniveau |
| OP-234 | P2 | De volledige poort las een werkbestand terwijl iets anders het herschreef |
| OP-236 | P2 | Een unittest kan groen zijn in een worktree en rood in de hoofdwerkmap |
| OP-243 | onbepaald | De testsuite raadt welke database de testdatabase is |

### SP-POORT-03 -- De rookmeldersaudit afmaken

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-210 | P2 | `errors="ignore"` maakt het nieuwe vangnet onbereikbaar in negen gevallen |
| OP-211 | P2 | De 37 gerepareerde melders waren niet dezelfde 37 als de geclassificeerde |
| OP-212 | P2 | Acht van de 29 "vals alarm"-melders hielden bij een blinde toets stand |
| OP-213 | P3 | Dezelfde foutklasse twee keer, op twee plekken |
| OP-42 | P2 | Bevestigd in de praktijk 2026-08-06: opgetreden, niet hypothetisch |
| OP-48 | P2 | OP-33 is gefixt maar heeft geen structurele guard |
| OP-73 | P2 | De contract-guard frontend/backend dekt twee handmatig genoemde bestanden |

### SP-BASIS-01 -- Database-integriteit

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-249 | P1 | ORM-model en migraties zijn uit elkaar gelopen: 31 kolommen over 9 tabellen |
| OP-247 | P1 | De drift-guard dekt maar een richting |
| OP-150 | P2 | De drift loopt ook de andere kant op: kolommen alleen in de database |
| OP-248 | P2 | De `downgrade()` van de policy-migratie is geen exacte inverse |
| OP-227 | P2 | De echte schematoets wordt genoemd als deploy-eis maar is het niet |
| OP-228 | P2 | Twee van de vier gemelde vorm-driftgevallen kloppen niet |
| OP-149 | P3 | Vier tabellen in de keten hebben geen ORM-model |

### SP-BASIS-02 -- De werkwijze en het gereedschap zelf

Hier hoort ook de oude sprint **SP-TYPE-007** bij (Any-type cleanup, loopt sinds
2026-06-27) -- dat is hetzelfde werk als OP-232.

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-17 | P1 | 1816 getrackte bestanden waren onzichtbaar voor elke zoekopdracht |
| OP-232 | P2 | De 7115 resterende `Any`-regels zijn een ontbrekend patroon, geen losse fouten |
| OP-205 | P2 | `agent_configs/router.py` gebruikt een ruwe databanksessie |
| OP-261 | P2 | De deploygate is op een ontwikkelmachine altijd rood |
| OP-263 | P2 | Het poortslot geeft zichzelf stil weg na 45 minuten |
| OP-237 | P2 | De VS Code PR-extensie vervuilt `.git/config` |
| OP-22 | onbepaald | De ASCII-regel uit CLAUDE.md had geen enkele handhaving |
| OP-240 | onbepaald | De feature-doc-poort keurt een review goed op een citaat |
| OP-241 | onbepaald | Een hernoemde sessie is in `claim_op.py` niet te onderscheiden |
| OP-242 | onbepaald | Een zelfgeschreven `respx.py` overschaduwde de echte bibliotheek |

### SP-ORG-01 -- Organisatorisch

| OP | Prio | Wat er mis is |
|---|---|---|
| OP-05 | onbepaald | DPIA, incidentmeldingspad, rechten van betrokkenen door de hierarchie heen |
| OP-02 | onbepaald | Versiebeheer en uitrol (canary, blue-green) voor wijzigingen aan skills |
| OP-04 | onbepaald | Laagdrempelig "dit klopt niet"-meldkanaal voor afdelingshoofden |

---

## De harde poort -- moet dicht voor elke klant

Uit `docs/meetlat.md` paragraaf 0. Dit staat los van de sprints hierboven: zolang deze
zes niet waar zijn, mag geen enkele externe klant op welke omgeving dan ook.

| # | Eis | Stand 2026-09-27 |
|---|---|---|
| 1 | De vijf P0-autorisatielekken dicht | register zegt OP-182 t/m OP-186 gesloten (11-15 sept) -- **niet nagetoetst** |
| 2 | Acceptatieketen 7 van 7 | **4 van 7**, maar ongeldige meting: er draaide geen database |
| 3 | Uitloggen maakt een token echt ongeldig | register zegt OP-188 gesloten (16 sept) -- niet nagetoetst |
| 4 | Volledige testpoort groen | niet gemeten op 2026-09-27; zie SP-POORT-01 |
| 5 | Auditketencontrole dagelijks groen | niet gemeten |
| 6 | Hersteltest vanaf backup een keer echt uitgevoerd | niet gemeten |

---

## Afgesloten op 2026-09-27

| Sprint | Uitkomst |
|---|---|
| SP-API-009 -- forbidden imports afsluiten | **CLOSED.** Gemeten met `lint-imports`: 9 contracten gehouden, 0 gebroken, exitcode 0. De zes rijen die openstonden waren achterhaald werk. |

---

## Wat hiervoor in de plaats komt

Tot 2026-09-27 stond de werkvoorraad op vier plaatsen tegelijk. Gemeten: `SPRINT_TRACKER.md`
werd voor het laatst bijgewerkt op 25 augustus, `SPRINT-CANVAS.md` op 6 juli,
`6-Development/SPRINT-TRACKER.MD` op 2 juli. Geen van drieen is ooit bewust afgesloten.

| Wat | Waar het nu staat |
|---|---|
| De oude canvas (2307 regels, 32 gesloten sprints) | `docs/99-Archive/sprintadministratie-2026-09-27/SPRINT-CANVAS.md` |
| De oude tracker (4052 regels, 246 gesloten sprints) | `docs/99-Archive/sprintadministratie-2026-09-27/SPRINT_TRACKER.md` |
| De tweede tracker (485 regels) | `docs/99-Archive/sprintadministratie-2026-09-27/SPRINT-TRACKER.MD` |
| De volledige beschrijving per OP-nummer | `docs/adr/036-REGISTER-OVERIG-EN-AFGEROND.md` -- **blijft staan als naslagwerk, bevroren: geen nieuwe rijen** |
| De stand van feiten (rolverdeling, secrets, testbaseline) | `.claude/WORKING-CONTEXT.md` -- dat is geen werkvoorraad en blijft |

**Waarom het register blijft:** dit bord noemt per punt een korte titel, maar de meting,
het bewijs en de geschiedenis staan in het register. Zonder dat is `OP-190` een nummer
zonder inhoud.

**Let op, gemeten 2026-09-27:** `.claude/WORKING-CONTEXT.md` meldt onder "Open ADR-Gaps" dat
OP-182 t/m OP-186 open staan. Het register zegt dat ze tussen 11 en 15 september zijn
gesloten. Die sectie is dus verouderd en moet worden bijgewerkt of verwijderd.
