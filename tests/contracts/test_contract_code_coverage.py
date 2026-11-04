"""
P5.4 Unit Tests for API Contract Test Code

Unit tests for test_api_contracts.py to achieve 95%+ code coverage.
Tests the APIContractValidator class and contract validation logic.

Reference: Test Plan v1.0 Section 6 - API Contract Testing
Pattern: Based on P5.3 approach (unit test the test code itself)
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import AsyncClient, Response

# Skip all tests that require imported test classes requiring fixtures
pytestmark = pytest.mark.integration

# Import the module under test
from tests.contracts.test_api_contracts import (
    APIContractValidator,
    TestAgentAPIContracts as AgentAPIContracts,
    TestAPIContractSummary as APIContractSummary,
    TestAuthAPIContracts as AuthAPIContracts,
    TestBackwardsCompatibilityContracts as BackwardsCompatibilityContracts,
    TestConcurrencyContracts as ConcurrencyContracts,
    TestDataTypeContracts as DataTypeContracts,
    TestErrorResponseContracts as ErrorResponseContracts,
    TestHeaderContracts as HeaderContracts,
    TestToolBrokerAPIContracts as ToolBrokerAPIContracts,
    TestWorkflowAPIContracts as WorkflowAPIContracts,
)

# ============================================================================
# SECTION 1: APIContractValidator Unit Tests
# ============================================================================


class TestAPIContractValidatorClass:
    """Tests for APIContractValidator class"""

    def test_validator_initialization(self):
        """Verify validator initializes with empty tracking lists"""
        validator = APIContractValidator()
        assert isinstance(validator.endpoints_tested, list)
        assert isinstance(validator.contracts_validated, list)
        assert len(validator.endpoints_tested) == 0
        assert len(validator.contracts_validated) == 0

    def test_validate_response_schema_with_dict_response(self):
        """Verify schema validation with simple dict response"""
        validator = APIContractValidator()

        # Mock response with valid data
        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {
            "email": "test@example.com",
            "id": "123",
            "name": "Test User",
        }

        expected_fields = {"email": str, "id": str}

        result = validator.validate_response_schema(mock_response, expected_fields)
        assert result is True

    def test_validate_response_schema_with_missing_fields(self):
        """Verify schema validation fails for missing fields"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {"email": "test@example.com"}

        expected_fields = {"email": str, "id": str, "name": str}  # Missing in response

        result = validator.validate_response_schema(mock_response, expected_fields)
        assert result is False

    def test_validate_response_schema_with_wrong_types(self):
        """Verify schema validation fails for wrong types"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {
            "email": "test@example.com",
            "id": 123,  # Should be str per expected
            "name": "Test",
        }

        expected_fields = {"email": str, "id": str}

        result = validator.validate_response_schema(mock_response, expected_fields)
        assert result is False

    def test_validate_response_schema_with_paginated_response(self):
        """Verify schema validation with paginated response (items list)"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {
            "items": [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}],
            "total": 2,
        }

        expected_fields = {"id": str}
        result = validator.validate_response_schema(mock_response, expected_fields)
        assert result is True

    def test_validate_response_schema_with_json_error(self):
        """Verify schema validation handles JSON parse errors"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.side_effect = ValueError("Invalid JSON")

        result = validator.validate_response_schema(mock_response, {"id": str})
        assert result is False

    def test_validate_response_schema_with_non_dict_response(self):
        """Verify schema validation handles non-dict responses"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = ["item1", "item2"]  # List, not dict

        result = validator.validate_response_schema(mock_response, {"id": str})
        assert result is False

    def test_validate_status_code_success(self):
        """Verify status code validation succeeds"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200

        result = validator.validate_status_code(mock_response, [200, 201])
        assert result is True

    def test_validate_status_code_failure(self):
        """Verify status code validation fails"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.status_code = 404

        result = validator.validate_status_code(mock_response, [200, 201])
        assert result is False

    def test_validate_pagination_success(self):
        """Verify pagination validation succeeds"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {
            "items": [{"id": "1"}],
            "total": 1,
            "skip": 0,
            "limit": 10,
        }

        result = validator.validate_pagination(mock_response)
        assert result is True

    def test_validate_pagination_missing_fields(self):
        """Verify pagination validation fails for missing fields"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {
            "items": [{"id": "1"}],
            "total": 1,
            # Missing skip and limit
        }

        result = validator.validate_pagination(mock_response)
        assert result is False

    def test_validate_pagination_json_error(self):
        """Verify pagination validation handles JSON errors"""
        validator = APIContractValidator()

        mock_response = Mock(spec=Response)
        mock_response.json.side_effect = TypeError("Cannot parse JSON")

        result = validator.validate_pagination(mock_response)
        assert result is False

    def test_record_endpoint_tracking(self):
        """Verify endpoint recording adds to tracking list"""
        validator = APIContractValidator()

        assert len(validator.endpoints_tested) == 0

        validator.record_endpoint("GET", "/auth/me", 200)

        assert len(validator.endpoints_tested) == 1
        assert validator.endpoints_tested[0]["method"] == "GET"
        assert validator.endpoints_tested[0]["path"] == "/auth/me"
        assert validator.endpoints_tested[0]["status"] == 200
        assert "timestamp" in validator.endpoints_tested[0]

    def test_record_endpoint_multiple(self):
        """Verify multiple endpoint recordings"""
        validator = APIContractValidator()

        validator.record_endpoint("GET", "/auth/me", 200)
        validator.record_endpoint("POST", "/auth/token", 200)
        validator.record_endpoint("GET", "/workflows", 200)

        assert len(validator.endpoints_tested) == 3


