#!/usr/bin/env node
import { validateWebOverlay } from '../plugins/friday_rework/adapters/dsh_keyless_web.mjs';
/** Finite, keyless component inspection of the pinned built Harness runtime. */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire, syncBuiltinESMExports } from 'node:module';
import net from 'node:net';
import tls from 'node:tls';
import http from 'node:http';
import https from 'node:https';
import dns from 'node:dns';
import childProcess from 'node:child_process';

const PIN = '5badb15009ae1756c3afe0ae0cef1faafc290ccc';
const started = new Date();
const report = { schema: 'friday.dsh-native-probe.v1', startedAt: started.toISOString(), status: 'RUNNING', checks: [], routes: {}, gaps: [] };
let reportPath;
let reportFd;
let booted;
let secondary;
let watchdog;
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const checked = (name, detail) => report.checks.push({ name, status: 'PASS', ...detail });
const finish = () => {
  report.finishedAt = new Date().toISOString();
  report.elapsedMs = Date.now() - started.getTime();
  if (reportFd !== undefined) {
    fs.writeFileSync(reportFd, `${JSON.stringify(report, null, 2)}\n`);
    fs.fsyncSync(reportFd);
    fs.closeSync(reportFd);
    reportFd = undefined;
  }
};

function options(argv) {
  const result = {};
  const allowed = new Set(['--donor', '--patch', '--home', '--report']);
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    assert(allowed.has(key) && argv[i + 1] && !argv[i + 1].startsWith('--'), 'invalid or incomplete argument');
    assert(result[key] === undefined, `duplicate argument ${key}`);
    result[key] = path.resolve(argv[i + 1]);
  }
  for (const key of allowed) assert(result[key], `required ${key}`);
  return result;
}

/** Block network and external processes before donor modules are imported. */
function installOfflineGuard() {
  report.offline = { networkAttempts: [], processAttempts: [], completions: 0 };
  const block = (category, method) => () => {
    report.offline[category].push(method);
    throw new Error(`OFFLINE_PROBE_BLOCKED:${method}`);
  };
  globalThis.fetch = block('networkAttempts', 'fetch');
  for (const [object, names] of [
    [net, ['connect', 'createConnection', 'createServer']],
    [tls, ['connect', 'createServer']], [http, ['request', 'get', 'createServer']],
    [https, ['request', 'get', 'createServer']], [dns, ['lookup', 'resolve', 'resolve4', 'resolve6']],
    [dns.promises, ['lookup', 'resolve', 'resolve4', 'resolve6']],
  ]) for (const name of names) object[name] = block('networkAttempts', name);
  net.Socket.prototype.connect = block('networkAttempts', 'Socket.connect');
  for (const name of ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']) {
    childProcess[name] = block('processAttempts', name);
  }
  syncBuiltinESMExports();
}

const sources = [
  ['apps/cli/src/bin.ts', 'runCli: profile dispatch and layered launch environment'],
  ['apps/cli/src/profile-boot.ts', 'prepareProfile/runProfile: native profile resolution, patch order, Loader settlement and startup audit'],
  ['packages/boot/app-boot/src/profile-context.ts', 'readProfilePatches: bundle -> profile -> home -> argv -> telemetry'],
  ['packages/boot/app-boot/src/index.ts', 'boot/auditStartupEntries: required activation policy'],
  ['packages/bundle/base/cordis.patch.yml', 'full base composition and independent auxiliary routes'],
  ['packages/bundle/headless/cordis.patch.yml', 'headless app rows'],
  ['packages/bundle/headless/src/index.ts', 'default selection, installModelSelection and native agent creation'],
  ['packages/core/agent-default-model/src/index.ts', 'currentSelection'],
  ['packages/core/agent/src/model-selection.ts', 'installModelSelection: assembled selection -> agent/request waterfall'],
  ['packages/subagent/subagent/src/child-agent.ts', 'resolveChildAgentOptions: latest request inheritance and explicit child overrides'],
  ['packages/subagent/subagent-in-process-driver/src/index.ts', 'startInProcessRun consumes resolveChildAgentOptions'],
  ['packages/compaction/compaction-basic/src/config.ts', 'resolveTargetPolicy/resolveCompactSpec: output reservation and headroom'],
  ['packages/compaction/compaction-basic/src/index.ts', 'compactIfNeeded and summarize'],
  ['packages/compaction/compaction-basic/src/summarizer.ts', 'summarizeWithLlm: configured -> latest request -> AgentOptions target'],
  ['packages/llm/llm-pi-ai/src/models.ts', 'createModels clears installed catalog routes'],
  ['packages/llm/llm-pi-ai/src/index.ts', 'explicit routes and credential reference resolution'],
];

