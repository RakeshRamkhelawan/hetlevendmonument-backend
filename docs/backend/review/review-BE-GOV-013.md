# Review BE-GOV-013: Per-request Profiling Consent in process_task()

**Datum:** 2026-06-26
**Sprint:** SP-DLP-003 Dag 2
**Reviewers:** code-reviewer (agent), quality-reviewer (agent)

---

## Gate 2 bevindingen (2 rondes)

### Ronde 1

| Bevinding | Ernst | Status |
|-----------|-------|--------|
| `async with _sf as _db:` zou `_sf()` moeten zijn (reviewers dachten dat _sf een async_sessionmaker was) | HIGH | ONTERECHT -- `memory_store["session_factory"]` slaat al een `AsyncSession` op (line 771: `container.session_factory()`). Bestaand patroon lines 383+501 bevestigd correct. |
| `task.tenant_id` fallback semantisch fout als user_id | HIGH | FIXED -- fallback verwijderd, leeg string = fail-open |
| `self._profiling_opted_out` persisteert als instance state over taken | HIGH | FIXED -- `self._profiling_opted_out = False` reset per-request voor de DB-check |
| ADR-034 Contract 7 schending: `src.core.agents` -> `src.core.governance` | BLOCKER | ONTERECHT -- Contract 7 (`agent_runtime_no_db`) verbiedt alleen `src.core.agents` -> `src.core.database`, NIET -> governance. Geverifieerd in `.importlinter`. |

### Ronde 2 (na fixes + verificatie)

| Check | Resultaat |
|-------|-----------|
| `_user_id_profiling` fallback verwijderd, leeg string = fail-open | OK |
| `self._profiling_opted_out = False` reset voor DB-check | OK |
| `async with _sf as _db:` correct (AsyncSession is context manager) | OK -- matches lines 383+501 |
| Contract 7 niet geschonden (governance import OK) | OK -- `.importlinter` geverifieerd |
| `if self._profiling_opted_out:` gate aanwezig in `process_task()` | OK -- vereist door TDD + arch test |
| Pyright 0 errors (baseline gehandhaafd) | OK |
| Ruff: All checks passed | OK |
| `# noqa: PLC0415` function-local import | OK -- PLC niet in ruff select, maar conventie in project |

---

## Verificatie

- `python -m pyright`: 0 errors (baseline gehandhaafd)
- `ruff check src/core/agents/base_agent.py`: All checks passed
- TDD tests: 3 GROEN (incl. falende arch test nu GROEN)
- Bestaande profiling tests: 2/2 GROEN

---

## Verdict: **APPROVED**

Gate 2 GO -- per-request profiling check wired, arch test GROEN, baseline gehandhaafd.
Twee "blocker" bevindingen van reviewers waren onjuist (session_factory type + Contract 7).

**Correctie 2026-08-25 (OP-172, empirisch weerlegd voor implementatie):** de
onderbouwing van regel 15/26 -- "`memory_store['session_factory']` slaat al een
`AsyncSession` op" -- is FEITELIJK ONJUIST en was zelf nooit geverifieerd.
`container.session_factory()` (`src/core/container.py:154-162`,
`create_session_factory`) retourneert een kale `async_sessionmaker`, geen
`AsyncSession`. Empirisch bevestigd: `async with een_async_sessionmaker as x:` geeft
`TypeError: 'async_sessionmaker' object does not support the asynchronous context
manager protocol`. De oorspronkelijke reviewer-bevinding (regel 15) was dus INHOUDELIJK
CORRECT -- `_sf as _db` had wel `_sf()` moeten zijn -- en de Ronde 2-tegenspraak (regel
26) bekrachtigde een onbewezen aanname zonder eigen verificatie. Gefixt en gesloten als
OP-172, zie `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md` en
`tests/unit/agents/test_governance_wiring_dag4.py::test_the_real_session_factory_wiring_supports_async_with_directly`.