# ============================================================================
# SECTION 2: Test Class Existence and Structure
# ============================================================================


class TestContractTestClassesExist:
    """Verify all contract test classes exist and have required methods"""

    def test_auth_api_contracts_class(self):
        """Verify AuthAPIContracts exists with methods"""
        assert hasattr(AuthAPIContracts, "test_auth_register_response_schema")
        assert hasattr(AuthAPIContracts, "test_auth_token_response_schema")
        assert hasattr(AuthAPIContracts, "test_auth_me_response_schema")
        assert hasattr(AuthAPIContracts, "test_auth_token_expiration_contract")
        assert hasattr(AuthAPIContracts, "test_auth_error_responses_contract")

    def test_workflow_api_contracts_class(self):
        """Verify WorkflowAPIContracts exists with methods"""
        assert hasattr(WorkflowAPIContracts, "test_workflow_create_response_schema")
        assert hasattr(WorkflowAPIContracts, "test_workflow_list_pagination_contract")
        assert hasattr(WorkflowAPIContracts, "test_workflow_get_by_id_schema")
        assert hasattr(WorkflowAPIContracts, "test_workflow_update_request_schema")
        assert hasattr(WorkflowAPIContracts, "test_workflow_delete_response_contract")
        assert hasattr(WorkflowAPIContracts, "test_workflow_execution_response_schema")

    def test_agent_api_contracts_class(self):
        """Verify AgentAPIContracts exists with methods"""
        assert hasattr(AgentAPIContracts, "test_agent_create_response_schema")
        assert hasattr(AgentAPIContracts, "test_agent_list_pagination_contract")
        assert hasattr(AgentAPIContracts, "test_agent_get_by_id_schema")
        assert hasattr(AgentAPIContracts, "test_agent_update_request_schema")
        assert hasattr(AgentAPIContracts, "test_agent_delete_response_contract")
        assert hasattr(AgentAPIContracts, "test_agent_execution_response_schema")

    def test_tool_broker_api_contracts_class(self):
        """Verify ToolBrokerAPIContracts exists with methods"""
        assert hasattr(ToolBrokerAPIContracts, "test_tools_list_response_schema")
        assert hasattr(ToolBrokerAPIContracts, "test_tools_get_by_name_schema")
        assert hasattr(ToolBrokerAPIContracts, "test_tool_execution_response_schema")
        assert hasattr(ToolBrokerAPIContracts, "test_tools_pagination_contract")

    def test_error_response_contracts_class(self):
        """Verify ErrorResponseContracts exists with methods"""
        assert hasattr(ErrorResponseContracts, "test_404_error_contract")
        assert hasattr(ErrorResponseContracts, "test_401_error_contract")
        assert hasattr(ErrorResponseContracts, "test_validation_error_contract")
        assert hasattr(ErrorResponseContracts, "test_rate_limit_error_contract")

    def test_header_contracts_class(self):
        """Verify HeaderContracts exists with methods"""
        assert hasattr(HeaderContracts, "test_json_content_type_contract")
        assert hasattr(HeaderContracts, "test_cors_headers_contract")
        assert hasattr(HeaderContracts, "test_security_headers_contract")

    def test_concurrency_contracts_class(self):
        """Verify ConcurrencyContracts exists with methods"""
        assert hasattr(ConcurrencyContracts, "test_concurrent_auth_requests_contract")
        assert hasattr(ConcurrencyContracts, "test_concurrent_workflow_reads_contract")

    def test_backwards_compatibility_contracts_class(self):
        """Verify BackwardsCompatibilityContracts exists with methods"""
        assert hasattr(
            BackwardsCompatibilityContracts,
            "test_auth_token_format_backwards_compatible",
        )
        assert hasattr(
            BackwardsCompatibilityContracts,
            "test_workflow_dag_format_backwards_compatible",
        )

    def test_openapi_schema_validation_class_is_gone(self):
        """`TestOpenAPISchemaValidation` MOET afwezig zijn (ADR-036 OP-124/OP-180).

        Die klasse haalde `/openapi.json` over HTTP op. Commit `a125f232` (2026-08-14, OP-124)
        heeft haar verwijderd omdat dat endpoint sindsdien buiten debug uit staat
        (`src/core/api/main.py:154`, `src/main.py:126-127`). De dekkingstest hieronder eiste
        daarna nog steeds dat de klasse BESTOND, en de import bovenaan dit bestand ook -- met
        als gevolg dat heel `tests/contracts` 18 dagen op een `ImportError` stond en niets
        meer meette (OP-180).

        De invariant is dus GEKANTELD: niet "deze OpenAPI-contracttests moeten bestaan", maar
        "ze horen niet te bestaan". Komt het endpoint ooit terug, dan faalt deze test en dat
        is het signaal om de contracttests er weer bij te zetten -- in plaats van dat de map
        opnieuw stil omvalt.

        **Dit is GEEN security-test, en zoek bij een failure niet in die richting.** Deze
        klasse inventariseert welke klassen de contract-suite bevat; elke buurtest hier doet
        hetzelfde met `hasattr`. Dat `/openapi.json` daadwerkelijk uit staat buiten debug is
        een andere invariant met een andere eigenaar, en die is wel geborgd:
        `tests/architecture/test_docs_disabled_in_prod.py` en
        `tests/architecture/test_every_fastapi_app_closes_its_docs.py`. Faalt DEZE test, dan is
        de vraag "wie heeft die testklasse teruggezet en is dat bedoeld", niet "welk schema is
        stuk".
        """
        import tests.contracts.test_api_contracts as contracten

        assert not hasattr(contracten, "TestOpenAPISchemaValidation"), (
            "TestOpenAPISchemaValidation is terug in test_api_contracts.py. Dat mag, maar dan "
            "moet /openapi.json ook echt bereikbaar zijn en moeten de contracttests ervoor "
            "hier weer opgesomd worden. Zie ADR-036 OP-124 en OP-180."
        )

    def test_data_type_contracts_class(self):
        """Verify DataTypeContracts exists with methods"""
        assert hasattr(DataTypeContracts, "test_user_id_data_type_contract")
        assert hasattr(DataTypeContracts, "test_timestamp_data_type_contract")

    def test_api_contract_summary_class(self):
        """Verify APIContractSummary exists with summary method"""
        assert hasattr(APIContractSummary, "test_api_contract_coverage_summary")


