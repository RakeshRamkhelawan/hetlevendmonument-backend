# BE-ARCH-001: Dramatiq dict-payload actor tenant_id preventietest

**Sprint:** AUDIT-SINGLE-TENANT-DB01 S7
**Datum:** 2026-07-02
**ADR:** ADR-035, ADR-003

## Probleem

TI-004 (CRITICAL, gefixed in S1) toonde aan dat een Dramatiq-actor met een
dict-payload (`task_data_dict: dict[...]`) tenant_id stilzwijgend kon
overslaan als het veld ontbrak, met cross-tenant data-isolatie-bypass tot
gevolg. Er was geen regressie-guard tegen het herintroduceren van dit patroon
in een nieuwe actor.

## Oplossing

`tests/architecture/test_dramatiq_actors_tenant_id.py` met twee tests:

1. `test_dict_payload_dramatiq_actors_validate_tenant_id` -- scant een vaste
   lijst bekende dict-payload-actor-modules (`workflow_tasks.py`,
   `cva_tasks.py`, `learning/worker.py` + collaborator `learning/service.py`)
   op een aantoonbaar tenant_id-guard-patroon (`if not tenant_id`,
   `if _tid_raw is None`, `tenant_id is None`).
2. `test_no_unregistered_dict_payload_dramatiq_actors` -- discovery-scan over
   heel `src/` die faalt zodra een NIEUWE dict-payload actor wordt toegevoegd
   zonder in de vaste lijst te zijn opgenomen (en dus niet gecontroleerd).

Onderscheid tussen twee actor-categorien:
- Expliciet getypeerde parameters (bijv. `tenant_id: int`) zijn AL veilig via
  Python's type-systeem -- geen aparte check nodig.
- Dict-payload parameters hebben GEEN taalgarantie en vereisen expliciete
  runtime-validatie.

## Bevinding tijdens implementatie

De discovery-test vond direct `src/core/workflow/worker_simple.py`: een dode
demo-actor (StubBroker, emoji in logs, nergens geimporteerd, geen
tenant_id-besef). Verwijderd na expliciete Rakesh-goedkeuring, samen met het
orphaned testbestand `tests/unit/test_worker_simple_import.py`.

## ADR-035 heroverweging

Bij implementatie bleek dat ADR-035's D3 Fix B (`single_tenant_worker_context`
auto-fallback decorator in `src/core/workers/tenant_context.py`) wel bestaat
en eigen tests heeft, maar in productie nergens wordt aangeroepen. Fix A
(fail-closed hard-fail, TI-004) is de daadwerkelijk geadopteerde strategie en
is strenger. ADR-035 succescriterium 4 is herschreven om dit te reflecteren.

## Test bewijs

```
python -m pytest tests/architecture/test_dramatiq_actors_tenant_id.py -v
2 passed
```

## Reviewers

code-reviewer: GO (2 non-blocking observaties: alias-import edge case,
lexicale i.p.v. semantische guard-detectie -- gedocumenteerd in code-comment).
quality-reviewer: GO (pyright 0 errors, ruff clean, ASCII-only, geen secrets).


## Trainingssamenvatting

- Actor: Een CI/architecture test runner of ontwikkelaar die `tests/architecture/test_dramatiq_actors_tenant_id.py` uitvoert.
- Voorwaarde: De source tree is beschikbaar; bekende dict-payload actor-modules zijn geregistreerd in `_DICT_PAYLOAD_ACTOR_MODULES`.
- Actie (request): Voer `pytest tests/architecture/test_dramatiq_actors_tenant_id.py` uit.
- Systeemverwerking: `test_dict_payload_dramatiq_actors_validate_tenant_id` parseert elk bekend modulepaar (actor + eventuele collaborators) met de AST, zoekt `@dramatiq.actor` functies met een dict-typed parameter zonder expliciete `tenant_id: int` parameter, en controleert of ten minste een functie een tenant_id-guard bevat (`if` op tenant_id-naam met `raise`/`return` in de body). `test_no_unregistered_dict_payload_dramatiq_actors` scant heel `src/` op nieuwe dict-payload actors en faalt als deze niet in de bekende lijst staan.
- Succesrespons: Beide tests rapporteren `passed`; er zijn geen dict-payload actors zonder validatie en geen niet-geregistreerde actors.
- Foutrespons: `AssertionError` met een lijst van modules zonder tenant_id-guard, of een lijst van nieuwe ongeregistreerde dict-payload actor bestanden.
- Uitzonderingen: Actors met een expliciet getypeerde `tenant_id: int` parameter vallen in categorie 1 en worden niet als dict-payload actor beschouwd; de test is een statische AST-scan en dekt geen runtime reflectie.
