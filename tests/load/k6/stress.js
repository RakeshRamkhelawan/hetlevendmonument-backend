/**
 * k6 Load Test: Stress Test
 * Sprint 5, Slice 3
 *
 * Purpose: Push system beyond normal capacity to find breaking point
 *
 * Goal: System stays stable (no crashes) under 200+ concurrent users
 * Acceptable degradation: Latency may increase, but error rate < 10%
 *
 * Scenario: Ramp to 200 users, spike to 300, observe recovery
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const requestsTotal = new Counter('requests_total');
const procedureLatency = new Trend('procedure_latency');

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp to 100
    { duration: '2m', target: 200 },   // Ramp to 200
    { duration: '1m', target: 300 },   // Spike to 300
    { duration: '2m', target: 300 },   // Hold spike
    { duration: '3m', target: 100 },   // Recover to 100
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.1'],     // < 10% error rate (stress tolerance)
    http_req_duration: ['p(99)<15000'], // 99% < 15s (degraded but not crashed)
    errors: ['rate<0.15'],             // < 15% errors
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8100';  // Port updated from 8000 to 8100
const TEST_EMAIL = __ENV.TEST_EMAIL || 'stresstest@test.com';
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'StressTest123!';

let authToken = '';

export function setup() {
  const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  if (loginRes.status === 200) {
    return { token: loginRes.json('access_token') };
  }

  // If auth fails, continue with degraded test (some endpoints might work without auth)
  console.warn('Setup auth failed, some tests may fail');
  return { token: null };
}

export default function (data) {
  requestsTotal.add(1);

  const headers = {
    'Content-Type': 'application/json',
  };

  if (data.token) {
    headers['Authorization'] = `Bearer ${data.token}`;
  }

  // Mix of read and write operations (70% read, 30% write)
  const operationType = Math.random();

  if (operationType < 0.7) {
    // READ operations (lighter)
    const endpoint = Math.random() < 0.5
      ? '/api/v1/procedures'
      : '/api/v1/agents';

    const res = http.get(`${BASE_URL}${endpoint}`, {
      headers,
      timeout: '20s'  // Higher timeout for stress conditions
    });

    const success = check(res, {
      'read operation OK': (r) => r.status === 200 || r.status === 304,
    });

    if (!success) {
      errorRate.add(1);
    }

  } else {
    // WRITE operations (heavier)
    const procedurePayload = JSON.stringify({
      procedure_id: Math.floor(Math.random() * 5) + 1,  // Random procedure 1-5
      inputs: {
        amount: Math.floor(Math.random() * 10000),
        timestamp: new Date().toISOString(),
      },
    });

    const execStart = Date.now();
    const execRes = http.post(
      `${BASE_URL}/api/v1/procedures/execute`,
      procedurePayload,
      { headers, timeout: '20s' }
    );
    const execDuration = Date.now() - execStart;

    const success = check(execRes, {
      'write operation accepted': (r) => r.status === 200 || r.status === 202 || r.status === 429,
      // 429 (rate limit) is acceptable during stress
    });

    if (!success && execRes.status !== 429) {
      errorRate.add(1);
    }

    procedureLatency.add(execDuration);
  }

  // Vary think time based on load
  // High load → shorter think time (more aggressive)
  const thinkTime = Math.random() * 2;  // 0-2 seconds
  sleep(thinkTime);
}

export function teardown(data) {
  console.log('Stress test completed - check error rates and recovery time');
}