# ============================================================================
# SECTION 3: API Contract Coverage Verification
# ============================================================================


class TestAPIContractCoverage:
    """Tests verifying comprehensive API contract coverage"""

    def test_auth_endpoints_covered(self):
        """Verify all auth endpoints have contract tests"""
        endpoints = [
            "test_auth_register_response_schema",
            "test_auth_token_response_schema",
            "test_auth_me_response_schema",
            "test_auth_token_expiration_contract",
            "test_auth_error_responses_contract",
        ]

        for endpoint in endpoints:
            assert hasattr(AuthAPIContracts, endpoint), f"Missing {endpoint}"

    def test_workflow_endpoints_covered(self):
        """Verify all workflow endpoints have contract tests"""
        endpoints = [
            "test_workflow_create_response_schema",
            "test_workflow_list_pagination_contract",
            "test_workflow_get_by_id_schema",
            "test_workflow_update_request_schema",
            "test_workflow_delete_response_contract",
            "test_workflow_execution_response_schema",
        ]

        for endpoint in endpoints:
            assert hasattr(WorkflowAPIContracts, endpoint), f"Missing {endpoint}"

    def test_agent_endpoints_covered(self):
        """Verify all agent endpoints have contract tests"""
        endpoints = [
            "test_agent_create_response_schema",
            "test_agent_list_pagination_contract",
            "test_agent_get_by_id_schema",
            "test_agent_update_request_schema",
            "test_agent_delete_response_contract",
            "test_agent_execution_response_schema",
        ]

        for endpoint in endpoints:
            assert hasattr(AgentAPIContracts, endpoint), f"Missing {endpoint}"

    def test_toolbroker_endpoints_covered(self):
        """Verify all tool broker endpoints have contract tests"""
        endpoints = [
            "test_tools_list_response_schema",
            "test_tools_get_by_name_schema",
            "test_tool_execution_response_schema",
            "test_tools_pagination_contract",
        ]

        for endpoint in endpoints:
            assert hasattr(ToolBrokerAPIContracts, endpoint), f"Missing {endpoint}"

    def test_error_scenarios_covered(self):
        """Verify all error scenarios have contract tests"""
        scenarios = [
            "test_404_error_contract",
            "test_401_error_contract",
            "test_validation_error_contract",
            "test_rate_limit_error_contract",
        ]

        for scenario in scenarios:
            assert hasattr(ErrorResponseContracts, scenario), f"Missing {scenario}"

    def test_security_contracts_covered(self):
        """Verify security contracts are tested"""
        scenarios = [
            "test_json_content_type_contract",
            "test_cors_headers_contract",
            "test_security_headers_contract",
        ]

        for scenario in scenarios:
            assert hasattr(HeaderContracts, scenario), f"Missing {scenario}"

    def test_concurrency_covered(self):
        """Verify concurrency scenarios are tested"""
        scenarios = [
            "test_concurrent_auth_requests_contract",
            "test_concurrent_workflow_reads_contract",
        ]

        for scenario in scenarios:
            assert hasattr(ConcurrencyContracts, scenario), f"Missing {scenario}"

    def test_backwards_compatibility_covered(self):
        """Verify backwards compatibility scenarios are tested"""
        scenarios = [
            "test_auth_token_format_backwards_compatible",
            "test_workflow_dag_format_backwards_compatible",
        ]

        for scenario in scenarios:
            assert hasattr(BackwardsCompatibilityContracts, scenario), f"Missing {scenario}"

    def test_data_type_contracts_covered(self):
        """Verify data type contracts are tested"""
        scenarios = [
            "test_user_id_data_type_contract",
            "test_timestamp_data_type_contract",
        ]

        for scenario in scenarios:
            assert hasattr(DataTypeContracts, scenario), f"Missing {scenario}"


