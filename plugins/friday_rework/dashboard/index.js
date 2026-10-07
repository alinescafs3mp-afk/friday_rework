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
    R.useEffect(() => { setData(null); setSession(null); setOffset(0); }, [profile, view]);
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
        if (action === "prepare") { setPrepared(result); setSecretName((result.required_names || [])[0] || ""); }
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
    const button = (label, fn, extra = {}) => h("button", {type: "button", disabled: busy, onClick: fn, ...extra}, label);
    const renderUser = row => h("li", {key: row.principal_id},
      h("span", null, `${row.platform} / ${row.transport_profile} / ${row.account_id} / ${row.user_id}: ${row.enabled ? "enabled" : "disabled"} (${row.role}) `),
      button(row.enabled ? "Disable" : "Enable", () => change(row, !row.enabled)),
      button(row.role === "admin" ? "Channel user role" : "Channel admin role", () => change(row, row.enabled, row.role === "admin" ? "user" : "admin")));
    return h("section", {"aria-label": "Friday administration", style: {padding: "1rem", display: "grid", gap: "1rem"}},
      h("h1", null, "Friday Administration"),
      h("label", null, "Product profile ", h("select", {value: profile, disabled: busy, onChange: e => setProfile(e.target.value)},
        ...profiles.map(p => h("option", {key: p, value: p}, p)))),
      h("nav", null, ...["users", "onboarding", "pairing", "conversations", "tasks", "effective"].map(v => button(v, () => setView(v), {key: v}))),
      view === "conversations" ? h("label", null, "Search ", h("input", {value: query, maxLength: 512, onChange: e => setQuery(e.target.value)})) : null,
      view === "conversations" ? h("div", null,
        ...["platform", "user_id", "account_id", "chat_id", "thread_id"].map(k => h("label", {key: k}, k + " ",
          h("input", {value: filters[k] || "", maxLength: 512, onChange: e => setFilters({...filters, [k]: e.target.value})}))),
        button("Previous native page", () => setOffset(Math.max(0, offset - 100))),
        button("Next native page", () => setOffset(Math.min(100000, offset + 100))),
        h("span", null, " Native page offset: " + offset + ". Load to apply; an empty filtered page does not prove no later matches.")) : null,
      button("Load current native state", () => load()),
      error ? h("p", {role: "alert"}, error) : null,
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
      h("p", null, "Task stop and configuration changes are unavailable until the owning-host control path is connected. Channel roles do not grant Dashboard access."));
  }
  window.__HERMES_PLUGINS__.register("friday_rework", Console);
})();
