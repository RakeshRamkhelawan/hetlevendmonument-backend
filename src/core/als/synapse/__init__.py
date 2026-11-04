"""Synapse Network - Agent collaboration partner discovery."""

from typing import Any

from .partner_recommender import PartnerRecommender
from .synapse_network import CollaborationHistory, SynapseNetwork, SynapseStrength

__all__ = [
    "SynapseNetwork",
    "SynapseStrength",
    "CollaborationHistory",
    "PartnerRecommender",
]
