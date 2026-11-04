"""
E2E (End-to-End) Test Suite
============================

This package contains end-to-end tests that validate complete user journeys
through the SanskritiSetu AI Agent Platform.

E2E tests simulate real user workflows from start to finish:
- User registration and authentication
- Agent creation and configuration
- Workflow design and execution
- Crisis management scenarios
- Multi-agent collaboration

Test Execution:
    # Run all E2E tests
    pytest tests/e2e/ -v -m e2e

    # Run smoke tests only
    pytest tests/e2e/ -v -m smoke

    # Run critical E2E tests
    pytest tests/e2e/ -v -m "e2e and critical"
"""
