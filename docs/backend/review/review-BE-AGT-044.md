# Review BE-AGT-044 -- De eerste tool die echt resolvet

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-044 |
| Datum | 2026-08-02 |
| Reviewvorm | **Gate 2 gehaald, en vóóraf gedraaid** -- `code-reviewer` en `security-reviewer` onafhankelijk, plus zelfreview |
| Omvang | ~330 regels productiecode in 5 bestanden; 25 + 8 tests |
| Uitkomst | **APPROVED** |

---

## 0. Gate 2 vooraf, en dat betaalde zich uit

De dag-2b-brief adviseerde Gate 2 vóór de documentatie te draaien in plaats van erna. Dat is
gedaan. Beide reviewers gaven **CHANGES_REQUESTED**, met samen vier plus vier HIGH-bevindingen.
Twee daarvan waren defecten die anders gemerged zouden zijn:

- **Twee nieuwe mypy-fouten in verse code.** Ik had mypy gedraaid *voordat* ik
  `_build_statement` schreef en daarna niet opnieuw. De teller stond op 54 tegen een baseline
  van 52. Gate 3 zou dat pas na de commit hebben laten zien.
- **De payload lekte op het foutpad.** Mijn hele privacy-ontwerp rust op "niets persoonlijks
  bereikt de event bus of de leeropslag", en op de twee `except`-takken ging de modeloutput
  alsnog verbatim mee. Erger: een van mijn eigen nieuwe tests liep precies dat pad, maar
  controleerde alleen dát er een fout kwam.

## 1. Wat de reviewers vonden en wat ermee gebeurde

| Bevinding | Severity | Status |
| --- | --- | --- |
| Payload verbatim naar event bus, leeropslag en auditketen (ook de geweigerde sleutels) | HIGH | **Opgelost** -- allowlist per tool in `redaction.py`, vóór de `try`, dus ook op beide foutpaden en in `tool_input` |
| Redactie ontbrak op de `except`-takken en in de auditregel | HIGH | **Opgelost** -- een punt van controle; test loopt nu het foutpad |
| `success=True` hardcoded in de broker bij een tool die faalt | HIGH | **Opgelost** -- `tool.failed`, `status_label`, `error_detail` |
| SQL en gebonden parameters in de foutmelding naar het model; niets gelogd | HIGH | **Opgelost** -- generieke melding, `logger.error(..., exc_info=True)`, `except` versmald tot `SQLAlchemyError` |
| Tenant reisde via de modelgestuurde payload; `context` is optioneel | HIGH | **Opgelost** -- tenant uit de context als expliciet argument, payload-sleutel eruit gefilterd |
| Twee nieuwe mypy-fouten (54 vs baseline 52) | HIGH | **Opgelost** -- terug op 52 |
| AVG art. 17: gewiste gebruikers telden mee | MEDIUM | **Opgelost** -- `deleted_at IS NULL`, eigen test en in de SQL-guard |
| `role`-filter accepteerde elk JSON-type en matchte dan stil niets | MEDIUM | **Opgelost** -- type- en lengtecontrole |
| Bypass-venster te breed; WARNING werd routine | MEDIUM | **Opgelost** -- bypass vervangen door ContextVar zetten/herstellen |
| `error_detail` niet gezet op het HR-faalpad | MEDIUM | **Opgelost** |
| Redactiehelper hoorde niet in een tool-specifieke module | MEDIUM | **Opgelost** -- `src/core/tool_broker/redaction.py` |
| `limit`/`offset` werden stil gecorrigeerd | LOW | **Opgelost** -- geweigerd, consistent met de rest |
| `active_count` niet distinct | LOW | **Opgelost** |
| Blokvolgorde `2a` boven `2` | LOW | **Opgelost** -- hernummerd naar 3 |
| Timeout en index op `user_roles(role_id)` | MEDIUM | **Niet gedaan**, zie par. 3 |
| Overige uitvoerpaden publiceren nog rauw | MEDIUM | **Vastgelegd in OP-27**, zie par. 3 |

## 2. Wat de reviewers bevestigden

Geen SQL-injectie (`Role.name == role_filter` bindt als parameter, en het type is nu
afgedwongen). De dubbele tenantfilter is juist en nodig: `user_roles` heeft zelf geen
tenantkolom. De tests zijn substantieel en niet vacuum -- de tenantpredicaat-mutatie sterft
correct. NOOIT-lijst schoon: geen `datetime.now()`, geen non-ASCII, geen secrets.

