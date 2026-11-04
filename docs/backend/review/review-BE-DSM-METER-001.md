STATUS: APPROVED

# Review BE-DSM-METER-001 -- de DSM-meter telt `import x`

Gate 2: code-reviewer (subagent), commit 9cc83edc, een ronde op 2026-10-22. Eindoordeel GO, geen blokkering.

## Gecontroleerd door de reviewer

- (a) AST-logica voor `ast.Import` klopt: per alias, `import a.b.c` gaat als volledige naam naar `classify`, `src.core.src.`-normalisatie gelijk aan ImportFrom, meerdere namen geven elk een rand, TYPE_CHECKING geldt voor beide takken; ImportFrom-gedrag ongewijzigd.
- (b) `_definieert_model` faalt naar de veilige kant: ontbrekende module of syntaxfout geeft False (de import telt dan als rand), een pakket wordt via `__init__.py` gelezen.
- (c) Padmatching in `_repo_wortel_en_pad` neemt het eerste `src`; een voorouderpad met een `src`-map ervoor laat de uitzondering vervallen (fout-rood, nooit fout-groen).
- (d) De nieuwe tests asserten op de uitkomst van `scan_module` in een echte tijdelijke nep-repo, beide richtingen; de lijst- en staleness-tests lezen het echte bestand.
- (e) De aftrek van de bekende schuld is een vast aantal per bucket en kan geen echte nieuwe rand maskeren; een negende niet-model-import maakt de lijst-test rood.
- Het core_api-budget 568 is gemeten (`scan_module("core_api", unique_pairs=True)` zonder shared geeft 568).

## Opmerkingen (niet blokkerend, bewust gelaten)

1. Een niet-model met een klasse met basis `Base` of een `__tablename__`-toewijzing valt ten onrechte vrij; de uitzondering geldt alleen in een bestand, alleen voor `import x` op moduleniveau. Klein risico.
2. Een model via een alias of een andere modelklasse als basis wordt gemist (extra rand; de staleness-test toont dat). Streng, dus veilig.
3. Een voorouderpad met een `src`-map eerder in de keten laat de uitzondering vervallen. Veilig; robuustere variant: op het pad-eindstuk zoeken of de repo-wortel meegeven.
4. `test_fan_out_budget` voor infra (budget 5, unique_pairs) trekt de bekende schuld niet af: infra is nu 3, dus er blijft 2 ruimte over. De schuld gebruikt een deel van de ruimte tot de brief van 2026-10-23 is uitgevoerd.
5. De eis `list(MODEL_REGISTRATIE_BESTANDEN) == [SLEUTEL]` betekent dat een tweede registratiebestand alleen met een bewuste testwijziging kan.

## Niet gemeten door de reviewer

Mutaties op de nieuwe tests (die heeft de bouwer gedaan en staan in de commitboodschap en het verslag aan de regie), de volledige testronde, een CI-run, `test_dsm_grade_a_plus.py` zelf.

## Vervolg 2026-10-23

De bekende-schuldlijst (`BEKENDE_NIET_MODEL_IMPORTS`) en de aftrek in de drie DSM-tests zijn weggehaald: de acht imports zelf zijn uit `import_all_models.py` verwijderd (per import gemeten: 201 tabellen met en zonder), zie `docs/backend/features/BE-DSM-METER-001-meter-telt-import-x.md`. Opmerking 4 hierboven (infra-ruimte) vervalt daarmee.
