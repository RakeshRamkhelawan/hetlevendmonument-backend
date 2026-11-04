/**
 * k6 Load Test: Noisy Neighbour
 * Sprint 5, Slice 3
 *
 * Purpose: Verify tenant isolation under load
 *
 * Scenario:
 * - Tenant A: Heavy load (100 VUs, aggressive procedures)
 * - Tenant B: Normal load (10 VUs, typical usage)
 *
 * Success Criteria (from §2.5):
 * - Tenant B latency increases max 50% due to Tenant A
 * - Tenant B error rate < 2%
 * - No cross-tenant data leakage
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import exec from 'k6/execution';

// Metrics per tenant
const tenantALatency = new Trend('tenant_a_latency');
const tenantBLatency = new Trend('tenant_b_latency');
const tenantBErrorRate = new Rate('tenant_b_errors');
const crossTenantLeaks = new Rate('cross_tenant_leaks');

export const options = {
  scenarios: {
    // Tenant A: Noisy neighbour (heavy load)
    tenant_a_heavy: {
      executor: 'ramping-vus',
      exec: 'tenantALoad',
      startVUs: 10,
      stages: [
        { duration: '1m', target: 50 },
        { duration: '3m', target: 100 },  // Peak load
        { duration: '1m', target: 50 },
        { duration: '1m', target: 0 },
      ],
      tags: { tenant: 'A' },
    },
    // Tenant B: Normal user (victim of noisy neighbour)
    tenant_b_normal: {
      executor: 'constant-vus',
      exec: 'tenantBLoad',
      vus: 10,
      duration: '6m',
      tags: { tenant: 'B' },
    },
  },
  thresholds: {
    'tenant_b_latency': ['p(95)<3000'],  // Max 50% increase from baseline 2s
    'tenant_b_errors': ['rate<0.02'],    // < 2% error rate
    'cross_tenant_leaks': ['rate==0'],   // Zero tolerance for data leakage
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8100';  // Port updated from 8000 to 8100

// Tenant credentials
const TENANT_A_EMAIL = __ENV.TENANT_A_EMAIL || 'tenant_a@test.com';
const TENANT_A_PASSWORD = __ENV.TENANT_A_PASSWORD || 'TenantA123!';
const TENANT_B_EMAIL = __ENV.TENANT_B_EMAIL || 'tenant_b@test.com';
const TENANT_B_PASSWORD = __ENV.TENANT_B_PASSWORD || 'TenantB123!';

// Shared state for tokens
let tokenA = '';
let tokenB = '';

export function setup() {
  // Authenticate both tenants
  const loginA = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: TENANT_A_EMAIL,
    password: TENANT_A_PASSWORD,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  const loginB = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: TENANT_B_EMAIL,
    password: TENANT_B_PASSWORD,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  if (loginA.status !== 200 || loginB.status !== 200) {
    throw new Error('Failed to authenticate tenants in setup');
  }

  return {
    tokenA: loginA.json('access_token'),
    tokenB: loginB.json('access_token'),
    tenantAId: loginA.json('tenant_id'),
    tenantBId: loginB.json('tenant_id'),
  };
}

// ============================================================================
// Tenant A (Noisy Neighbour): Heavy, complex procedures
// ============================================================================
export function tenantALoad(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.tokenA}`,
  };

  group('Tenant A - Heavy Load', () => {
    // Execute complex multi-department procedure
    const heavyPayload = JSON.stringify({
      procedure_id: 2,  // Assume complex procedure
      inputs: {
        departments: ['finance', 'legal', 'ops'],
        amount: 50000,
        approval_chain: ['manager', 'director', 'cfo'],
        documents: Array(20).fill('large_document.pdf'),  // Heavy payload
      },
    });

    const res = http.post(
      `${BASE_URL}/api/v1/procedures/execute`,
      heavyPayload,
      { headers, timeout: '30s' }
    );

    const success = check(res, {
      'Tenant A execution accepted': (r) => r.status === 200 || r.status === 202,
    });

    if (success) {
      tenantALatency.add(res.timings.duration);
    }

    // No think time - aggressive load
    sleep(0.5);
  });
}

// ============================================================================
// Tenant B (Normal User): Typical usage, should not be impacted
// ============================================================================
export function tenantBLoad(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.tokenB}`,
  };

  group('Tenant B - Normal Load', () => {
    // Simple procedure execution
    const normalPayload = JSON.stringify({
      procedure_id: 1,
      inputs: {
        amount: 500,
        vendor: 'Regular Vendor',
      },
    });

    const execStart = Date.now();
    const res = http.post(
      `${BASE_URL}/api/v1/procedures/execute`,
      normalPayload,
      { headers, timeout: '15s' }
    );
    const execDuration = Date.now() - execStart;

    const success = check(res, {
      'Tenant B execution OK': (r) => r.status === 200 || r.status === 202,
    });

    if (!success) {
      tenantBErrorRate.add(1);
      console.warn(`Tenant B error: ${res.status} - ${res.body}`);
    }

    tenantBLatency.add(execDuration);

    // Verify tenant isolation: response should only contain Tenant B data
    if (success && res.json('execution_id')) {
      const executionId = res.json('execution_id');
      const statusRes = http.get(
        `${BASE_URL}/api/v1/procedures/executions/${executionId}`,
        { headers }
      );

      check(statusRes, {
        'Tenant B status OK': (r) => r.status === 200,
      });

      // Check for data leakage
      if (statusRes.status === 200) {
        const body = statusRes.json();
        const leakDetected =
          JSON.stringify(body).includes(data.tenantAId) ||
          JSON.stringify(body).includes('tenant_a') ||
          JSON.stringify(body).includes(TENANT_A_EMAIL);

        if (leakDetected) {
          crossTenantLeaks.add(1);
          console.error('❌ CRITICAL: Cross-tenant data leak detected!');
        } else {
          crossTenantLeaks.add(0);
        }
      }
    }

    // Realistic think time
    sleep(Math.random() * 4 + 2);  // 2-6 seconds
  });
}

export function teardown(data) {
  console.log('=== Noisy Neighbour Test Summary ===');
  console.log('Tenant A (noisy): Heavy load applied');
  console.log('Tenant B (victim): Check latency increase and error rate');
  console.log('Data Isolation: Verify zero cross-tenant leaks');
}
