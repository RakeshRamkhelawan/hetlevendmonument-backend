"""
Feature Registry
Maps application routes and components to functional descriptions for AI awareness.
"""

from typing import TypedDict


class FeatureDefinition(TypedDict):
    name: str
    description: str
    capabilities: list[str]
    route_matcher: str  # substring or regex to match URL


class SystemFeatureRegistry:
    """
    Static registry of system features.
    """

    FEATURES: dict[str, FeatureDefinition] = {
        "workflow_builder": {
            "name": "Workflow Builder",
            "description": "A visual drag-and-drop interface for creating multi-agent workflows.",
            "capabilities": [
                "Create linear sequences of tasks",
                "Connect agents using drag-and-drop",
                "Configure agent parameters",
                "Save and execute workflows",
                "Visual dependency management",
            ],
            "route_matcher": "/workflow-builder",
        },
        "agents_registry": {
            "name": "Agent Registry",
            "description": "Catalog of all available AI agents and integrations.",
            "capabilities": [
                "Browse native and integration agents",
                "View agent details and status",
                "Directly interact/chat with specific agents",
                "Search and filter agents",
            ],
            "route_matcher": "/agents",
        },
        "cva_chat": {
            "name": "CVA Strategic Chat",
            "description": "Central command interface for the Chief Visionary Architect.",
            "capabilities": [
                "High-level strategic planning",
                "Multi-mode execution (Reactive, Proactive, CEO)",
                "Orchestrating complex tasks across agents",
                "System-wide analysis",
            ],
            "route_matcher": "/cva",
        },
        "vibe": {
            "name": "VIBE (Visual Interactive Building Environment)",
            "description": "Generative UI interface for dynamic component creation.",
            "capabilities": [
                "Generate React components on the fly",
                "Preview and iterate on UI designs",
                "Export generated code",
            ],
            "route_matcher": "/vibe",
        },
        "dashboard": {
            "name": "Command Dashboard",
            "description": "Main overview of system status and activities.",
            "capabilities": [
                "View system health metrics",
                "Monitor recent activities",
                "Quick access to key tools",
                "Resource usage summary",
            ],
            "route_matcher": "/dashboard",
        },
    }

    @classmethod
    def get_feature_by_route(cls, route: str) -> FeatureDefinition | None:
        """Find feature definition that matches the current route"""
        for feature in cls.FEATURES.values():
            if feature["route_matcher"] in route:
                return feature
        return None

    @classmethod
    def get_all_features_summary(cls) -> str:
        """Get markdown summary of all features"""
        summary = ["### System Features (UI Capabilities):"]
        for key, feat in cls.FEATURES.items():
            caps = ", ".join(feat["capabilities"])
            summary.append(f"- **{feat['name']}**: {feat['description']}")
            summary.append(f"  - *Capabilities*: {caps}")
        return "\n".join(summary)