En een vondst die ik zelf niet had: de vervanging van `TenantFilterBypass` door het zetten van
de ContextVar **repareerde stilzwijgend een productiebug**. `users` heeft Postgres-RLS, en
`db_manager.get_session()` emit alleen `SET LOCAL app.current_tenant` als die ContextVar staat.
De bypass-versie zette hem nooit, dus op PostgreSQL vanuit een worker zou de query nul rijen
hebben teruggegeven en dat als succes hebben gemeld. In de SQLite-unittests volstrekt
onzichtbaar. Dat staat nu in de feature-doc.

## 3. Bewust niet gedaan

**Geen timeout en geen index.** `user_roles` heeft geen index met `role_id` voorop, dus de
join gaat over de globale associatietabel, en de HR-tak negeert de `timeout_seconds` die de
skill meegeeft. Beide zijn reeel maar het zijn prestatiemaatregelen die een Alembic-migratie
en een eigen meting vragen; die horen niet ongemeten in een dag waarvan het punt "eerste
werkende tool" is. Genoteerd voor dag 4 (observability).

**De overige uitvoerpaden redigeren nog niet.** Lokaal, business en extern publiceren hun
payload ongefilterd, en `ToolAuditRepository` saniteert wel `tool_output` maar niet
`tool_input`. Dat is platformbreed werk; het staat nu expliciet in OP-27 met de eis dat het
gedicht is vóórdat er ergens een publisher of auditrepository wordt aangesloten. De gedeelde
module staat er al, met een lege allowlist voor de andere tools -- toevoegen is een bewuste
stap, geen herontwerp.

## 4. Bevindingen in mijn eigen werk

**F-1.** Ik draaide mypy voordat de laatste functie geschreven was en concludeerde "52,
gelijk aan baseline". Dat was waar op het moment van meten en onwaar bij de commit. De les is
niet "draai mypy" maar "draai hem als laatste".

**F-2.** Mijn eerste caching-ontwerp gebruikte `TenantFilterBypass` met als motivering dat de
isolatietest anders vacuum zou zijn. Die redenering klopte, maar ik had niet doorzien dat het
alternatief -- toetsen op de gecompileerde SQL -- diezelfde garantie geeft zonder een
detectiecontrole uit te zetten. Ik koos een zwaardere maatregel omdat ik één oplossing zag.

**F-3.** Ik weigerde `department` met het argument dat stil corrigeren een onwaarheid is, en
corrigeerde twee regels verderop `limit="abc"` stilzwijgend naar 50. De reviewer wees op die
inconsistentie in mijn eigen redenering.

## 5. Compliance

| Regel | Status |
| --- | --- |
| Gate 1 plan | OK -- goedgekeurd, met elf vooraf getoetste twijfels |
| Gate 2 dubbele reviewer-GO | **OK, en vooraf** |
| Gate 3 pyright / ruff / mypy | 0 / schoon / 52 (gelijk aan baseline) |
| black | Schoon op eigen bestanden; pre-existing schuld niet meegenomen |
| Rode test vóór de fix, eigen commit | OK -- `bf937547`, 9 rood |
| Mutatie-getest | OK -- zes richtingen na het herontwerp |
| Isolatietest verplicht | OK -- drie invalshoeken plus een compiled-SQL-guard |
| ASCII-only | OK |
| Bevinding zonder fix heeft borging | OK -- OP-26 en OP-27, beide met test of guard |
| Sprint-dag-brief | OK -- geschreven vóór de code |

## 6. Conclusie

**APPROVED.** De eerste van 27 gedeclareerde tools werkt echt, de keten is op de echte ingang
bewezen, en de tenantgrens is drievoudig en mutatie-geverifieerd.

De belangrijkste uitkomst van de dag is echter geen code: de piloot kan geen skills-gap-analyse
doen, want er is geen HR-data. De tool ziet wie er is en welke rol die heeft, verder niets. Dat
staat als OP-26 en vraagt een besluit van Rakesh voordat deze piloot inhoudelijk waarde levert.

En de procesles bevestigt die van dag 2b, nu van de andere kant: Gate 2 vooraf draaien kostte
wachttijd en ving twee defecten die anders in `develop` hadden gestaan.
