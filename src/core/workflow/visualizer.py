import logging
from typing import Any

import yaml

logger = logging.getLogger("sop_visualizer")


class SOPVisualizer:
    """
    Bidirectional Adapter: SOP YAML <-> React Flow JSON.
    Enables Visual Programming for the Agentic Enterprise.
    """

    def yaml_to_flow(self, yaml_content: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Converts SOP YAML string to React Flow JSON (nodes & edges).
        """
        try:
            data = yaml.safe_load(yaml_content)
            steps = data.get("steps", [])

            nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Create Nodes
            for i, step in enumerate(steps):
                node_id = str(i)
                nodes.append(
                    {
                        "id": node_id,
                        "type": "toolNode",  # Custom node type for frontend
                        "position": {"x": 250, "y": i * 150},  # Simple vertical layout
                        "data": {
                            "label": step.get("description", step.get("tool")),
                            "tool": step.get("tool"),
                            "params": step.get("params", {}),
                            "stepIndex": i,
                        },
                    }
                )

                # Create Edge to next step (if exists)
                if i < len(steps) - 1:
                    edges.append(
                        {
                            "id": f"e{i}-{i + 1}",
                            "source": str(i),
                            "target": str(i + 1),
                            "type": "smoothstep",
                            "animated": True,
                        }
                    )

            return {
                "id": data.get("id", "unknown"),
                "description": data.get("description", ""),
                "variables": data.get("variables", []),
                "nodes": nodes,
                "edges": edges,
            }

        except Exception as e:
            logger.error(f"Failed to convert YAML to Flow: {e}")
            raise ValueError(f"Invalid YAML format: {e}")

    def flow_to_yaml(self, flow_json: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Converts React Flow JSON back to SOP YAML string.
        Logic: Sorts nodes by Y-position to determine execution order.
        """
        try:
            nodes = flow_json.get("nodes", [])

            # 1. Sort nodes by Y position (Top to Bottom execution)
            # This allows users to reorder steps visually by dragging them.
            sorted_nodes = sorted(nodes, key=lambda n: n["position"]["y"])

            steps: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for node in sorted_nodes:
                data = node.get("data", {})
                step = {"tool": data.get("tool"), "params": data.get("params", {})}
                # Optional description
                if data.get("label"):
                    step["description"] = data.get("label")

                steps.append(step)

            # 2. Reconstruct SOP Structure
            sop_data = {
                "id": flow_json.get("id", "GENERATED-SOP"),
                "description": flow_json.get("description", "Visually created workflow"),
                "version": "1.0",
                "variables": flow_json.get("variables", []),
                "steps": steps,
            }

            # 3. Dump to YAML
            yaml_str: str = yaml.dump(sop_data, sort_keys=False, default_flow_style=False)
            return yaml_str

        except Exception as e:
            logger.error(f"Failed to convert Flow to YAML: {e}")
            raise ValueError(f"Invalid Flow JSON: {e}")


# Singleton
visualizer = SOPVisualizer()
