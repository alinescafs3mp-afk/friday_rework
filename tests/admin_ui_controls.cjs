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
  Headers, URLSearchParams, Promise, console: {warn: () => {}, log: () => {}},
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
    else if (path.endsWith("/pairing")) data = input.pending || {pending: []};
    else if (path.endsWith("/pairing/approve")) data = {recorded: true};
    else if (path.endsWith("/tasks")) data = input.tasks;
    else if (path.endsWith("/effective")) data = input.effective;
    else if (path.endsWith("/settings")) data = {recorded: true, runtime_application: "PERSISTED_NEXT_NATIVE_SESSION_OR_RELOAD"};
    else if (path.endsWith("/schedules")) data = input.schedules;
    else if (path.includes("/tasks/") && path.endsWith("/control")) data = input.control;
    else if (path.includes("/schedules/") && path.endsWith("/control")) data = {recorded: true};
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
  if (input.action === "messages") {
    await click("conversations"); await click("Load current native state");
    await click("session-1");
    const observe = () => {const row = states.find(s => s && s.session_id === "session-1" && s.messages);
      assert(row); pageStates.push(row.page.state); counts.push(row.messages.length);};
    observe(); await click("Next messages"); observe();
    assert(find(tree, "Next messages").props.disabled);
    await click("Previous messages"); observe();
    assert(find(tree, "Previous messages").props.disabled);
  } else if (input.action === "approve") {
    await click("pairing"); await click("Load current native state"); await click("Approve and enable");
  } else if (["cancel_task", "pause_task", "check_task"].includes(input.action)) {
    await click("tasks"); await click("Load current native state");
    await click({cancel_task: "Cancel task", pause_task: "Pause task", check_task: "Check task"}[input.action]);
    if (!input.control.accepted) assert(text(tree).includes("Control refused or outcome unknown"));
  } else if (input.action === "schedule") {
    await click("schedules"); await click("Load current native state"); await click("Pause schedule");
  } else if (input.action === "settings") {
    await click("effective"); await click("Load current native state");
    const locate = (node, label) => {
      if (!node || typeof node !== "object") return null;
      if (node.props["aria-label"] === label) return node;
      for (const child of node.children || []) {const hit = locate(child, label); if (hit) return hit;}
      return null;
    };
    locate(tree, "kind").props.onChange({target: {value: input.kind}}); render();
    for (const [field, value] of Object.entries(input.fields || {})) {
      locate(tree, field).props.onChange({target: {value}}); render();
    }
    await click("Save operational settings");
  } else {
    await click("Load current native state");
    await click({disable: "Disable", enable: "Enable", role: "Channel admin role"}[input.action]);
  }
  process.stdout.write(JSON.stringify({requests, page_states: pageStates, message_counts: counts}));
})().catch(e => {process.stderr.write(String(e.stack)); process.exitCode = 1;});
