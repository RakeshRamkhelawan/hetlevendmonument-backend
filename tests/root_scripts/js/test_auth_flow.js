// Test login flow
async function testCompleteFlow() {
    console.log('[1/3] Testing login...');

    const loginResponse = await fetch('http://localhost:8001/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            email: 'admin@sanskritisetu.org',
            password: 'admin123'
        })
    });

    const loginData = await loginResponse.json();
    console.log('Login result:', loginResponse.status, loginData);

    if (!loginResponse.ok) {
        console.error('[FAIL] Login failed!');
        return;
    }

    const token = loginData.access_token;
    console.log('[2/3] Got token:', token.substring(0, 50) + '...');

    console.log('[3/3] Testing /auth/me with token...');
    const meResponse = await fetch('http://localhost:8001/api/v1/auth/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });

    const meData = await meResponse.json();
    console.log('/auth/me result:', meResponse.status, meData);

    if (meResponse.ok) {
        console.log('[OK] Full auth flow works!');
    } else {
        console.error('[FAIL] /auth/me failed');
    }
}

testCompleteFlow();