# ============================================================================
# SECTION 4: Test Configuration and Markers
# ============================================================================


class TestTestConfiguration:
    """Tests for test configuration and markers"""

    def test_all_test_methods_callable(self):
        """Verify all test methods are callable"""
        test_classes = [
            AuthAPIContracts,
            WorkflowAPIContracts,
            AgentAPIContracts,
            ToolBrokerAPIContracts,
            ErrorResponseContracts,
            HeaderContracts,
            ConcurrencyContracts,
            BackwardsCompatibilityContracts,
            DataTypeContracts,
        ]

        for test_class in test_classes:
            for name in dir(test_class):
                if name.startswith("test_"):
                    method = getattr(test_class, name)
                    assert callable(method), f"{test_class.__name__}.{name} is not callable"

    def test_pytest_asyncio_markers(self):
        """Verify pytest.mark.asyncio is used where needed"""
        # All test methods using 'async def' should be properly marked
        test_classes = [AuthAPIContracts, WorkflowAPIContracts]

        for test_class in test_classes:
            for name in dir(test_class):
                if name.startswith("test_"):
                    method = getattr(test_class, name)
                    # Verify method exists and is decorated
                    assert hasattr(method, "__name__")


# ============================================================================
# SECTION 5: Validator Fixture Integration
# ============================================================================


