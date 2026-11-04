"""ActivePieces 0.92-compatibiliteit van de FlowTransformer.

Bron: upstream `docs/install/reference/breaking-changes.mdx` (tag 0.92.1):
- 0.82.0: piece-versies worden exact vastgepind; een `~` wordt weggehaald, dus
  `~0.0.0` wordt `0.0.0` (een versie die niet bestaat).
- 0.85.4: een stapverwijzing is `step_1['output'][...]` in plaats van `step_1[...]`.
De oude vorm moet op 0.81.4 blijven werken, daar is `step_1` de uitvoer zelf.
"""

import pytest

from src.core.activepieces.transformer import FlowTransformer, rewrite_step_references

GRAPH = {
    "name": "Ref Flow",
    "nodes": [
        {"id": "trigger_node", "agent_name": "webhook_trigger", "config": {}},
        {"id": "classify", "agent_name": "openai", "config": {"prompt": "x"}},
        {
            "id": "notify",
            "agent_name": "slack",
            "config": {
                "text": "Cat {{classify.category}} ({{ classify['confidence'] }})",
                "nested": [{"body": "{{trigger.body.name}}"}],
                "literal": "classify.category zonder accolades",
            },
        },
    ],
    "edges": [
        {"source": "trigger_node", "target": "classify"},
        {"source": "classify", "target": "notify"},
    ],
}

VERSIONS = {
    "@activepieces/piece-openai": "0.7.3",
    "@activepieces/piece-slack": "0.11.2",
    "@activepieces/piece-webhook": "0.1.20",
}


class TestPieceVersion:
    def test_without_versions_keeps_legacy_wildcard_for_0_81(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(GRAPH)
        assert result["actions"]["classify"]["settings"]["pieceVersion"] == "~0.0.0"

    def test_exact_version_from_catalog(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.92.1"
        )
        assert result["actions"]["classify"]["settings"]["pieceVersion"] == "0.7.3"
        assert result["actions"]["notify"]["settings"]["pieceVersion"] == "0.11.2"
        assert result["trigger"]["settings"]["pieceVersion"] == "0.1.20"

    def test_exact_version_also_on_0_81(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.81.4"
        )
        assert result["actions"]["classify"]["settings"]["pieceVersion"] == "0.7.3"

    def test_unknown_piece_refuses_instead_of_pinning_0_0_0(self) -> None:
        with pytest.raises(ValueError, match="piece-slack"):
            FlowTransformer.react_flow_to_activepieces(
                GRAPH,
                piece_versions={"@activepieces/piece-openai": "0.7.3"},
                server_version="0.92.1",
            )

    def test_pinning_server_without_versions_refuses(self) -> None:
        with pytest.raises(ValueError, match="0.82"):
            FlowTransformer.react_flow_to_activepieces(GRAPH, server_version="0.82.0")


class TestStepReferences:
    def test_0_81_keeps_bare_references(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.81.4"
        )
        text = result["actions"]["notify"]["settings"]["input"]["text"]
        assert text == "Cat {{classify.category}} ({{ classify['confidence'] }})"

    def test_0_85_4_wraps_references_in_output(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.85.4"
        )
        notify_input = result["actions"]["notify"]["settings"]["input"]
        assert notify_input["text"] == (
            "Cat {{classify['output'].category}} ({{ classify['output']['confidence'] }})"
        )
        assert notify_input["nested"][0]["body"] == "{{trigger['output'].body.name}}"
        assert notify_input["literal"] == "classify.category zonder accolades"

    def test_0_85_3_is_still_old_format(self) -> None:
        result = FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.85.3"
        )
        assert "['output']" not in result["actions"]["notify"]["settings"]["input"]["text"]

    def test_graph_input_is_not_mutated(self) -> None:
        FlowTransformer.react_flow_to_activepieces(
            GRAPH, piece_versions=VERSIONS, server_version="0.92.1"
        )
        assert GRAPH["nodes"][2]["config"]["text"].startswith("Cat {{classify.category}}")


class TestRewriteStepReferences:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{{step_1.a}}", "{{step_1['output'].a}}"),
            ("{{step_1['a']}}", "{{step_1['output']['a']}}"),
            ("{{step_1['output']['a']}}", "{{step_1['output']['a']}}"),
            ("{{step_1.output.a}}", "{{step_1.output.a}}"),
            ("{{other.a}}", "{{other.a}}"),
            ("{{my_step_1.a}}", "{{my_step_1.a}}"),
            ("{{x.step_1.a}}", "{{x.step_1.a}}"),
            ("{{'step_1.a'}}", "{{'step_1.a'}}"),
            ("{{step_1.a + step_1.b}}", "{{step_1['output'].a + step_1['output'].b}}"),
            ("step_1.a", "step_1.a"),
        ],
    )
    def test_cases(self, source: str, expected: str) -> None:
        assert rewrite_step_references(source, {"step_1"}) == expected
