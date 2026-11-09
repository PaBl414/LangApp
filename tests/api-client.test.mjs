import test from "node:test";
import assert from "node:assert/strict";
import { APIError, request } from "../frontend/js/api-client.js";
import { getCookieId, getFingerprint } from "../frontend/js/fingerprint.js";

function replaceFetch(t, implementation) {
  const original = globalThis.fetch;
  globalThis.fetch = implementation;
  t.after(() => { globalThis.fetch = original; });
}

test("JSON writes preserve credentials and are not retried automatically", async t => {
  let calls = 0;
  replaceFetch(t, async (url, options) => {
    calls++;
    assert.equal(url, "/api/example");
    assert.equal(options.method, "POST");
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), {value: 1});
    return new Response('{"ok":true}', {status: 200});
  });
  assert.deepEqual(await request("/api/example", "POST", {value: 1}), {ok: true});
  assert.equal(calls, 1);
});

test("field validation errors remain readable", async t => {
  replaceFetch(t, async () => new Response(JSON.stringify({detail: [{loc: ["body", "answers", 0, "given"], msg: "Invalid answer"}]}), {status: 422}));
  await assert.rejects(request("/api/example"), error => error instanceof APIError && error.status === 422 && error.message === "answers.0.given: Invalid answer");
});

test("HTML gateway errors preserve their HTTP status", async t => {
  replaceFetch(t, async () => new Response("<h1>Bad gateway</h1>", {status: 502}));
  await assert.rejects(request("/api/example"), error => error.status === 502 && error.message.includes("HTTP 502") && !error.message.includes("<h1>"));
});

test("malformed successful JSON is rejected explicitly", async t => {
  replaceFetch(t, async () => new Response("invalid json", {status: 200}));
  await assert.rejects(request("/api/example"), /nieprawidłową odpowiedź/);
});

test("expired authentication remains distinguishable", async t => {
  replaceFetch(t, async () => new Response('{"detail":"Sesja wygasła."}', {status: 401}));
  await assert.rejects(request("/api/example"), error => error.status === 401 && error.message === "Sesja wygasła.");
});

test("timeouts abort the request and do not retry writes", async t => {
  let calls = 0;
  replaceFetch(t, (url, options) => {
    calls++;
    return new Promise((resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), {once: true}));
  });
  await assert.rejects(request("/api/example", "POST", {value: 1}, 10), /Upłynął czas/);
  assert.equal(calls, 1);
});

test("network failures are readable and do not cause hidden retries", async t => {
  let calls = 0;
  replaceFetch(t, async () => { calls++; throw new TypeError("fetch failed"); });
  await assert.rejects(request("/api/example"), /Brak odpowiedzi serwera/);
  assert.equal(calls, 1);
});

test("empty 204 responses are supported", async t => {
  replaceFetch(t, async () => new Response(null, {status: 204}));
  assert.equal(await request("/api/example", "DELETE"), null);
});

test("blocked browser storage does not prevent creating login identifiers", async t => {
  for (const name of ["localStorage", "sessionStorage", "window"]) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
    t.after(() => { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name]; });
    Object.defineProperty(globalThis, name, name === "window"
      ? {configurable: true, value: {}}
      : {configurable: true, get() { throw new Error("Storage blocked"); }});
  }
  const id = getCookieId();
  assert.ok(id.length >= 8);
  assert.equal(getCookieId(), id);
  assert.match(await getFingerprint(), /^fallback-/);
});