async function main() {
  const args = options(process.argv.slice(2));
  const destination = args['--report'];
  const reportParent = path.dirname(destination);
  assert(fs.existsSync(reportParent), 'report directory must already exist');
  assert(fs.realpathSync(reportParent) === reportParent, 'report directory must be canonical');
  const parentStat = fs.statSync(reportParent);
  assert(parentStat.isDirectory() && parentStat.uid === process.getuid() && (parentStat.mode & 0o077) === 0, 'report directory must be owned and private');
  const donor = fs.realpathSync(args['--donor']);
  const patch = fs.realpathSync(args['--patch']);
  const home = args['--home'];
  assert(destination !== patch && !destination.startsWith(`${donor}/`), 'report must not overwrite an input or donor file');
  try { reportFd = fs.openSync(destination, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600); }
  catch (error) { throw new Error(error.code === 'EEXIST' ? 'report destination already exists' : 'cannot create private report'); }
  fs.fchmodSync(reportFd, 0o600);
  reportPath = destination;
  assert(!home.startsWith(`${donor}/`) && home !== donor, 'home must be outside donor');
  assert(fs.realpathSync(path.dirname(home)) === path.dirname(home), 'home parent must be canonical');
  if (!fs.existsSync(home)) fs.mkdirSync(home, { mode: 0o700 });
  const homeStat = fs.lstatSync(home);
  assert(homeStat.isDirectory() && homeStat.uid === process.getuid() && (homeStat.mode & 0o777) === 0o700, 'home must be an owned mode700 directory');
  assert(fs.realpathSync(home) === home, 'home must not traverse symlinks');
  assert(fs.readdirSync(home).length === 0, 'home must be an empty disposable directory');
  const head = childProcess.execFileSync('git', ['--no-optional-locks', '-C', donor, 'rev-parse', 'HEAD'], {
    env: { PATH: process.env.PATH, GIT_OPTIONAL_LOCKS: '0' }, encoding: 'utf8', timeout: 5000,
  }).trim();
  assert.equal(head, PIN, 'unsupported donor source pin');
  report.inputs = { donor, head, patch, patchSha256: sha(patch), home, node: process.version, executable: process.execPath, probeSha256: sha(process.argv[1]) };
  report.command = [process.execPath, process.argv[1], ...process.argv.slice(2)];
  report.sourceReferences = sources.map(([file, method]) => ({ file, method, sha256: sha(path.join(donor, file)) }));
  report.builtHashes = Object.fromEntries([
    ...fs.readdirSync(path.join(donor, 'apps/cli/lib')).filter(file => file.endsWith('.js')).map(file => `apps/cli/lib/${file}`),
    'packages/boot/app-boot/lib/index.js',
    'packages/core/agent/lib/index.js', 'packages/subagent/subagent/lib/index.js',
    'packages/compaction/compaction-basic/lib/index.js', 'packages/llm/llm-pi-ai/lib/index.js',
  ].map(file => [file, sha(path.join(donor, file))]));

  // A component probe does not load .env files or inherited credentials/proxies.
  const inheritedPath = process.env.PATH;
  for (const key of Object.keys(process.env)) delete process.env[key];
  process.env.PATH = inheritedPath;
  process.env.DSH_HOME = home;
  process.env.DSH_TELEMETRY_DISABLED = '1';
  process.chdir(home);
  installOfflineGuard();
  watchdog = setTimeout(() => {
    report.status = 'FAIL'; report.error = '45 second finite-probe deadline exceeded'; finish(); process.exit(1);
  }, 45000);
  const requireDonor = createRequire(path.join(donor, 'apps/cli/package.json'));
  const loadPackage = name => import(pathToFileURL(requireDonor.resolve(name)).href);
  const [profileBoot, appBoot, launch, cordis, agentModule, subagent, basic] = await Promise.all([
    import(pathToFileURL(path.join(donor, 'apps/cli/lib/profile-boot.js')).href),
    loadPackage('@deepseek-ai/dsh-app-boot'), loadPackage('@deepseek-ai/dsh-launch-environment'),
    loadPackage('@deepseek-ai/cordis'), loadPackage('@deepseek-ai/dsh-agent'),
    loadPackage('@deepseek-ai/dsh-subagent'), loadPackage('@deepseek-ai/dsh-compaction-basic'),
  ]);
  const profile = profileBoot.prepareProfile('headless');
  const overlay = appBoot.loadOverlayPatches('native-probe', patch);
  const context = {
    name: 'headless', dir: profile.dir, patchPath: profile.patchPath, installAnchor: profileBoot.INSTALL_ANCHOR,
    cwd: home, home, startedBundles: profile.layers.map(layer => layer.packageName),
    overlays: overlay, telemetryDisabledEnv: '1',
  };
  const patches = appBoot.readProfilePatches('native-probe', context, profile);
  const rows = appBoot.composeEntries([patches]);
  const row = id => { const hit = rows.find(item => item.id === id); assert(hit, `missing effective row ${id}`); return hit; };
  const disabled = ['llm-deepseek', 'llm-deepseek-account', 'deepseek-account', 'session-title-llm',
    'web-search-deepseek', 'tool-web', 'tool-goal', 'command-goal', 'goal-round-driver', 'tool-workflow', 'session-telemetry-otel'];
  const webEnabled = validateWebOverlay(overlay);
  for (const id of disabled.filter(id=>!(webEnabled&&id==='tool-web'))) assert.equal(row(id).disabled, true, `independent route must be disabled: ${id}`);
  assert.equal(overlay.some(item => item.name || item.remove), false, 'probe accepts exact reviewed web insert and row updates only');
  assert(!fs.readFileSync(patch, 'utf8').includes('!!js'), 'probe patch must not contain executable expressions');
  assert(!JSON.stringify(overlay).includes('__jsExpr'), 'probe patch must not contain expression nodes');
  const permittedRows = new Set(['llm-pi-ai', 'agent-default-model', 'compaction-basic', ...disabled, ...(webEnabled?['web','web-fetch-http']:[])]);
  for (const item of overlay) {
    if (webEnabled && item.insert) continue; // validateWebOverlay already checked exact whole insert.
    assert(permittedRows.has(item.id), 'unsupported probe overlay row');
    assert(Object.keys(item).every(key => ['id', 'config', 'disabled'].includes(key)), 'unsupported row update');
  }
  const configured = row('agent-default-model').config;
  assert(Object.keys(configured).every(key => ['provider', 'model', 'reasoningEffort'].includes(key)), 'unsupported default selection field');
  assert.deepEqual(Object.keys(row('llm-pi-ai').config), ['providers'], 'only an explicit provider dictionary is accepted');
  const providerConfig = row('llm-pi-ai').config.providers;
  assert.deepEqual(Object.keys(providerConfig), [configured.provider], 'exactly the selected local provider may be active');
  const route = providerConfig[configured.provider];
  assert(Object.keys(route).every(key => ['api', 'baseURL', 'apiKeyEnv', 'models', 'timeoutMs'].includes(key)), 'unsupported route field (inline auth/headers forbidden)');
  assert.equal(route.api, 'openai-completions', 'only the audited local protocol is accepted');
  assert.equal(route.models.length, 1, 'exactly one explicit local model required');
  assert.equal(route.models[0].id, configured.model, 'model identity must match the selected route');
  assert(!Object.hasOwn(route, 'apiKey'), 'only credential references may be configured');
  const url = new URL(route.baseURL);
  assert(!url.username && !url.password && !url.search && !url.hash, 'endpoint must not serialize credentials');
  report.composition = {
    layerOrder: ['bundle', 'profile', 'home', 'argv', 'telemetry'], bundles: context.startedBundles,
    rows: rows.map(item => ({ id: item.id, name: item.name, disabled: typeof item.disabled === 'boolean' ? item.disabled : 'native-expression' })),
    selected: configured, provider: { api: route.api, baseURL: route.baseURL, apiKeyEnv: route.apiKeyEnv, models: route.models },
    compaction: row('compaction-basic').config ?? {}, disabled,
  };
  checked('effective-native-patch-stack', { rows: rows.length });

  // Hold only the two one-shot app rows. The complete base tree still mounts,
  // evaluates its native expressions, settles and passes the native startup audit.
  const inspectionPatch = path.join(home, 'inspection.patch.json');
  fs.writeFileSync(inspectionPatch, JSON.stringify([{ id: 'headless-startup', disabled: true }, { id: 'headless-runner', disabled: true }]), { mode: 0o600 });
  const environment = launch.createLaunchEnvironmentSnapshot([{ source: 'process', values: { ...process.env } }]);
  booted = await profileBoot.runProfile({ environment, profile: 'headless', patchFiles: [patch, inspectionPatch], args: [] });
  const ctx = booted.ctx;
  const entries = [...ctx.loader.entries()];
  report.startup = {
    heldAppRows: ['headless-startup', 'headless-runner'],
    entries: entries.map(entry => ({ id: entry.options.id, disabled: entry.disabled, fiberState: entry.fiber?.state ?? null })),
  };
  const selected = ctx.agentDefaultModel.currentSelection();
  assert.deepEqual(selected, configured);
  const registered = ctx.llm.listProviders();
  assert.equal(registered.length, 1, 'runtime must register exactly one provider');
  assert.equal(registered[0].id ?? registered[0].provider, selected.provider);
  const info = await ctx.llm.resolveModelInfo(selected.provider, selected.model);
  report.registeredProviders = registered;
  report.modelInfo = info;
  checked('full-native-startup-with-held-app', { entries: entries.length });

  // Execute the same native selection hook installed by headless, using the
  // native request waterfall in an isolated Context (no agent turn is queued).
  const requestCtx = new cordis.Context();
  secondary = requestCtx;
  const ref = { current: selected, assembled: undefined };
  await requestCtx.plugin((await loadPackage('@deepseek-ai/dsh-system-prompt')).default);
  const releaseSelection = agentModule.installModelSelection(requestCtx, ref);
  const assembled = await requestCtx.systemPrompt.assemble();
  assert.equal(assembled.variables.provider, selected.provider);
  assert.equal(assembled.variables.model, selected.model);
  const nativeSession = (await loadPackage('@deepseek-ai/dsh-session')).Session;
  const session = nativeSession.create('native-probe-session');
  const parent = { options: { provider: 'created-before-route', model: 'created-before-route', maxTokens: info.defaultMaxTokens }, session };
  const routed = await agentModule.agentEvents(requestCtx, parent).waterfall('agent/request', {
    turn: 1, step: 1, signal: new AbortController().signal,
  }, () => Promise.resolve({ provider: 'forbidden-seed', model: 'forbidden-seed', temperature: 0.2 }));
  assert.equal(routed.provider, selected.provider); assert.equal(routed.model, selected.model);
  session.append('request/header', { header: { config: { ...routed, maxTokens: info.defaultMaxTokens } }, reason: 'initial' });
  const inherited = subagent.resolveChildAgentOptions(parent, undefined, 1);
  assert.equal(inherited.provider, selected.provider); assert.equal(inherited.model, selected.model);
  const override = subagent.resolveChildAgentOptions(parent, { provider: 'probe-explicit-other', model: 'probe-explicit-other' }, 1);
  assert.equal(override.provider, 'probe-explicit-other');
  let unknownRouteError;
  try { await ctx.llm.resolveModelInfo(override.provider, override.model); assert.fail('unregistered child route unexpectedly resolved'); }
  catch (error) { assert(/not registered|no adapter|unknown provider/i.test(error.message), error.message); unknownRouteError = { message: error.message, code: error.code }; }
  report.routes.main = { method: 'installModelSelection + native prompt assembly + agentEvents(agent/request)', selected, assembledSelection: ref.assembled, routed };
  report.routes.child = { method: 'resolveChildAgentOptions (used by native spawn/fork driver)', createdParent: parent.options, latestRequest: routed, inherited, explicitOverrideAccepted: override, unregisteredOverrideError: unknownRouteError };
  releaseSelection();
  checked('native-main-and-child-selection', {});

  // Observe the real summarizer's GenerateOptions; stop before adapter/network.
  let summaryCall;
  const marker = new Error('NATIVE_PROBE_NO_COMPLETION');
  const stopStream = ctx.on('llm/stream', function* (options) { summaryCall = options; throw marker; }, { prepend: true });
  try { await ctx.compaction.summarize({ messages: [] }, parent); assert.fail('summary interception missing'); }
  catch (error) { assert.equal(error, marker); }
  stopStream();
  assert.equal(summaryCall.provider, selected.provider); assert.equal(summaryCall.model, selected.model);
  report.routes.compaction = {
    method: 'actual mounted BasicCompactionEngine.summarize -> native summarizeWithLlm -> rejecting llm/stream observer',
    provider: summaryCall.provider, model: summaryCall.model, maxTokens: summaryCall.maxTokens, purpose: summaryCall.purpose,
    config: ctx.compaction.config,
  };
  checked('native-compaction-route-before-stream', {});

  // Probe the native pressure branch at its source-defined threshold. A private
  // token meter reports controlled counts; the native policy and route info run.
  const policy = ctx.compaction.config;
  assert.equal(policy.modelPolicies.length, 0, 'pressure probe requires the renderer single-policy profile');
  const capacity = info.context.contextWindow;
  const reservation = info.defaultMaxTokens ?? 0;
  const threshold = Math.floor(Math.min(capacity * policy.thresholdRatio, capacity - reservation - policy.headroomTokens));
  assert(threshold > 0, 'positive native pressure budget required');
  const measure = ctx.tokenMeter.measure(session);
  let totalTokens = threshold - 1;
  let prunes = 0;
  const pressureCtx = new cordis.Context();
  pressureCtx.provide('llm', ctx.llm);
  pressureCtx.provide('tokenMeter', { measure: () => ({ ...measure, totalTokens }) });
  pressureCtx.provide('sessions', ctx.sessions);
  pressureCtx.provide('toolResultPruner', { pruneSession: () => { prunes += 1; } });
  await pressureCtx.plugin(basic.default, { ...report.composition.compaction, auto: false });
  try {
    await pressureCtx.compaction.compactIfNeeded(parent, 'pressure', new AbortController().signal);
    assert.equal(prunes, 0, 'no pruning below pressure threshold');
    totalTokens = threshold;
    await pressureCtx.compaction.compactIfNeeded(parent, 'pressure', new AbortController().signal);
    assert.equal(prunes, 1, 'native threshold must admit pruning at exact boundary');
    session.append('request/header', { header: { config: { ...routed, maxTokens: capacity + 1 } }, reason: 'initial' });
    let invalidReservation;
    try { await pressureCtx.compaction.compactIfNeeded(parent, 'pressure', new AbortController().signal); assert.fail('invalid reservation accepted'); }
    catch (error) { assert(/leaving no message budget/.test(error.message), error.message); invalidReservation = error.message; }
    report.pressure = { contextWindow: capacity, reservedCompletionTokens: reservation, headroomTokens: policy.headroomTokens, thresholdRatio: policy.thresholdRatio, thresholdTokens: threshold, observations: [{ totalTokens: threshold - 1, pruneCalls: 0 }, { totalTokens: threshold, pruneCalls: 1 }], invalidRequestReservation: { maxTokens: capacity + 1, rejected: invalidReservation }, meter: 'controlled private fixture; native policy, model metadata and branch' };
    checked('native-pressure-threshold-negative-and-boundary', {});
  } finally { await pressureCtx.fiber.dispose(); }
  assert.deepEqual(report.offline.networkAttempts, [], 'no network attempt allowed');
  assert.deepEqual(report.offline.processAttempts, [], 'no child process attempt allowed');
  report.gaps = [
    'The two headless application rows are held; this is full base startup and native component routing, not a completed CLI job.',
    'Main routing uses native prompt-selection assembly and waterfall hooks with controlled agent/session input; no agent loop turn or full deployed prompt is executed.',
    'Child inheritance and explicit override are executed through the native resolver; no child turn is spawned. Explicit alternate routes remain possible and fail only at registry resolution unless separately constrained.',
    'Compaction is intercepted before adapter streaming: no summary output, checkpoint persistence, compression quality, or provider request compatibility is established.',
    'Pressure counts are synthetic; native configuration/model metadata and the exact threshold branch are exercised. Real token-meter accuracy and long-context compaction remain untested.',
    'No real model inference, actual endpoint authentication, tool effects, or deployment isolation is tested. Offline guards are test process guards, not a production sandbox.',
  ];
  report.status = 'PASS';
}

try { await main(); }
catch (error) { report.status = 'FAIL'; report.error = { message: error.message, stack: error.stack }; }
finally {
  try { if (secondary) await secondary.fiber.dispose(); if (booted) await booted.ctx.fiber.dispose(); }
  catch (error) { report.status = 'FAIL'; report.cleanupError = error.message; }
  if (watchdog) clearTimeout(watchdog);
  finish();
}
process.stdout.write(`${JSON.stringify({ status: report.status, report: reportPath, checks: report.checks.length, error: report.error?.message })}\n`);
process.exit(report.status === 'PASS' ? 0 : 1);
