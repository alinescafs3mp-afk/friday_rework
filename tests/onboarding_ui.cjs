/* Execute the shipped plugin and exact native fetchJSON source in a finite VM.
 * React hook/element driver and fetch responses are explicit offline fixtures.
 * No browser, rendering, service or network acceptance is claimed. */
"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const plugin = fs.readFileSync(process.argv[2], "utf8");
const native = fs.readFileSync(process.argv[3], "utf8");
// These are byte-exact donor function bodies, with types stripped by Node.
const authStart = native.indexOf('const SESSION_HEADER =');
const authEnd = native.indexOf('// ── Global management-profile scope', authStart);
const profileStart = native.indexOf('let _managementProfile =');
const fetchEnd = native.indexOf('/** Encode a plugin registry key', profileStart);
assert(authStart >= 0 && authEnd > authStart && profileStart >= 0 && fetchEnd > profileStart);
// Erase only these exact pinned type annotations. No Wasm compiler or build:
// its virtual memory reservation exceeds the original 4 GiB runner bound.
let client = (native.slice(authStart, authEnd) + native.slice(profileStart, fetchEnd)).replace(/export /g, "");
for (const [typed, plain] of [
  ["function setSessionHeader(headers: Headers, token: string): void", "function setSessionHeader(headers, token)"],
  ["function setManagementProfile(name: string): void", "function setManagementProfile(name)"],
  ["function getManagementProfile(): string", "function getManagementProfile()"],
  ["function withManagementProfile(url: string): string", "function withManagementProfile(url)"],
  ["async function fetchJSON<T>(\n  url: string,\n  init?: RequestInit,\n  options?: FetchJSONOptions,\n): Promise<T>", "async function fetchJSON(url, init, options)"],
  ["let res: Response;", "let res;"],
  ["let body: { error?: string; login_url?: string } = {};", "let body = {};"],
  ["new Promise<T>", "new Promise"],
]) {assert(client.includes(typed), "Pinned native client annotation changed: " + typed); client = client.replace(typed, plain);}
// Bounded WHATWG Headers subset used by this native client: case-insensitive
// has/set and iteration. Node's lazy Undici/Wasm HTTP stack is never imported.
class OfflineHeaders {
  constructor(init) {this.values=new Map();for (const [k,v] of Object.entries(init || {})) this.set(k,v);}
  has(key) {return this.values.has(key.toLowerCase());}
  set(key,value) {this.values.set(key.toLowerCase(),String(value));}
  [Symbol.iterator]() {return this.values[Symbol.iterator]();}
}
const Module = require("node:module"), originalLoad = Module._load;
Module._load = function(name, ...args) {
  if (/^(node:)?(net|http|https|http2|dns|tls|dgram|child_process|worker_threads)$/.test(name)) throw Error("OFFLINE_EFFECT_REFUSED");
  return originalLoad.call(this,name,...args);
};
const requests = [], states = [], pageStates = [], counts = [];
let cursor = 0, effects = [], tree, Component;
const React = {
  createElement: (tag, props, ...children) => ({tag, props: props || {}, children}),
  useState: (initial) => { const index = cursor++; if (!(index in states)) states[index] = initial;
    return [states[index], value => {states[index] = typeof value === "function" ? value(states[index]) : value;}]; },
  useEffect: (effect, dependencies) => { const index = cursor++;
    const old = states[index];
    if (!old || dependencies.some((x, i) => x !== old[i])) {states[index] = dependencies; effects.push(effect);} },
};
const context = {
  window: {__HERMES_SESSION_TOKEN__: input.token || "", location: {assign: () => {throw Error("Unexpected login redirect");}}},
  Headers: OfflineHeaders, URLSearchParams, Promise, console: {warn: () => {}, log: () => {}},
  BASE: "", dashboardServingProfile: () => "default", clearDashboardTokenReloadAttempt: () => {},
  attemptDashboardTokenReloadOnce: () => false,
  apiErrorFromNetworkFailure: e => e,
  apiErrorFromResponse: (status, text) => Error(status + ":" + text),
  fetch: async (url, init) => {
    const record = {url, method: init.method || "GET", headers: Object.fromEntries(init.headers),
      credentials: init.credentials, body: init.body || null}; requests.push(record);
    const parsed = new URL(url, "http://offline.invalid"), path = parsed.pathname;
    let data;
    if (path.endsWith("/profiles")) data = ["default"];
    else if (path.endsWith("/users")) data = input.users || {accounts: [], users: []};
    else if (path.endsWith("/onboarding")) data = {templates: ["approved-local"], pending: [], config_sha256: "a".repeat(64)};
    else if (path.endsWith("/onboarding/prepare")) data = {state: "DISABLED_INCOMPLETE", enabled: false,
      generation: 1, config_sha256: "b".repeat(64), required_names: ["LOCAL_KEY", "EXA_API_KEY"]};
    else if (path.endsWith("/onboarding/credentials")) data = {state: "DISABLED_SETUP_PENDING", enabled: false, recorded: true};
    else if (path.endsWith("/onboarding/activate")) data = {state: "ADMITTED_NEXT_NATIVE_REQUEST", enabled: true};
    else if (path.endsWith("/pairing")) data = input.pending || {pending: []};
    else if (path.endsWith("/pairing/approve")) data = {recorded: true};
    else if (path.endsWith("/conversations")) data = input.conversations;
    else if (path.includes("/conversations/")) {
      data = input.pages[parsed.searchParams.get("offset")]; assert(data, "Unexpected message page");
    } else throw Error("Unexpected offline API request: " + path);
    return {ok: true, status: 200, json: async () => data};
  },
};
vm.createContext(context);
vm.runInContext(client + "\nglobalThis.nativeFetchJSON = fetchJSON;", context, {timeout: 1000});
context.window.__HERMES_PLUGIN_SDK__ = {React, fetchJSON: context.nativeFetchJSON,
  authedFetch: () => {throw Error("No download requested");}};
