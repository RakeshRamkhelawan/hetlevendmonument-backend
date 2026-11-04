# BE-AGT-023 -- CriticAgent LearningMixin Integratie

## Metadata

- **Sprint**: SP-AGT-007, Dag 1 van 1
- **Status**: IMPLEMENTED
- **Datum**: 2026-06-27
- **Auteur**: Claude (SP-AGT-007 implementatie-agent)

---

## Samenvatting

CriticAgent erft nu van `LearningMixin` (ADR-022). Na elke succesvolle `critique_task()`-run
wordt `_record_method_observation()` aangeroepen met score en schema_valid in de result_snapshot.
De MRO is veilig: singleton-factory (`get_critic_agent`) wraps de constructie; FastAPI
inspecteert `CriticAgent.__init__` niet rechtstreeks.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/critic_agent.py` | `class CriticAgent(LearningMixin):` + `__init_learning__(tenant_id)` in `__init__` + `_record_method_observation()` in `critique_task()` |
| `tests/unit/agents/test_critic_agent_learning.py` | NIEUW -- 4 unit tests (rood voor, groen na) |

---

## Observation snapshot

| Veld | Waarde |
|---|---|
| `method_name` | `"critique_task"` |
| `args_snapshot` | `{"agent_name": ..., "task_id": ..., "use_llm": ...}` |
| `result_snapshot` | `{"score": <final_score>, "schema_valid": <bool>}` |
| `duration_seconds` | wall-clock via `time.monotonic()` |

---

## Uitsluitingen

- Schema-fail pad (`schema_result.passed == False`): geen observatie (score is 0.0, geen valide run).
- Exception-fallback pad: geen observatie (run is mislukt).
- Comment in code legt dit uit (`NOTE: exception and schema-failure paths intentionally omit observation`).

---

## Testbewijs

```
tests/unit/agents/test_critic_agent_learning.py::test_critic_agent_inherits_learning_mixin PASSED
tests/unit/agents/test_critic_agent_learning.py::test_record_method_observation_called_after_critique_task PASSED
tests/unit/agents/test_critic_agent_learning.py::test_observation_result_snapshot_contains_score_and_schema_valid PASSED
tests/unit/agents/test_critic_agent_learning.py::test_observation_uses_panel_score_when_panel_activated PASSED
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-AGT-007 Dag 1: CriticAgent LearningMixin integratie (__init_learning__ + _record_method_observation in critique_task) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-AGT-007 Dag 1: CriticAgent LearningMixin integratie (__init_learning__ + _record_method_observation in critique_task).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
