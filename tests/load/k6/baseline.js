/**
 * k6 Load Test: Baseline Performance
 * Sprint 5, Slice 3
 *
 * Purpose: Validate Phase 3 meets NFRs under normal load
 *
 * NFR Targets (from PHASE_3_INTELLIGENT_AGENTS.md §2.5):
 * - Fully automated: p50 < 2s, p95 < 5s
 * - Single approval gate: p50 < 2s (auto steps), p95 < 5s
 * - Multi-department: p50 < 5s, p95 < 10s
 *
 * Scenario: 50 concurrent users, 5-minute steady state
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const procedureExecutionRate = new Rate('procedure_execution_success');
const procedureLatency = new Trend('procedure_latency');
const authLatency = new Trend('auth_latency');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up to 10 users
    { duration: '1m', target: 50 },   // Ramp to 50 users
    { duration: '5m', target: 50 },   // Steady state (5 min)
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],  // 95% requests < 5s
    http_req_failed: ['rate<0.05'],     // < 5% error rate
    procedure_latency: ['p(50)<2000', 'p(95)<5000'],  // NFR targets
  },
};

// Base URL (override with -e BASE_URL=...)
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8100';  // Port updated from 8000 to 8100

// Test data
const TEST_TENANT = __ENV.TEST_TENANT || 'tenant_100';
const TEST_EMAIL = __ENV.TEST_EMAIL || 'loadtest@test.com';
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'LoadTest123!';

let authToken = '';

export function setup() {
  // Authenticate once and share token
  const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(loginRes, {
    'login succeeded': (r) => r.status === 200,
  });

  if (loginRes.status === 200) {
    const body = JSON.parse(loginRes.body);
    authToken = body.access_token;
    return { token: authToken };
  }

  throw new Error('Authentication failed in setup');
}

export default function (data) {
  const token = data.token;
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  // Test 1: Health check (should be fast)
  const healthRes = http.get(`${BASE_URL}/health`, { headers });
  check(healthRes, {
    'health check OK': (r) => r.status === 200,
  });

  // Test 2: List procedures (common read operation)
  const listRes = http.get(`${BASE_URL}/api/v1/procedures`, { headers });
  check(listRes, {
    'list procedures OK': (r) => r.status === 200,
  });

  // Test 3: Execute simple procedure (fully automated)
  const procedurePayload = JSON.stringify({
    procedure_id: 1,  // Assume test procedure exists
    inputs: {
      amount: 100,
      vendor: 'Test Vendor',
    },
  });

  const execStart = Date.now();
  const execRes = http.post(
    `${BASE_URL}/api/v1/procedures/execute`,
    procedurePayload,
    { headers, timeout: '10s' }
  );
  const execDuration = Date.now() - execStart;

  const execSuccess = check(execRes, {
    'procedure execution started': (r) => r.status === 200 || r.status === 202,
  });

  procedureExecutionRate.add(execSuccess);
  procedureLatency.add(execDuration);

  // Test 4: Check execution status
  if (execSuccess && execRes.json('execution_id')) {
    const executionId = execRes.json('execution_id');
    const statusRes = http.get(
      `${BASE_URL}/api/v1/procedures/executions/${executionId}`,
      { headers }
    );
    check(statusRes, {
      'execution status OK': (r) => r.status === 200,
    });
  }

  // Realistic user think time
  sleep(Math.random() * 3 + 1);  // 1-4 seconds
}

export function teardown(data) {
  // Optional: cleanup test data
  console.log('Baseline load test completed');
}
