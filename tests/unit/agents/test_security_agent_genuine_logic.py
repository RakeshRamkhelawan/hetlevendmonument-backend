"""Unit tests validating genuine implementations for SecurityAgent parsing and analysis methods.

Enforces that methods extract real findings, calculate mathematical risk matrices,
map to standard OWASP categories, and return actionable steps instead of empty lists.
"""

from unittest.mock import MagicMock
import pytest

from src.core.agents.security_agent import SecurityAgent


@pytest.fixture
def agent():
    return SecurityAgent(agent_id="sec_test_001", tenant_id=1)


SAMPLE_SECURITY_REPORT = """
# Security Assessment Report

## Identified Risks and Vulnerabilities
- [CRITICAL] SQL Injection in authentication endpoint (/api/v1/auth/login). Likelihood: 4, Impact: 5. Allows full database extraction.
- [HIGH] Insecure Direct Object References (IDOR) on document downloads. Likelihood: 3, Impact: 4. Tenant isolation bypass.
- [MEDIUM] Missing Rate Limiting on password reset. Likelihood: 3, Impact: 2. Susceptible to brute force.
- [LOW] Server version banner disclosed in HTTP headers. Likelihood: 2, Impact: 1.

## Compliance Gaps (GDPR / ISO27001)
- [CRITICAL] Unencrypted database backups in S3 bucket. Non-compliant with ISO 27001 A.10.1.
- [HIGH] Personal Data Retention policy not enforced after 30 days. GDPR Article 17 gap.

## Incident Containment & Response
1. Immediately revoke compromised API tokens and terminate active sessions.
2. Isolate infected pod from internal Kubernetes cluster network.
3. Capture memory dump and disk snapshot of affected container for forensics.
4. Review Traefik reverse proxy logs for anomalous POST requests from IP 198.51.100.24.

## Recommended Testing Tooling & Phases
Phase 1: Static Analysis using Semgrep and Bandit on all backend Python code.
Phase 2: Dynamic API scanning with OWASP ZAP and Postman security suite.
Phase 3: Manual penetration testing against multi-tenant isolation boundaries.
"""


def test_extract_risks_and_security_issues(agent):
    risks = agent._extract_risks(SAMPLE_SECURITY_REPORT)
    assert len(risks) >= 3, f"Expected at least 3 risks extracted, got {len(risks)}"
    
    critical_risks = [r for r in risks if r.get("severity") == "critical"]
    assert len(critical_risks) >= 1
    assert "sql" in critical_risks[0]["title"].lower() or "sql" in critical_risks[0]["description"].lower()

    issues = agent._extract_security_issues(SAMPLE_SECURITY_REPORT)
    assert len(issues) >= 3
    assert any(i.get("severity") == "high" for i in issues)


def test_build_risk_matrix(agent):
    risks = [
        {"title": "R1", "severity": "critical", "likelihood": 4, "impact": 5},
        {"title": "R2", "severity": "high", "likelihood": 3, "impact": 4},
        {"title": "R3", "severity": "low", "likelihood": 1, "impact": 2},
    ]
    matrix = agent._build_risk_matrix(risks)
    assert isinstance(matrix, dict)
    assert "critical" in matrix
    assert "high" in matrix
    assert len(matrix["critical"]) == 1
    assert matrix["critical"][0]["title"] == "R1"
    assert "matrix_distribution" in matrix


def test_map_to_owasp_top10(agent):
    issues = [
        {"title": "SQL Injection in auth", "description": "SQL injection flaw", "severity": "critical"},
        {"title": "IDOR on documents", "description": "Broken Access Control object reference", "severity": "high"},
        {"title": "Server header banner", "description": "Security Misconfiguration header leak", "severity": "low"},
    ]
    mapped = agent._map_to_owasp_top10(issues)
    assert isinstance(mapped, dict)
    assert len(mapped) > 0
    # SQLi should map to Injection (A03)
    assert any("Injection" in k for k in mapped.keys())
    # IDOR should map to Broken Access Control (A01)
    assert any("Access Control" in k for k in mapped.keys())


def test_extract_compliance_and_remediation_timeline(agent):
    findings = agent._extract_compliance_findings(SAMPLE_SECURITY_REPORT)
    assert len(findings) >= 2
    assert any("backup" in f["description"].lower() or "iso" in f["description"].lower() for f in findings)

    gaps = agent._identify_compliance_gaps(SAMPLE_SECURITY_REPORT)
    assert len(gaps) >= 1

    timeline = agent._generate_remediation_timeline(gaps)
    assert isinstance(timeline, list)
    assert len(timeline) == len(gaps)
    for item in timeline:
        assert "target_days" in item or "sla_days" in item or "timeline" in item
        assert "severity" in item


def test_extract_threats_and_attack_vectors_and_countermeasures(agent):
    threats = agent._extract_threats(SAMPLE_SECURITY_REPORT)
    assert len(threats) >= 2

    vectors = agent._extract_attack_vectors(SAMPLE_SECURITY_REPORT)
    assert isinstance(vectors, list)

    countermeasures = agent._generate_countermeasures(threats)
    assert len(countermeasures) == len(threats)
    for cm in countermeasures:
        assert "countermeasure" in cm or "mitigation" in cm
        assert "target_threat" in cm


def test_extract_incident_response_steps_and_tooling(agent):
    actions = agent._extract_immediate_actions(SAMPLE_SECURITY_REPORT)
    assert len(actions) >= 2
    assert any("token" in a.lower() or "session" in a.lower() for a in actions)

    investigation = agent._extract_investigation_steps(SAMPLE_SECURITY_REPORT)
    assert len(investigation) >= 1
    assert any("log" in s.lower() or "dump" in s.lower() or "forensics" in s.lower() for s in investigation)

    phases = agent._extract_testing_phases(SAMPLE_SECURITY_REPORT)
    assert len(phases) >= 2
    assert any("static" in p.get("name", "").lower() or "penetration" in p.get("name", "").lower() for p in phases)

    tools = agent._extract_testing_tools(SAMPLE_SECURITY_REPORT)
    assert len(tools) >= 2
    assert any(t.lower() in ["semgrep", "bandit", "owasp zap", "zap", "postman"] for t in tools)
