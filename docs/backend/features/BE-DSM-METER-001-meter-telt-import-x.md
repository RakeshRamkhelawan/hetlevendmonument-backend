# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DSM-METER-001
- **Feature naam:** De DSM-meter telt `import x` gelijk aan `from x import y`
- **Status:** Gereed op code en meting; Gate 2 staat in `docs/backend/review/review-BE-DSM-METER-001.md`
- **Auteur:** bouwsessie dsmmeter
- **Reviewer:** code-reviewer (subagent, Gate 2)
- **Datum:** 2026-10-22
- **Gerelateerde ticket:** brief `docs/agent-briefs/generated/2026-10-22-sprint-dag-dsm-meter-telt-ook-import-x.md`
- **Gerelateerde module:** `scripts/dsm_full_analysis.py` (`scan_module`), `tests/architecture/test_dsm_meter_telt_import_x.py`
- **Gerelateerde database tabellen:** geen (GEEN migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

De laaggrenzen meten echte afhankelijkheden. Tot 2026-10-22 zag de meter alleen `ast.ImportFrom`: 100 regels `import src....` onder `src/` telden nooit mee. Een bouwer kon een laagovertreding verbergen door `import x` te schrijven in plaats van `from x import y`.

### Buiten scope

Geen laagovertreding repareren; geen productiecode buiten `scripts/` en `tests/`. De acht niet-model-imports in `import_all_models.py` gaan weg via de brief `2026-10-23-sprint-dag-import-all-models-registreert-alleen-modellen`.

## Wat er veranderd is

- **De meter telt `import x`, `import x as y` en meerdere namen per regel** op dezelfde manier als `from x import y`, met dezelfde uitsluitingen (TYPE_CHECKING-blok, testmappen, niet-`src.`).
- **Eerlijke uitzondering voor het registratiebestand.** `src/core/database/import_all_models.py` importeert modellen alleen om de SQLAlchemy-metadata te vullen (Alembic, `create_all`); dat is geen runtime-afhankelijkheid. Sleutel `bestand::<module>`, dus nooit een kaal bestand. Een import telt als registratie alleen als: hij `import x` op moduleniveau is (niet in een functie, niet `from x import y`) EN het doel een SQLAlchemy-model definieert (een klasse met basis `Base` of met `__tablename__`). Alles anders in dat bestand telt gewoon mee.
- **De acht niet-model-imports zijn weg (vervolg 2026-10-23).** In `import_all_models.py` stonden acht imports (regels 39, 40, 43, 57, 76, 161, 164 en 166) van modules zonder SQLAlchemy-model (pydantic, Enum, her-exporterend of leeg); ze gaven de randen infra -> agent_runtime (5), infra -> domain_pack (1) en twee niet-ingedeelde modules. Per import gemeten met een verse interpreter per meting: `Base.metadata` had met alle imports 201 tabellen, zonder elk van de acht afzonderlijk 201 en zonder alle acht samen ook 201, zonder importfout. Ze zijn weggehaald; een negende, `src.core.database.models` (een her-exporterend pakket waarvan de submodules er al apart staan), is bij de nieuwe test gevonden en ook weggehaald (201 tabellen zonder). De tijdelijke gedateerde uitzonderingslijst in de meter en in de drie DSM-tests (`no_unclassified`, `infra_no_domain_pack`, `agent_runtime_infra_circular`) is daarmee verwijderd. Nieuwe guard: `tests/architecture/test_import_all_models_noemt_alleen_modellen.py`. Gemeten: `alembic heads` 1; de 392 driftmeldingen van `alembic check` zijn voor en na identiek (er bestond al drift: dit is geen schemawijziging); `tests/integration/database/test_the_chain_builds_the_whole_schema.py` 21 groen.
- **core_api-budget 566 naar 568**, met reden per rand bij het budget in `test_dsm_grade_a_plus.py`: `health_endpoints.py:32` en `system_endpoints.py:216` (twee legitieme health-randen naar infra).

## Getallen per grens (op `df79d145`)

Statements Ce/Ca/instabiliteit | unique_pairs Ce/Ca/instabiliteit.

| Bak | Oude meter | Nieuw zonder uitzondering | Nieuw met uitzondering |
| --- | --- | --- | --- |
| agent_runtime | 244/207/0,541 \| 167/87/0,657 | 245/231/0,515 \| 167/88/0,655 | 245/212/0,536 \| 167/88/0,655 |
| infra | 1/373/0,003 \| 1/239/0,004 | 46/375/0,109 \| 8/240/0,032 | 7/375/0,018 \| 3/240/0,012 |
| core_api | 941/2/0,998 \| 566/2/0,996 | 944/2/0,998 \| 568/2/0,996 | 944/2/0,998 \| 568/2/0,996 |
| tenancy | 11/22/0,333 \| 5/14/0,263 | 11/23/0,324 \| 5/15/0,250 | 11/22/0,333 \| 5/14/0,263 |
| governance | 13/105/0,110 \| 9/54/0,143 | 13/111/0,105 \| 9/55/0,141 | 13/105/0,110 \| 9/54/0,143 |
| domain_pack | 14/89/0,136 \| 13/45/0,224 | 14/95/0,128 \| 13/46/0,220 | 14/90/0,135 \| 13/46/0,220 |
| integrations | 53/85/0,384 \| 26/57/0,313 | 53/90/0,371 \| 26/58/0,310 | 53/85/0,384 \| 26/57/0,313 |

Overige bakken (auth, llm, tool_broker, worker) veranderen alleen in Ca met 0 tot 2.

Op de noodstop-tak `b83995ba` met deze meter: agent_runtime Ce 257, Ca 212, instabiliteit 0,548 (de grens 0,55 wordt gehaald), met en zonder de variant-A-herschrijving gelijk.

## Trainingssamenvatting

### Een bouwer voegt een `import src....` toe aan een laag

- **Actor:** een ontwikkelaar of een agent die code schrijft.
- **Voorwaarde:** de import raakt een andere DSM-bak dan het bestand zelf.
- **Actie:** `import src.core.x` of `from src.core.x import y`, op moduleniveau of in een functie.
- **Systeemreactie:** de meter telt beide schrijfwijzen als dezelfde rand; de DSM-tests (fan-out-budget, instabiliteit, circulaire paren) zien hem.
- **Succes:** een rand binnen de grens blijft groen.
- **Fout:** een rand boven de grens maakt de bijbehorende DSM-test rood, ook als hij als `import x` is geschreven.
- **Uitzondering:** alleen `import x` op moduleniveau in `import_all_models.py` naar een echt SQLAlchemy-model telt niet mee.

## Bekende beperkingen

- De modelherkenning is structureel (een klasse met basis `Base` of `__tablename__`); een model dat via een andere basisnaam wordt gedefinieerd, telt als gewone rand.
- Een `import x` in een functie in `import_all_models.py` telt altijd mee.
- De noodstop-tak moet haar Ce-plafond 253 in `test_dsm_008_reclassification.py` bijstellen (Ce 257 met de nieuwe meter).
