"""Legt het gat vast tussen agentic_service en pack_intent_matcher (2026-08-05).

BEVINDING (nog niet gefixt -- bewust, wacht op routering door Rakesh):
de domain-pack-template-matching in de agentic flow builder draait nooit.

`AgenticService` haalt zijn matcher op met
`getattr(_pm_module, "get_pack_intent_matcher", None)`, maar
`src/core/services/pack_intent_matcher.py` exporteert `get_intent_matcher` -- zonder
`pack_`. De getattr geeft dus altijd None, de `if` erna is altijd False, en het hele
pack-match-blok (agentic_service.py, ca. regel 328-380) is onbereikbaar. Omdat het een
getattr met default is, faalt er niets: de feature is stil uitgeschakeld.

Alleen de naam herstellen is NIET genoeg, en daarom staat dit hier als test in plaats van
dat het even gefixt is. Het blok leest drie velden die `PackMatchResult` niet heeft
(`can_use_as_is`, `suggested_customizations`, `match_score`), en vergelijkt `confidence`
-- een float 0.0-1.0 -- met de strings "exact"/"high"/"medium", terwijl die tekstwaarden
in het aparte veld `match_type` zitten. De naam herstellen zonder de rest activeert een
slapende codepad dat direct op een AttributeError stukloopt.

Deze tests zijn GROEN zolang het gat bestaat en worden ROOD zodra iemand een deel ervan
dicht,zodat de andere delen niet vergeten worden. Zie
.claude/rules/quality-gates.md, "guard-met-gedateerde-uitzondering".
"""

from __future__ import annotations

import dataclasses

import src.core.services.pack_intent_matcher as pm

# Velden die agentic_service.py van een pack-match verwacht maar die PackMatchResult
# niet heeft. Verdwijnt er een uit deze lijst, dan is het gat kleiner geworden.
_MISSING_FIELDS = ("can_use_as_is", "suggested_customizations", "match_score")


def test_matcher_factory_name_mismatch_still_exists() -> None:
    """agentic_service zoekt `get_pack_intent_matcher`; de module heeft `get_intent_matcher`."""
    assert hasattr(pm, "get_intent_matcher"), (
        "pack_intent_matcher.get_intent_matcher is weg. Als hij hernoemd is naar "
        "get_pack_intent_matcher: werk agentic_service.py bij EN de andere twee punten "
        "in deze module-docstring, anders activeer je een codepad dat stukloopt."
    )
    assert not hasattr(pm, "get_pack_intent_matcher"), (
        "pack_intent_matcher exporteert nu get_pack_intent_matcher, dus het pack-match-blok "
        "in agentic_service.py is niet langer onbereikbaar. Controleer eerst de twee andere "
        "gaten (ontbrekende velden + confidence-vergelijking) en verwijder daarna deze test."
    )


def test_pack_match_result_still_misses_the_fields_agentic_service_reads() -> None:
    """PackMatchResult mist can_use_as_is / suggested_customizations / match_score."""
    fields = {f.name for f in dataclasses.fields(pm.PackMatchResult)}
    present = [name for name in _MISSING_FIELDS if name in fields]
    assert not present, (
        f"PackMatchResult heeft nu {present}. Het gat met agentic_service.py is dus deels "
        "gedicht -- werk deze test bij en controleer of de andere twee punten "
        "(factory-naam, confidence-vergelijking) ook kloppen."
    )


def test_confidence_is_a_float_not_a_match_type_string() -> None:
    """`confidence` is numeriek; de tekstwaarden zitten in `match_type`."""
    annotations = {f.name: f.type for f in dataclasses.fields(pm.PackMatchResult)}
    assert "float" in str(annotations["confidence"]), (
        "PackMatchResult.confidence is geen float meer. agentic_service.py vergelijkt hem "
        'met ["exact", "high", "medium"]; controleer of die vergelijking nu wel klopt.'
    )
    assert "str" in str(annotations["match_type"]), (
        "PackMatchResult.match_type is geen str meer -- dat is het veld waar "
        "agentic_service.py op had moeten filteren."
    )
