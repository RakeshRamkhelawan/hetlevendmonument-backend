# Review: BE-AGT-035 — Permissieprofiel ALS-piloot-skill skillsgaptraining

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-AGT-035-als-skill-tool-permissions.md` |
| Reviewer | Onafhankelijke review-stap (fresh eyes, zonder subagent — runtime heeft geen subagent-mogelijkheid; protocol identiek aan dag 1-3) |
| Datum | 2026-07-30 |

---

## A. EINDOORDEEL: APPROVED

0 CRITICAL, 0 HIGH, 0 MEDIUM open. 2 Low vastgelegd en beargumenteerd.

## B. Checklist

| Laag | Bevinding | Oordeel |
| --- | --- | --- |
| Correctheid | Profiel-agent_id (`skillsgaptraining`) komt overeen met `manifest.skill_id` en met de `agent_id` die `BaseSpecialistAgent.act()` aan `execute_tool` meegeeft (`specialist_base.py:253`, via `to_config()["agent_id"]`). Geverifieerd in code. | OK |
| Correctheid | Rood-groen bewijs klopt: op HEAD faalden 1.1/1.3/1.5/1.6; 1.6 faalde op de permissie-assert, niet op de routing. Na de fix 9/9 groen. | OK |
| Architectuur | Architecture-test toetst de invariant (stopgap ⇔ geen profiel; profiel ⊆ manifest) en niet de huidige toestand; dekt toekomstige skills. Past in de 390-suite. | OK |
| Security (ADR-015) | Default-deny ongewijzigd en gepind; geen wildcards; profiel == manifest (least privilege); `ToolPermissionManager` niet aangepast; agent-level filter is voor deze skill niet-leeg dus fail-closed. | OK |
| Scope | Alleen de piloot-skill; 134 andere manifests ongewijzigd (geverifieerd: test 1.5 assert dat de stopgap bij `burnoutcoach` blijft staan; geen andere manifests in de diff). | OK |
| Kwaliteit | ruff clean (Python), pyright 0/0, ASCII-scan clean, beide YAML valide; commentaarregels per tool beargumenteerd. | OK |
| Eerlijkheid spec | Spec claimt niet meer dan gebouwd is: ontbrekende broker-handlers en de dode-tekst-bevinding zijn expliciet benoemd met eigenaar (dag 5 / escalatie). | OK |

## C. Issue register

| ID | Ernst | Bevinding | Afhandeling |
| --- | --- | --- | --- |
| L-001 | Low | De architecture-test was op HEAD vacuo groen (invariant gold al); het rood-groen-bewijs rust daardoor volledig op de unit-tests. | Bewust ontwerp (invariant-test, zoals de brief eist: "niet de huidige toestand hardcoden"); gedocumenteerd in spec §3 beslissing 4 en in de final-approver brief. |
| L-002 | Low | 4 van de 5 profiel-tools hebben geen broker-handler; een LLM-aanroep daarvan faalt op dispatch-niveau met "unknown tool". | Fail-closed gedrag, geen security-risico; handlers horen bij AUDIT-009/D10. Expliciet gedocumenteerd in spec §2 en §4 stap 5. |

## D. Verificatie van claims (zelf uitgevoerd)

- `pytest tests/unit/tool_broker/test_skillsgaptraining_tool_permissions.py tests/architecture/test_als_skills_tool_permissions.py` → 9 passed.
- `pytest tests/architecture/` → 390 passed (388 + 2 nieuwe).
- Gerichte set + dag 1-3 regressieset → 96 passed; copilot/council/service/als/agents → 1249 passed.
- ruff (2 Python-bestanden): All checks passed. pyright: 0 errors / 0 warnings. ASCII-scan: NONE. YAML: beide valide via `yaml.safe_load`.
- `config/tool_permissions.yml`: profiel met exact de 5 manifest-tools, `max_tools: 10`, `denied_tools: []`.
- Manifest: stopgap-marker afwezig bij `skillsgaptraining`, aanwezig bij de overige 134 manifests (invariant door arch-test afgedwongen).

---

*Eindoordeel: APPROVED | Reviewer: onafhankelijke review-stap | Datum: 2026-07-30*
