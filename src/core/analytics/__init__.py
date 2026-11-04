"""
Analytics module for cross-company benchmarking and anonymization.

This module provides privacy-preserving analytics capabilities for
comparing pack usage across companies while maintaining k-anonymity
and GDPR compliance.
"""

from src.core.analytics.anonymizer import DataAnonymizer

__all__ = ["DataAnonymizer"]
