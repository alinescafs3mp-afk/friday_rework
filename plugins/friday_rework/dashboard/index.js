/* Native Hermes Dashboard SDK; no build, second chat, credentials or polling. */
(function () {
  "use strict";
  const sdk = window.__HERMES_PLUGIN_SDK__;
  const {React: R, fetchJSON, authedFetch} = sdk;
  const h = R.createElement;
  const base = "/api/plugins/friday_rework";
  function Console() {
    const [profiles, setProfiles] = R.useState([]), [profile, setProfile] = R.useState("");
    const [view, setView] = R.useState("users"), [query, setQuery] = R.useState("");
    const [offset, setOffset] = R.useState(0), [filters, setFilters] = R.useState({});
    const [data, setData] = R.useState(null), [error, setError] = R.useState("");
    const [session, setSession] = R.useState(null), [busy, setBusy] = R.useState(false);
    const [control, setControl] = R.useState(null), [edit, setEdit] = R.useState({kind: "model", slot: "main", route: "0", web: "exa-paid", timeout: "30", chars: "15000", name: "", enabled: true, key: "agent.max_turns", value: "30"});
    const [setup, setSetup] = R.useState({platform: "telegram", account_id: "", user_id: "", runtime_profile: "", template: ""});
    const [prepared, setPrepared] = R.useState(null), [secretName, setSecretName] = R.useState("");
    const [secretValue, setSecretValue] = R.useState("");
    R.useEffect(() => { let active = true;
      fetchJSON(base + "/profiles").then(p => { if (active) { setProfiles(p); setProfile(p[0] || ""); } })
        .catch(() => { if (active) setError("Administrator access or native configuration unavailable."); });
      return () => { active = false; };
    }, []);
    async function load(selected = view) {
      if (!profile || busy) return;
      setBusy(true); setError(""); setSession(null);
      try {
        const params = new URLSearchParams({profile});
        if (selected === "conversations") {
          params.set("query", query); params.set("offset", String(offset));
          Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
        }
        setData(await fetchJSON(base + "/" + selected + "?" + params));
      } catch (_) { setError("Native state unavailable or request refused."); setData(null); }
      finally { setBusy(false); }
    }
    R.useEffect(() => { setData(null); setSession(null); setControl(null); setOffset(0); }, [profile, view]);
    R.useEffect(() => { setPrepared(null); setSecretValue(""); }, [profile]);
    async function change(row, enabled, role = row.role) {
      setBusy(true); setError("");
      try { await fetchJSON(base + "/users?" + new URLSearchParams({profile}), {
        method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({platform: row.platform, transport_profile: row.transport_profile,
          account_id: row.account_id, user_id: row.user_id, enabled, role})});
        setData(await fetchJSON(base + "/users?" + new URLSearchParams({profile})));
      } catch (_) { setError("Access write unconfirmed. Reload before another action."); }
      finally { setBusy(false); }
    }
    async function approve(row) {
      const accounts = await fetchJSON(base + "/users?" + new URLSearchParams({profile}));
      const candidates = accounts.accounts.filter(a => a.platform === row.platform && a.transport_profile === profile);
      if (candidates.length !== 1) { setError("No unique configured receiving account for this request."); return; }
      setBusy(true); setError("");
      try { const a = candidates[0]; await fetchJSON(base + "/pairing/approve?" + new URLSearchParams({profile}), {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({platform: a.platform, transport_profile: a.transport_profile,
          account_id: a.account_id, request_id: row.request_id})});
        setData(await fetchJSON(base + "/pairing?" + new URLSearchParams({profile})));
      } catch (_) { setError("Onboarding unconfirmed; native grant may exist. Inspect current users before continuing."); }
      finally { setBusy(false); }
    }
    async function onboard(action) {
      if (!profile || busy) return;
      setBusy(true); setError("");
      try {
        const identity = {platform: setup.platform, transport_profile: profile, account_id: setup.account_id,
          user_id: setup.user_id, expected_config_sha256: prepared ? prepared.config_sha256 : data.config_sha256};
        let body = action === "prepare" ? {...identity, runtime_profile: setup.runtime_profile, template: setup.template}
          : {...identity, generation: prepared.generation};
        if (action === "credentials") body = {...body, name: secretName, value: secretValue};
        const result = await fetchJSON(base + "/onboarding/" + action + "?" + new URLSearchParams({profile}), {
          method: action === "credentials" ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
        if (action === "prepare") { setPrepared(result); setSecretName((result.required_names || [])[0] || "");
          setProfiles(await fetchJSON(base + "/profiles")); }
        else setPrepared({...prepared, state: result.state, enabled: result.enabled});
      } catch (_) { setError("Setup write unconfirmed or refused. Inspect current native state before any further action."); }
      finally { setSecretValue(""); setBusy(false); }
    }
    async function open(row, messageOffset = 0) {
      setBusy(true); setError("");
      try { setSession(await fetchJSON(base + "/conversations/" + encodeURIComponent(row.session_id)
        + "?" + new URLSearchParams({profile, limit: "100", offset: String(messageOffset)}))); }
      catch (_) { setError("Conversation unavailable or scope refused."); }
      finally { setBusy(false); }
    }
    async function download(task, file, kind = "attachments") {
      setBusy(true); setError("");
      try {
        const response = await authedFetch(base + "/" + kind + "/" + encodeURIComponent(task.existing_task_id)
          + "/" + file.index + "?" + new URLSearchParams({profile}));
        if (!response.ok) throw new Error("refused");
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a"); link.href = url; link.download = file.logical_name;
        link.click(); URL.revokeObjectURL(url);
      } catch (_) { setError("Attachment ownership or current bytes unproved."); }
      finally { setBusy(false); }
    }
    async function taskControl(task, action) {
      setBusy(true); setError(""); setControl(null);
      try { const result = await fetchJSON(base + "/tasks/" + encodeURIComponent(task.existing_task_id) + "/control?" + new URLSearchParams({profile}), {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({action})});
        setControl(result);
        if (!result.accepted) setError("Control refused or outcome unknown. Reload retained task state; do not assume execution stopped.");
        setData(await fetchJSON(base + "/tasks?" + new URLSearchParams({profile})));
      } catch (_) { setError("Control outcome unknown. Reload task state before any further action."); }
      finally { setBusy(false); }
    }
    async function saveSettings() {
      setBusy(true); setError(""); setControl(null);
      try {
        let values;
        if (edit.kind === "model") values = {slot: edit.slot, ...data.typed_options.local_routes[Number(edit.route)]};
        else if (edit.kind === "web") values = {profile: edit.web, extract_timeout: Number(edit.timeout), extract_char_limit: Number(edit.chars)};
        else if (["toolset", "skill"].includes(edit.kind)) values = {name: edit.name, enabled: edit.enabled};
        else values = {key: edit.key, value: edit.key === "streaming.enabled" ? edit.enabled : Number(edit.value)};
        setControl(await fetchJSON(base + "/settings?" + new URLSearchParams({profile}), {
          method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({kind: edit.kind, expected_sha256: data.config_sha256, values})}));
        setData(await fetchJSON(base + "/effective?" + new URLSearchParams({profile})));
      } catch (_) { setError("Configuration write refused or unconfirmed. Reload before another edit."); }
      finally { setBusy(false); }
    }
    async function scheduleControl(row, action) {
      setBusy(true); setError("");
      try { setControl(await fetchJSON(base + "/schedules/" + encodeURIComponent(row.id) + "/control?" + new URLSearchParams({profile}), {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({action})}));
        setData(await fetchJSON(base + "/schedules?" + new URLSearchParams({profile})));
      } catch (_) { setError("Schedule write unconfirmed. Inspect current native state before continuing."); }
      finally { setBusy(false); }
    }
    const button = (label, fn, extra = {}) => h("button", {type: "button", disabled: busy, onClick: fn, ...extra}, label);
    const select = (field, values) => h("select", {"aria-label": field, value: edit[field], disabled: busy, onChange: e => setEdit({...edit, [field]: e.target.value})},
      ...values.map(v => h("option", {key: v, value: v}, v)));
    const number = field => h("input", {"aria-label": field, type: "number", value: edit[field], disabled: busy, onChange: e => setEdit({...edit, [field]: e.target.value})});
    const enabled = () => h("label", null, "Enabled ", h("input", {type: "checkbox", checked: edit.enabled, onChange: e => setEdit({...edit, enabled: e.target.checked})}));
    const renderUser = row => h("li", {key: row.principal_id},
      h("span", null, `${row.platform} / ${row.transport_profile} / ${row.account_id} / ${row.user_id}: ${row.enabled ? "enabled" : "disabled"} (${row.role}) `),
      button(row.enabled ? "Disable" : "Enable", () => change(row, !row.enabled)),
      button(row.role === "admin" ? "Channel user role" : "Channel admin role", () => change(row, row.enabled, row.role === "admin" ? "user" : "admin")));
    return h("section", {"aria-label": "Friday administration", style: {padding: "1rem", display: "grid", gap: "1rem"}},
      h("h1", null, "Friday Administration"),
      h("label", null, "Product profile ", h("select", {value: profile, disabled: busy, onChange: e => setProfile(e.target.value)},
        ...profiles.map(p => h("option", {key: p, value: p}, p)))),
      h("nav", null, ...["users", "onboarding", "pairing", "conversations", "tasks", "effective", "schedules"].map(v => button(v, () => setView(v), {key: v}))),
      view === "conversations" ? h("label", null, "Search ", h("input", {value: query, maxLength: 512, onChange: e => setQuery(e.target.value)})) : null,
      view === "conversations" ? h("div", null,
        ...["platform", "user_id", "account_id", "chat_id", "thread_id"].map(k => h("label", {key: k}, k + " ",
          h("input", {value: filters[k] || "", maxLength: 512, onChange: e => setFilters({...filters, [k]: e.target.value})}))),
        button("Previous native page", () => setOffset(Math.max(0, offset - 100))),
        button("Next native page", () => setOffset(Math.min(100000, offset + 100))),
        h("span", null, " Native page offset: " + offset + ". Load to apply; an empty filtered page does not prove no later matches.")) : null,
      button("Load current native state", () => load()),
      error ? h("p", {role: "alert"}, error) : null,
      control ? h("pre", {role: "status"}, JSON.stringify(control, null, 2)) : null,
      ["users", "pairing"].includes(view) ? h("p", null, "Select the receiving account profile for user access and pairing. Execution profiles do not own these controls.") : null,
      view === "onboarding" && data ? h("div", {"aria-label": "New private Friday profile"},
        h("p", null, "Prepare a new private profile, capture its scoped keys, approve native channel access, then activate. Incomplete setup stays disabled."),
        ...["platform", "account_id", "user_id", "runtime_profile"].map(k => h("label", {key: k}, k + " ",
          h("input", {value: setup[k], disabled: busy || !!prepared, maxLength: k.includes("profile") ? 64 : 512,
            onChange: e => setSetup({...setup, [k]: e.target.value})}))),
        h("label", null, "Approved configuration ", h("select", {value: setup.template, disabled: busy || !!prepared,
          onChange: e => setSetup({...setup, template: e.target.value})}, h("option", {value: ""}, "Select"),
          ...data.templates.map(t => h("option", {key: t, value: t}, t)))),
        button("Prepare disabled profile", () => onboard("prepare"), {disabled: busy || !!prepared || !setup.template}),
        !prepared ? h("ul", null, ...(data.pending || []).map(row => h("li", {key: row.principal_id},
          row.runtime_profile + ": " + row.state + " ", row.recoverable ? button("Continue existing disabled setup", () => {
            setSetup({platform: row.platform, account_id: row.account_id, user_id: row.user_id,
              runtime_profile: row.runtime_profile, template: row.template}); setPrepared(row);
            setSecretName((row.required_names || [])[0] || ""); setSecretValue("");
          }) : null))) : null,
        prepared ? h("div", null,
          h("p", {role: "status"}, prepared.state),
          h("select", {value: secretName, disabled: busy || prepared.enabled, onChange: e => setSecretName(e.target.value)},
            ...(prepared.required_names || []).map(n => h("option", {key: n, value: n}, n))),
          h("input", {type: "password", autoComplete: "new-password", value: secretValue, disabled: busy || prepared.enabled,
            "aria-label": "New profile scoped key", onChange: e => setSecretValue(e.target.value)}),
          button("Store scoped key", () => onboard("credentials"), {disabled: busy || prepared.enabled || !secretName || !secretValue}),
          button("Activate complete profile", () => onboard("activate"), {disabled: busy || prepared.enabled})) : null) : null,
      view === "users" && data ? h("ul", null, ...data.users.map(renderUser)) : null,
      view === "pairing" && data ? h("ul", null, ...data.pending.map(row => h("li", {key: row.request_id || row.user_id},
        `${row.platform} / ${row.user_id} `, button("Approve native access", () => approve(row), {disabled: busy || !row.request_id})))) : null,
      view === "conversations" && Array.isArray(data) ? h("ul", null, ...data.map(row => h("li", {key: row.session_id},
        button(row.title || row.session_id, () => open(row)), h("pre", null, JSON.stringify(row.identity, null, 2))))) : null,
      session ? h("article", null, h("h2", null, session.session_id),
        h("nav", {"aria-label": "Message pages"},
          button("Previous messages", () => open(session, session.page.previous_offset), {disabled: busy || session.page.previous_offset === null}),
          button("Next messages", () => open(session, session.page.next_offset), {disabled: busy || session.page.next_offset === null}),
          h("span", null, ` Messages offset ${session.page.offset}, count ${session.page.count}; ${session.page.state === "END" ? "end of history" : session.page.state === "MORE" ? "more messages available" : "bounded navigation limit reached"}.`)),
        ...session.messages.map((m, i) => h("div", {key: m.id || i}, h("strong", null, m.role), h("pre", {style: {whiteSpace: "pre-wrap"}}, m.content))),
        h("pre", null, JSON.stringify(session.tasks, null, 2)),
        ...session.tasks.flatMap(task => task.attachments.map(file =>
          button("Download " + file.logical_name, () => download(task, file), {key: task.existing_task_id + "/" + file.index}))),
        ...session.tasks.flatMap(task => task.inputs.map(file =>
          button("Received attachment " + file.logical_name, () => download(task, file, "inputs"), {key: task.existing_task_id + "/input/" + file.index})))) : null,
      ["tasks", "effective"].includes(view) && data ? h("pre", {style: {whiteSpace: "pre-wrap"}}, JSON.stringify(data, null, 2)) : null,
      view === "tasks" && Array.isArray(data) ? h("ul", null, ...data.map(task => h("li", {key: task.existing_task_id}, task.existing_task_id,
        button("Check task", () => taskControl(task, "status")),
        button("Pause task", () => taskControl(task, "pause"), {disabled: busy || task.quiescent}),
        button("Cancel task", () => taskControl(task, "cancel"), {disabled: busy || task.quiescent})))) : null,
      view === "schedules" && Array.isArray(data) ? h("ul", null, ...data.map(row => h("li", {key: row.id}, row.name || row.id,
        button(row.enabled ? "Pause schedule" : "Resume schedule", () => scheduleControl(row, row.enabled ? "pause" : "resume"))))) : null,
      view === "effective" && data && data.typed_options ? h("fieldset", {disabled: busy}, h("legend", null, "Operational settings"),
        select("kind", ["model", "web", "toolset", "skill", "operational"]),
        edit.kind === "model" ? h("div", null, select("slot", data.typed_options.model_slots),
          h("select", {"aria-label": "Local model route", value: edit.route, onChange: e => setEdit({...edit, route: e.target.value})},
            ...data.typed_options.local_routes.map((r, i) => h("option", {key: i, value: String(i)}, `${r.provider} / ${r.model} / ${r.base_url}`)))) : null,
        edit.kind === "web" ? h("div", null, select("web", data.typed_options.web_backends), number("timeout"), number("chars")) : null,
        ["toolset", "skill"].includes(edit.kind) ? h("div", null, select("name", ["", ...data.typed_options[edit.kind === "toolset" ? "toolsets" : "skills"]]), enabled()) : null,
        edit.kind === "operational" ? h("div", null, select("key", data.typed_options.operational), edit.key === "streaming.enabled" ? enabled() : number("value")) : null,
        button("Save operational settings", saveSettings),
        h("p", null, "Saved settings apply through the next native session or reload. Existing worker bindings and original deadlines remain fixed.")) : null,
      h("p", null, "Control needs the owning gateway and a valid native administrator session. Lost responses remain unknown. Channel roles do not grant Dashboard access."));
  }
  window.__HERMES_PLUGINS__.register("friday_rework", Console);
})();
