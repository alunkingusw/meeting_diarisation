const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function loadModule(relativePath, imports, globals = {}) {
  const source = readFileSync(path.join(__dirname, '..', relativePath), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports,
    require: name => {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
    URL, Headers, Error, ...globals,
  });
  return exports;
}

function authEnvironment(token = 'test-session', status = 200) {
  const removed = [];
  const redirects = [];
  const requests = [];
  const response = new Response(null, { status });
  const auth = loadModule('lib/auth.ts', {
    'js-cookie': { get: () => token, remove: name => removed.push(name) },
  }, {
    window: { location: {
      pathname: '/home/1/members', search: '?filter=active', hash: '#member-2',
      replace: url => redirects.push(url),
    } },
    fetch: async (...args) => { requests.push(args); return response; },
  });
  return { auth, removed, redirects, requests, response };
}

test('safe return targets preserve group path, query, and fragment', () => {
  const { auth } = authEnvironment();
  assert.equal(auth.getRedirectTarget('/home/1/members?filter=active#member-2'), '/home/1/members?filter=active#member-2');
  assert.equal(auth.getRedirectTarget('/home'), '/home');
  assert.equal(auth.getRedirectTarget(null), '/home');
});

test('unsafe, malformed, or non-protected return targets fall back to home', () => {
  const { auth } = authEnvironment();
  for (const value of [
    '//example.com/home', '/\\example.com/home', 'https://example.com/home',
    'javascript:alert(1)', '/', '/homepage', '/home/../../login',
    '/home\n', '/home\r', 'http://[', 'home/1',
  ]) {
    assert.equal(auth.getRedirectTarget(value), '/home', value);
  }
});

test('missing token clears the session and redirects without an API request', async () => {
  const { auth, removed, redirects, requests } = authEnvironment(null);
  await assert.rejects(auth.authenticatedFetch('/groups/1'), auth.SessionExpiredError);
  assert.deepEqual(removed, ['token']);
  assert.deepEqual(redirects, [auth.getLoginUrl('/home/1/members?filter=active#member-2')]);
  assert.equal(requests.length, 0);
});

test('401 clears invalid token and redirects preserving the exact intended URL', async () => {
  const { auth, removed, redirects } = authEnvironment('expired-session', 401);
  await assert.rejects(auth.authenticatedFetch('/groups/1'), auth.SessionExpiredError);
  assert.deepEqual(removed, ['token']);
  assert.deepEqual(redirects, ['/?redirect=%2Fhome%2F1%2Fmembers%3Ffilter%3Dactive%23member-2']);
});

test('concurrent authentication failures trigger only one navigation', async () => {
  const { auth, removed, redirects } = authEnvironment('expired-session', 401);
  const results = await Promise.allSettled([
    auth.authenticatedFetch('/groups/1'),
    auth.authenticatedFetch('/groups/1/members'),
    auth.authenticatedFetch('/groups/1/meetings'),
  ]);
  assert.ok(results.every(result => result.status === 'rejected' && result.reason instanceof auth.SessionExpiredError));
  assert.deepEqual(removed, ['token']);
  assert.equal(redirects.length, 1);
});

test('403, 404, and server errors never sign the user out', async () => {
  for (const status of [403, 404, 500]) {
    const { auth, removed, redirects, response } = authEnvironment('test-session', status);
    assert.equal(await auth.authenticatedFetch('/groups/1'), response);
    assert.throws(() => auth.checkGroupResponse(response, 'Unable to load group'));
    assert.deepEqual(removed, []);
    assert.deepEqual(redirects, []);
  }
});

test('successful requests preserve request options and add the current token', async () => {
  const { auth, requests, response } = authEnvironment();
  const controller = new AbortController();
  assert.equal(await auth.authenticatedFetch('/groups/1', {
    method: 'POST', body: '{"name":"Group"}', signal: controller.signal,
    headers: { 'Content-Type': 'application/json' },
  }), response);
  const [url, options] = requests[0];
  assert.equal(url, '/groups/1');
  assert.equal(options.headers.get('Authorization'), 'Bearer test-session');
  assert.equal(options.headers.get('Content-Type'), 'application/json');
  assert.equal(options.body, '{"name":"Group"}');
  assert.equal(options.method, 'POST');
  assert.equal(options.signal, controller.signal);
  assert.doesNotThrow(() => auth.checkGroupResponse(response, 'Unable to load group'));
});

test('network failures propagate without clearing a valid session', async () => {
  const removed = [];
  const failure = new Error('Network unavailable');
  const auth = loadModule('lib/auth.ts', {
    'js-cookie': { get: () => 'test-session', remove: name => removed.push(name) },
  }, { fetch: async () => { throw failure; } });
  await assert.rejects(auth.authenticatedFetch('/groups/1'), error => error === failure);
  assert.deepEqual(removed, []);
});

test('middleware sends unauthenticated deep links to login and permits cookie-bearing requests', () => {
  const { middleware } = loadModule('middleware.ts', {
    'next/server': { NextResponse: { redirect: url => url, next: () => 'next' } },
  });
  const url = new URL('http://localhost:5000/home/1/members?filter=active');
  const request = token => ({ url: url.href, nextUrl: url, cookies: { get: () => token } });
  const login = middleware(request(undefined));
  assert.equal(login.pathname, '/');
  assert.equal(login.searchParams.get('redirect'), '/home/1/members?filter=active');
  assert.equal(middleware(request({ value: 'test-session' })), 'next');
});