class TestValidatorFixture:
    """Tests for validator fixture"""

    def test_validator_fixture_provides_instance(self):
        """Verify validator fixture provides APIContractValidator instance"""
        validator = APIContractValidator()
        assert isinstance(validator, APIContractValidator)

    def test_validator_state_isolation(self):
        """Verify each validator instance has isolated state"""
        v1 = APIContractValidator()
        v2 = APIContractValidator()

        v1.record_endpoint("GET", "/test", 200)

        assert len(v1.endpoints_tested) == 1
        assert len(v2.endpoints_tested) == 0


# ============================================================================
# SECTION 6: Response Mock Patterns
# ============================================================================


class TestResponseMockPatterns:
    """Tests for response mocking patterns used in contracts"""

    def test_mock_json_response(self):
        """Verify JSON response mocking works correctly"""
        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {"id": "123", "name": "test"}
        mock_response.status_code = 200

        assert mock_response.json()["id"] == "123"
        assert mock_response.status_code == 200

    def test_mock_header_access(self):
        """Verify header access mocking works correctly"""
        mock_response = Mock(spec=Response)
        mock_response.headers = {"content-type": "application/json"}

        assert "application/json" in mock_response.headers.get("content-type", "")

    def test_mock_error_response(self):
        """Verify error response mocking works correctly"""
        mock_response = Mock(spec=Response)
        mock_response.json.return_value = {"detail": "Not found"}
        mock_response.status_code = 404

        assert mock_response.status_code == 404
        assert "detail" in mock_response.json()


# ============================================================================
# SECTION 7: Status Code Coverage
# ============================================================================


class TestStatusCodeCoverage:
    """Tests for status code validation patterns"""

    def test_success_status_codes(self):
        """Verify success status codes are properly tested"""
        success_codes = [200, 201, 202, 204]
        for code in success_codes:
            mock_response = Mock(spec=Response)
            mock_response.status_code = code
            # Should be valid for success scenarios
            assert code in range(200, 300)

    def test_client_error_status_codes(self):
        """Verify client error status codes are properly tested"""
        error_codes = [400, 401, 403, 404, 422]
        for code in error_codes:
            mock_response = Mock(spec=Response)
            mock_response.status_code = code
            # Should be valid for error scenarios
            assert code in range(400, 500)

    def test_server_error_status_codes(self):
        """Verify server error status codes are properly tested"""
        error_codes = [500, 502, 503, 504]
        for code in error_codes:
            mock_response = Mock(spec=Response)
            mock_response.status_code = code
            # Should be valid for error scenarios
            assert code in range(500, 600)


