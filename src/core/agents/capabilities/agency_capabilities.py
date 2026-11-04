"""
Agency Capabilities - The Agency skills integrated into SanskritiSetu

This module provides The Agency agent skills as capabilities that can be
added to existing SanskritiSetu agents. This is the CORRECT integration
approach - not as standalone agents, but as capabilities within the
existing agent architecture.

Usage:
    from src.core.agents.capabilities.agency_capabilities import DesignCapabilities

    # In an agent's _initialize_capabilities method:
    self._capabilities.append(AgentCapability(
        name="agency_design_system",
        description="Generate design system (The Agency: UI Designer)",
        input_types=["design_requirements"],
        output_types=["design_system", "css_variables"],
        handler=DesignCapabilities.create_design_system
    ))
"""

import logging
from typing import Any, Dict, List, Optional
from collections.abc import Callable

logger = logging.getLogger(__name__)


class AgencyCapabilityRegistry:
    """
    Registry for Agency capabilities.

    This provides a central place to register and discover
    Agency skills as capabilities within SanskritiSetu agents.
    """

    _capabilities: dict[str, Callable[..., Any]] = {}  # TODO(TYPE): replace Any with concrete type

    @classmethod
    def register(
        cls, name: str, handler: Callable[..., Any]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register an Agency capability"""
        cls._capabilities[name] = handler
        logger.info(f"Registered Agency capability: {name}")

    @classmethod
    def get(
        cls, name: str
    ) -> Callable[..., Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get an Agency capability by name"""
        return cls._capabilities.get(name)

    @classmethod
    def list_capabilities(cls) -> list[str]:
        """List all registered Agency capabilities"""
        return list(cls._capabilities.keys())


# ============================================================================
# Design Capabilities (from The Agency: UI Designer, UX Researcher, etc.)
# ============================================================================


class DesignCapabilities:
    """
    Design capabilities from The Agency.

    These methods implement the skills from:
    - UI Designer
    - UX Researcher
    - Brand Guardian
    - Image Prompt Engineer
    """

    @staticmethod
    def create_design_system(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: UI Designer skill

        Generate a complete design system with CSS variables,
        component tokens, and accessibility notes.
        """
        brand_colors = params.get("brand_colors", {"primary": "#3b82f6"})
        spacing_base = params.get("spacing_base", 4)

        primary = brand_colors.get("primary", "#3b82f6")
        secondary = brand_colors.get("secondary", "#6b7280")

        return {
            "css_variables": f"""
:root {{
  --color-primary: {primary};
  --color-secondary: {secondary};
  --space-1: {spacing_base}px;
  --space-2: {spacing_base * 2}px;
  --space-4: {spacing_base * 4}px;
}}
""",
            "component_tokens": {
                "button": {
                    "padding": "var(--space-2) var(--space-4)",
                    "border_radius": "0.375rem",
                },
                "card": {
                    "padding": "var(--space-4)",
                    "shadow": "0 1px 3px rgba(0,0,0,0.1)",
                },
            },
            "accessibility_notes": [
                "Ensure 4.5:1 contrast ratio for text",
                "Use semantic HTML elements",
                "Include focus indicators",
            ],
        }

    @staticmethod
    def craft_image_prompt(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Image Prompt Engineer skill

        Craft optimized prompts for AI image generation.
        """
        subject = params.get("subject", "professional portrait")
        style = params.get("style", "editorial")

        prompt = f"""
Professional {subject}, high-quality photography, {style} style,
soft natural lighting, 8k resolution, detailed textures
""".strip()

        return {
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, distorted",
            "platform_optimized": {
                "midjourney": f"{prompt} --ar 16:9 --v 6",
                "dalle": prompt,
            },
        }

    @staticmethod
    def create_brand_foundation(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Brand Guardian skill

        Create brand foundation with mission, vision, values.
        """
        business_name = params.get("business_name", "Company")
        industry = params.get("industry", "technology")

        return {
            "brand_name": business_name,
            "brand_purpose": f"To empower {industry} professionals",
            "brand_vision": f"Leader in {industry} innovation",
            "brand_values": [
                {"name": "Innovation", "definition": "Always improving"},
                {"name": "Integrity", "definition": "Do what's right"},
            ],
        }


# ============================================================================
# Engineering Capabilities (from The Agency: Frontend, Backend, Security, DevOps)
# ============================================================================


class EngineeringCapabilities:
    """
    Engineering capabilities from The Agency.

    These methods implement the skills from:
    - Frontend Developer
    - Backend Architect
    - Security Engineer
    - DevOps Automator
    """

    @staticmethod
    def create_react_component(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Frontend Developer skill

        Generate React component code.
        """
        name = params.get("component_name", "MyComponent")
        framework = params.get("framework", "react")

        code = f"""import React from 'react';

interface {name}Props {{
  // Define props here
}}

export const {name}: React.FC<{name}Props> = (props) => {{
  return (
    <div className="{name.lower()}">
      {{/* Component implementation */}}
    </div>
  );
}};
"""

        return {
            "code": code,
            "framework": framework,
            "file_name": f"{name}.tsx",
        }

    @staticmethod
    def design_api_endpoints(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Backend Architect skill

        Design REST/GraphQL API structure.
        """
        resources = params.get("resources", ["users"])

        endpoints: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for resource in resources:
            endpoints.extend(
                [
                    {"method": "GET", "path": f"/api/v1/{resource}"},
                    {"method": "POST", "path": f"/api/v1/{resource}"},
                ]
            )

        return {
            "api_version": "v1",
            "endpoints": endpoints,
            "authentication": "JWT Bearer token",
        }

    @staticmethod
    def conduct_threat_modeling(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Security Engineer skill

        Perform STRIDE threat modeling.
        """
        system_name = params.get("system_name", "Application")

        return {
            "system": system_name,
            "threats": [
                {
                    "category": "Spoofing",
                    "risk": "HIGH",
                    "mitigation": "Implement strong authentication",
                },
                {
                    "category": "Information Disclosure",
                    "risk": "HIGH" if params.get("data_sensitivity") == "high" else "MEDIUM",
                    "mitigation": "Encrypt data at rest and in transit",
                },
            ],
            "methodology": params.get("methodology", "stride"),
        }


# ============================================================================
# Marketing Capabilities (from The Agency: Growth Hacker, Content Creator)
# ============================================================================


class MarketingCapabilities:
    """
    Marketing capabilities from The Agency.

    These methods implement the skills from:
    - Growth Hacker
    - Content Creator
    """

    @staticmethod
    def design_viral_loop(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Growth Hacker skill

        Design viral growth mechanics.
        """
        product_type = params.get("product_type", "saas")

        mechanics = {
            "saas": "collaboration",
            "marketplace": "network_effects",
        }

        return {
            "recommended_mechanic": mechanics.get(product_type, "referral"),
            "viral_coefficient_target": "> 1.0",
            "tactics": [
                "One-click sharing",
                "Referral rewards",
                "Social proof integration",
            ],
        }

    @staticmethod
    def create_content_strategy(
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Agency: Content Creator skill

        Create content strategy and calendar.
        """
        goals = params.get("business_goals", ["brand_awareness"])

        return {
            "content_pillars": [
                "Educational content",
                "Thought leadership",
                "Product updates",
            ],
            "distribution_channels": [
                "Blog",
                "LinkedIn",
                "Email newsletter",
            ],
            "kpis": {
                "brand_awareness": ["Reach", "Impressions"],
                "engagement": ["Likes", "Comments", "Shares"],
            },
        }


# ============================================================================
# Registration of all Agency capabilities
# ============================================================================


def register_all_agency_capabilities() -> None:
    """
    Register all Agency capabilities with the registry.

    This should be called during application startup.
    """
    # Design capabilities
    AgencyCapabilityRegistry.register(
        "agency_design_system", DesignCapabilities.create_design_system
    )
    AgencyCapabilityRegistry.register("agency_image_prompt", DesignCapabilities.craft_image_prompt)
    AgencyCapabilityRegistry.register(
        "agency_brand_foundation", DesignCapabilities.create_brand_foundation
    )

    # Engineering capabilities
    AgencyCapabilityRegistry.register(
        "agency_react_component", EngineeringCapabilities.create_react_component
    )
    AgencyCapabilityRegistry.register(
        "agency_api_design", EngineeringCapabilities.design_api_endpoints
    )
    AgencyCapabilityRegistry.register(
        "agency_threat_model", EngineeringCapabilities.conduct_threat_modeling
    )

    # Marketing capabilities
    AgencyCapabilityRegistry.register("agency_viral_loop", MarketingCapabilities.design_viral_loop)
    AgencyCapabilityRegistry.register(
        "agency_content_strategy", MarketingCapabilities.create_content_strategy
    )

    logger.info(
        f"Registered {len(AgencyCapabilityRegistry.list_capabilities())} Agency capabilities"
    )


# Auto-register on import
register_all_agency_capabilities()

# Register real (non-mock) capabilities
# These override any mock implementations with real logic
try:
    from .agency_capabilities_real import register_real_capabilities

    register_real_capabilities(AgencyCapabilityRegistry)
    logger.info("Real capabilities registered (overriding mock implementations)")
except ImportError:
    logger.warning("Real capabilities module not found, using mock implementations")

# Register extended capabilities (Product/Testing/Support/Specialized/Game Dev)
# NOTE: importing agency_capabilities_extended already runs its own module-level
# auto-registration (see that file's bottom line) -- do NOT call
# register_all_agency_capabilities_extended() a second time here. A prior version
# of this file called it twice (once via this import's own side effect, once
# explicitly), which was redundant and made a suspected partial-registration
# flake (some integration test runs saw only ~15 of 32 capabilities) harder to
# diagnose. Single registration path only.
try:
    # De import is er om het REGISTRATIE-neveneffect, niet om de klasse: die staat in dit
    # bestand zelf en wordt door de extended-module juist hiervandaan geimporteerd. Hem
    # daar weer vandaan halen was een terug-import die mypy terecht afkeurde
    # ("does not explicitly export attribute", gemeten 2026-08-14, baseline 0 -> 1).
    from . import agency_capabilities_extended  # noqa: F401

    _extended_count = len(AgencyCapabilityRegistry.list_capabilities())
    if _extended_count < 30:
        logger.error(
            "Agency capability registry has only %d entries after import -- "
            "expected >=30 (base + extended). Registration is incomplete.",
            _extended_count,
        )
    else:
        logger.info("Extended capabilities registered (%d total)", _extended_count)
except ImportError:
    logger.warning("Extended capabilities module not found")