context.window.__HERMES_PLUGINS__ = {register: (name, component) => {assert.equal(name, "friday_rework"); Component = component;}};
vm.runInContext(plugin, context, {timeout: 1000});
const render = () => {cursor = 0; tree = Component(); const pending = effects; effects = []; pending.forEach(f => f()); return tree;};
const text = node => typeof node === "string" ? node : node && node.children ? node.children.map(text).join("") : "";
const find = (node, label) => {
  if (!node || typeof node !== "object") return null;
  if (node.tag === "button" && text(node) === label) return node;
  for (const child of node.children || []) {const hit = find(child, label); if (hit) return hit;}
  return null;
};
const tick = async () => {for (let i = 0; i < 12; i++) await Promise.resolve();};
const click = async label => {render(); const node = find(tree, label); assert(node, "Missing button " + label);
  assert(!node.props.disabled, "Disabled button " + label); await node.props.onClick(); await tick(); render();};
(async () => {
  render(); await tick(); render(); render();
  const observations = [];
  await click("onboarding"); await click("Load current native state");
  function inputs(node, output = []) {
    if (!node || typeof node !== "object") return output;
    if (node.tag === "input" || node.tag === "select") output.push(node);
    for (const child of node.children || []) inputs(child, output);
    return output;
  }
  function setField(value, next) {
    render(); const field = inputs(tree).find(x => x.props.value === value && x.props.onChange);
    assert(field, "Missing field " + value); field.props.onChange({target: {value: next}});render();
  }
  setField("", "bot-A");setField("", "1");setField("", "user-1");setField("", "approved-local");
  await click("Prepare disabled profile");
  const prepare = requests.find(r => r.url.includes("/onboarding/prepare"));
  assert(prepare);const body = JSON.parse(prepare.body);
  assert.deepEqual(body, {platform: "telegram", transport_profile: "default", account_id: "bot-A", user_id: "1",
    expected_config_sha256: "a".repeat(64), runtime_profile: "user-1", template: "approved-local"});
  observations.push("EXACT_PRINCIPAL_PROFILE_TEMPLATE_CAS");
  assert(find(tree,"Prepare disabled profile").props.disabled); observations.push("NO_DUPLICATE_PREPARE");
  const keyInput=inputs(tree).find(x => x.props.type === "password");assert(keyInput && keyInput.props.autoComplete === "new-password");
  observations.push("SECRET_CAPTURE_PASSWORD_INPUT");
  keyInput.props.onChange({target:{value:"synthetic-native-key-canary"}});render();
  await click("Store scoped key");
  const capture = requests.find(r => r.url.includes("/onboarding/credentials"));assert(capture && capture.method === "PUT");
  const secretBody = JSON.parse(capture.body); assert.equal(secretBody.generation,1);assert.equal(secretBody.expected_config_sha256,"b".repeat(64));
  assert.equal(secretBody.name,"LOCAL_KEY");assert.equal(secretBody.value,"synthetic-native-key-canary");
  assert(!("runtime_profile" in secretBody) && !("template" in secretBody)); observations.push("SCOPED_SECRET_EXACT_NATIVE_API");
  assert.equal(inputs(tree).find(x => x.props.type === "password").props.value, "");observations.push("SECRET_CLEARED_AFTER_CAPTURE");
  await click("Activate complete profile");
  const activation = requests.find(r => r.url.includes("/onboarding/activate"));assert(activation && activation.method === "POST");
  const activateBody=JSON.parse(activation.body);assert.equal(activateBody.generation,1);assert.equal(activateBody.expected_config_sha256,"b".repeat(64));
  assert(!("value" in activateBody));observations.push("ACTIVATION_ORIGINAL_GENERATION_CURRENT_CAS");
  assert(find(tree,"Activate complete profile").props.disabled);observations.push("NO_REPEAT_ENABLED_ACTIVATION");
  for (const request of requests) {assert.equal(request.credentials,"include");assert.equal(request.headers["x-hermes-session-token"],input.token);}
  observations.push("EXACT_NATIVE_AUTHENTICATED_FETCH_CLIENT");
  process.stdout.write(JSON.stringify({observations, request_methods: requests.map(r => r.method), count: observations.length, source_fixture: true, browser_live: "NOT_RUN"}));
})().catch(e => {process.stderr.write(String(e.stack)); process.exitCode = 1;});