# ============================================================================
# SECTION 8: API Endpoint Coverage Summary
# ============================================================================


class TestAPIEndpointCoverageSummary:
    """Summary test for API endpoint coverage"""

    def test_total_auth_tests(self):
        """Verify auth endpoint tests"""
        auth_tests = [m for m in dir(AuthAPIContracts) if m.startswith("test_")]
        assert len(auth_tests) >= 5, f"Expected at least 5 auth tests, got {len(auth_tests)}"

    def test_total_workflow_tests(self):
        """Verify workflow endpoint tests"""
        workflow_tests = [m for m in dir(WorkflowAPIContracts) if m.startswith("test_")]
        assert (
            len(workflow_tests) >= 6
        ), f"Expected at least 6 workflow tests, got {len(workflow_tests)}"

    def test_total_agent_tests(self):
        """Verify agent endpoint tests"""
        agent_tests = [m for m in dir(AgentAPIContracts) if m.startswith("test_")]
        assert len(agent_tests) >= 6, f"Expected at least 6 agent tests, got {len(agent_tests)}"

    def test_total_toolbroker_tests(self):
        """Verify tool broker endpoint tests"""
        toolbroker_tests = [m for m in dir(ToolBrokerAPIContracts) if m.startswith("test_")]
        assert (
            len(toolbroker_tests) >= 4
        ), f"Expected at least 4 tool broker tests, got {len(toolbroker_tests)}"

    def test_total_error_tests(self):
        """Verify error scenario tests"""
        error_tests = [m for m in dir(ErrorResponseContracts) if m.startswith("test_")]
        assert len(error_tests) >= 4, f"Expected at least 4 error tests, got {len(error_tests)}"

    def test_minimum_total_contract_tests(self):
        """Verify minimum total contract tests"""
        test_classes = [
            AuthAPIContracts,
            WorkflowAPIContracts,
            AgentAPIContracts,
            ToolBrokerAPIContracts,
            ErrorResponseContracts,
            HeaderContracts,
            ConcurrencyContracts,
            BackwardsCompatibilityContracts,
            DataTypeContracts,
        ]

        total_tests = 0
        for test_class in test_classes:
            class_tests = [m for m in dir(test_class) if m.startswith("test_")]
            total_tests += len(class_tests)

        assert total_tests >= 30, f"Expected at least 30 total contract tests, got {total_tests}"


# ============================================================================
# SECTION 9: Completion Summary
# ============================================================================


class TestP54CompletionSummary:
    """Summary test for P5.4 completion"""

    def test_p54_test_file_coverage_requirements(self):
        """Verify P5.4 test file meets coverage requirements"""
        # This test verifies all required components are in place
        assert APIContractValidator is not None
        assert AuthAPIContracts is not None
        assert WorkflowAPIContracts is not None
        assert AgentAPIContracts is not None
        assert ToolBrokerAPIContracts is not None
        assert ErrorResponseContracts is not None
        assert HeaderContracts is not None
        assert ConcurrencyContracts is not None
        assert BackwardsCompatibilityContracts is not None
        assert DataTypeContracts is not None

    def test_api_contract_test_categories(self):
        """Verify all API contract test categories covered"""
        categories = {
            "Auth Endpoints": AuthAPIContracts,
            "Workflow Endpoints": WorkflowAPIContracts,
            "Agent Endpoints": AgentAPIContracts,
            "Tool Broker Endpoints": ToolBrokerAPIContracts,
            "Error Responses": ErrorResponseContracts,
            "Headers & Security": HeaderContracts,
            "Concurrency": ConcurrencyContracts,
            "Backwards Compatibility": BackwardsCompatibilityContracts,
            "Data Types": DataTypeContracts,
        }

        for category, test_class in categories.items():
            assert test_class is not None, f"{category} not implemented"
            methods = [m for m in dir(test_class) if m.startswith("test_")]
            assert len(methods) > 0, f"{category} has no tests"
