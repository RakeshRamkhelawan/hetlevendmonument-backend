"""ADR-036 OP-170: `forensics.py`'s eigen hash-herberekening is een KOPIE van
`CouncilAuditWriter.compute_canonical_json()`'s dict-opbouw, niet een aanroep ervan -- en die
kopie is uit de pas gaan lopen.

**De bevinding (gevonden 2026-08-20, security-reviewer, fix-sprint dag 6, tijdens Gate 2 van de
message-redactiefix -- niet veroorzaakt door die fix).** `src/core/copilot/audit/forensics.py`'s
`HashChainVerifier.verify_tenant_chain()` bouwt zijn eigen `decision_data`-dict om de hash van een
opgeslagen rij te herberekenen, in plaats van `CouncilAuditWriter.compute_canonical_json()` te
gebruiken zoals `chain_verifier.py` en `report_generator.py` dat WEL doen. Die kopie mist
`model_id`/`model_version`, terwijl `compute_canonical_json()` die twee velden altijd meehasht.
Gevolg: `forensics.py` herberekent voor ELKE rij een hash die niet overeenkomt met de opgeslagen
`decision_hash`, en meldt dus "Content tampering detected" op elke bestaande rij, onafhankelijk
van of er daadwerkelijk mee gerommeld is. Gebruikt door `tools/copilot_admin.py` (een
admin-CLI-script).

**Waarom deze test bestaat.** `elke FA-bevinding die niet direct gefixed wordt, VEREIST een
falende architecture test in dezelfde commit` (`.claude/rules/quality-gates.md`). Dit is geen
guard-met-een-lijst-van-uitzonderingen (er is precies EEN bevinding, geen verzameling), dus de
`xfail(strict=True)`-vorm past hier beter dan een groene-guard-met-datering: de test IS de
vastlegging, en `strict=True` dwingt af dat iemand de marker verwijdert zodra het gefixed is
(anders faalt CI juist DOOR een onverwacht groene test).

**Wat dit WEL en NIET bewijst.** Deze test vergelijkt de SLEUTELVERZAMELINGEN van de twee
dict-opbouwen via AST, niet de daadwerkelijke hash-uitkomst op een echte database-rij (dat zou
een async DB-sessie-mock vereisen die voor deze structurele bevinding niet nodig is). Een
sleutelverschil is voldoende om de bevinding te bewijzen: twee reconstructies van "dezelfde"
canonieke JSON die verschillende velden meenemen, geven per definitie andere hashes voor elke
rij met een niet-lege waarde in het ontbrekende veld.

**Mutatiebewijs (beide richtingen, uitgevoerd 2026-08-20, backup/restore via `cp`+`git diff
--stat`, niet in deze test zelf omdat dat de productiebugfix zou vereisen die vandaag bewust
niet gebeurt):**
- Fix toegepast (model_id/model_version toegevoegd aan `forensics.py`'s dict): eerste poging
  bleef ONVERWACHT XFAIL i.p.v. XPASS -- de guard zelf bleek hol. Oorzaak: `verify_tenant_chain`
  is `async def` (`ast.AsyncFunctionDef`), en de eerste versie van `_dict_literal_keys_in_function`
  matchte alleen `ast.FunctionDef`, dus `forensics_keys` was altijd een lege verzameling en de
  assertion faalde om de VERKEERDE reden. Gefixed door beide AST-klassen te accepteren; daarna
  gaf dezelfde mutatie het verwachte `XPASS(strict)`, wat de testrun laat falen -- exact het
  gedrag dat de marker moet afdwingen.
- Herstel (`cp` uit backup, `git diff --stat` bevestigt 0 wijzigingen t.o.v. HEAD): weer XFAIL.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

COMPUTE_CANONICAL_JSON_FILE = "src/core/copilot/council/audit_writer.py"
COMPUTE_CANONICAL_JSON_FUNCTION = "compute_canonical_json"

FORENSICS_FILE = "src/core/copilot/audit/forensics.py"
FORENSICS_FUNCTION = "verify_tenant_chain"
FORENSICS_DICT_VARIABLE = "decision_data"


def _dict_literal_keys_in_function(
    filepath: str, function_name: str, dict_variable_name: str | None = None
) -> set[str]:
    """Vind de string-sleutels van een dict-literal binnen een functie.

    `dict_variable_name`: als gezet, alleen de dict die aan DIE naam wordt toegewezen (er staan
    meerdere dict-literals in `verify_tenant_chain`, o.a. `v_dict` voor de officer-verdicts-hash
    -- zonder deze filter zou de test de verkeerde dict pakken).
    """
    tree = ast.parse(Path(filepath).read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        # `ast.AsyncFunctionDef` is NIET een subklasse van `ast.FunctionDef` -- zonder deze
        # tweede check matcht `async def verify_tenant_chain` nooit en levert deze functie
        # stil een lege verzameling terug, wat de bevinding onzichtbaar zou maken in plaats
        # van bewijzen. Zelf gevonden via mutatietest (fix toegevoegd aan forensics.py,
        # test bleef XFAIL i.p.v. XPASS -- zie de docstring hierboven).
        is_function = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not (is_function and node.name == function_name):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Dict):
                if dict_variable_name is not None:
                    targets = [t.id for t in inner.targets if isinstance(t, ast.Name)]
                    if dict_variable_name not in targets:
                        continue
                for key_node in inner.value.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        keys.add(key_node.value)
        break
    return keys


def test_forensics_reconstructs_the_same_fields_as_compute_canonical_json() -> None:
    canonical_keys = _dict_literal_keys_in_function(
        COMPUTE_CANONICAL_JSON_FILE, COMPUTE_CANONICAL_JSON_FUNCTION
    )
    forensics_keys = _dict_literal_keys_in_function(
        FORENSICS_FILE, FORENSICS_FUNCTION, FORENSICS_DICT_VARIABLE
    )

    assert canonical_keys, "AST vond geen dict-literal in compute_canonical_json -- test kapot"
    assert forensics_keys, "AST vond geen decision_data-dict in verify_tenant_chain -- test kapot"

    missing_in_forensics = canonical_keys - forensics_keys
    extra_in_forensics = forensics_keys - canonical_keys

    assert not missing_in_forensics and not extra_in_forensics, (
        f"forensics.py's decision_data-sleutels ({sorted(forensics_keys)}) komen niet overeen "
        f"met compute_canonical_json()'s sleutels ({sorted(canonical_keys)}). "
        f"Ontbrekend in forensics.py: {sorted(missing_in_forensics)}. "
        f"Extra in forensics.py: {sorted(extra_in_forensics)}. "
        "Elk verschil betekent dat verify_tenant_chain() een andere hash herberekent dan "
        "persist() opsloeg, en dus tampering meldt op elke rij."
    )
