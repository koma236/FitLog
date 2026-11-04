const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

for (const ip of ['192.0.2.42', '2001:db8::1234']) {
  test(`viewer ${ip} replaces spoofed value and multiValue`, async () => {
    const source = readFileSync(join(__dirname, 'client-ip.js'), 'utf8');
    const context = {};
    runInNewContext(source, context);
    const request = { method: 'POST', uri: '/api/auth/login', querystring: {},
      body: { data: 'unchanged' }, cookies: { csrftoken: { value: 'test-cookie' } },
      headers: { host: { value: 'demo.cloudfront.net' },
        'x-fitlog-client-ip': { value: 'spoof', multiValue: [{ value: 'spoof' }, { value: '192.0.2.99' }] } } };
    const expected = structuredClone(request);
    expected.headers['x-fitlog-client-ip'] = { value: ip };
    const result = await context.handler({ viewer: { ip }, request });
    assert.equal(result, request);
    assert.deepEqual(JSON.parse(JSON.stringify(result)), expected);
  });
}

test('adds the dedicated header when absent', async () => {
  const context = {};
  runInNewContext(readFileSync(join(__dirname, 'client-ip.js'), 'utf8'), context);
  const result = await context.handler({ viewer: { ip: '192.0.2.10' }, request: { headers: {} } });
  assert.equal(result.headers['x-fitlog-client-ip'].value, '192.0.2.10');
});
