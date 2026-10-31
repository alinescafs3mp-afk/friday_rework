# Exported exact definition excerpts; not a complete product module.
from __future__ import annotations

def _normalize_aux_provider(provider: Optional[str]) -> str:
    normalized = (provider or "auto").strip().lower()
    if normalized.startswith("custom:"):
        suffix = normalized.split(":", 1)[1].strip()
        if not suffix:
            return "custom"
        normalized = suffix
    if normalized == "codex":
        return "openai-codex"
    if normalized == "main":
        # Resolve to the actual main provider so named custom providers work.
        main_prov = (_read_main_provider() or "").strip().lower()
        if not main_prov or main_prov in {"auto", "main"}:
            return "custom"
        normalized = main_prov
    return _provider_alias_table().get(normalized, normalized)


def resolve_provider_client(
    provider: str, model: str = None, async_mode: bool = False, raw_codex: bool = False,
    explicit_base_url: str = None, explicit_api_key: Optional[Union[str, Callable[[], str]]] = None,
    api_mode: str = None, main_runtime: Optional[Dict[str, Any]] = None, is_vision: bool = False,
    task: Optional[str] = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """Central router: return a configured client (auth, base URL, API format) for a provider + optional model.
    The client always exposes ``.chat.completions.create()``; Codex/Responses providers get an adapter.
    ``provider``: built-in name, ``custom:<name>``, "custom" (OPENAI_BASE_URL + OPENAI_API_KEY) or "auto"
    (full auto-detection chain). ``model=None`` → provider's default aux model. ``raw_codex`` → bare OpenAI
    client for ``responses.stream()`` callers. ``api_mode`` forces "codex_responses"/"chat_completions"/
    "anthropic_messages" instead of auto-detect. Returns (client, resolved_model) or (None, None)."""
    from hermes_cli import friday_credential_admission as admission
    if admission.managed():
        provider, model, explicit_base_url, explicit_api_key, api_mode = admission.client_inputs(
            provider, model, explicit_base_url, explicit_api_key, api_mode, task=task)
        main_runtime = None
    _validate_proxy_env_urls()
    # Keep the pre-alias name so a custom_providers entry named like a built-in alias
    # (e.g. "kimi" → "kimi-coding") is still reachable via the named-custom branch.
    original_provider = (provider or "").strip().lower()
    provider = _normalize_aux_provider(provider)
    api_mode = _canonical_api_mode(str(api_mode or "")).lower() or None
    # MoA chokepoint: "moa" is not an HTTP provider; resolve to the aggregator so direct callers don't
    # dead-end in unknown-provider. Unresolvable preset → leave untouched for the normal diagnostic.
    if provider == "moa":
        _agg_provider, _agg_model = _resolve_moa_aggregator(model)
        if _agg_provider and _agg_model:
            original_provider = _agg_provider.strip().lower()
            provider = _normalize_aux_provider(_agg_provider)
            model = _agg_model
            # The moa:// facade endpoint/key belong to the virtual runtime, not the aggregator.
            if explicit_base_url and str(explicit_base_url).lower().startswith("moa://"):
                explicit_base_url = None
                explicit_api_key = None
    from agent.auxiliary_local_runtime import bare_llamacpp_endpoint
    local = bare_llamacpp_endpoint(original_provider, explicit_base_url, explicit_api_key)
    if local is not None:
        if not local[0]:
            logger.warning("resolve_provider_client: %s requested but no local llama.cpp server is running", original_provider)
            return None, None
        explicit_base_url, explicit_api_key = local
    # Model for concrete providers: caller ``model`` → catalog default (empty for OAuth-gated providers whose
    # lists drift) → configured main model (MoA → aggregator), keeping OAuth aux tasks off the Step-2 fallback.
    # Excluded: ``auto`` (a stale main slug could pair with any picked provider) and Nous + vision (the
    # Portal's tier-aware vision recommendation must win over a text-only model).
    if not model and provider != "auto" and not (provider == "nous" and is_vision):
        # ``auto`` is intentionally excluded: `_resolve_auto_route(main_runtime=...)` returns the model paired
        # with the provider it actually selected. Pre-filling an auto call from `_read_main_model()` can
        # leak a stale process-global runtime into a different provider (for example Claude model slug on
        # Codex OAuth) and override that correctly resolved model. 1. ``model`` argument (caller knew what
        # they wanted) 2. Provider's catalog default — cheap/fast model the provider registered via
        # ``ProviderProfile.default_aux_model`` or the legacy ``_API_KEY_PROVIDER_AUX_MODELS_FALLBACK``
        # dict. 3. User's main model from ``model.model`` in config.yaml. This is the load-bearing step for
        # OAuth providers: an xai-oauth user with grok-4.3 configured gets grok-4.3 for title generation
        # instead of silently dropping to whatever Step-2 fallback (#31845). When the main provider is MoA,
        # ``_read_main_model_for_aux()`` substitutes the preset's aggregator model — the preset NAME is
        # never a valid wire model id, so unset aux models default to the preset's acting model instead.
        # Each provider branch below sees a non-empty ``model`` whenever the user has *anything* configured
        # — no provider-specific empty-model guards needed. When the user has NOTHING configured (fresh
        # install, main_model also empty), the branches still hit their own missing-credentials returns and
        # ``_resolve_auto_route`` falls through to the Step-2 chain as before. Do NOT pre-fill a blank ``auto``
        # request from the config/main default here. Claude model sent to Codex after the main lane fell
        # back to gpt-5.5). Let _resolve_auto_route() return the actual current runtime model when the caller did
        # not explicitly request one. (# compression-current-model) Nous + vision is the one carve-out: the
        # branch below resolves its model from the Portal's tier-aware vision recommendation
        # (``_try_nous(vision= True)``), and ``final_model = model or default`` means anything pre-filled
        # here wins over that. The main chat model is routinely text-only (e.g. a ``:free`` chat SKU), so
        # pre-filling it sends the image to a model that cannot accept one and the Portal 404s. Leave
        # ``model`` unset and let the Portal slot through; only an explicit caller model may override it.
        model = _get_aux_model_for_provider(provider) or _read_main_model_for_aux() or model
    req = _ResolveRequest(
        provider, original_provider, model, async_mode, raw_codex,
        explicit_base_url, explicit_api_key, api_mode, main_runtime, is_vision, task,
    )
    branch = _EXPLICIT_PROVIDER_BRANCHES.get(provider)
    alias_identity = original_provider.removeprefix("custom:")
    # A configured provider whose name collides with a local-server alias is still a named
    # provider. Resolve it before the alias's generic ``custom`` branch, which otherwise loses
    # the configured base_url and can fall through to an unrelated credentialed provider.
    if branch is None or alias_identity in _LOCAL_SERVER_ALIASES:
        try:
            result = _resolve_named_custom_branch(req)
        except ImportError:
            result = None
        if result is not None:
            return result
    if branch is not None:
        return branch(req)
    if provider == "azure-foundry":
        return _resolve_azure_foundry_branch(req)
    return _resolve_registry_branch(req)


def _normalize_vision_provider(provider: Optional[str]) -> str:
    return _normalize_aux_provider(provider)


def resolve_vision_provider_client(
    provider: Optional[str] = None, model: Optional[str] = None, *, base_url: Optional[str] = None,
    api_key: Optional[str] = None, async_mode: bool = False,
    main_runtime: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[Any], Optional[str]]:
    """Resolve the client actually used for vision tasks.

    Direct endpoint overrides beat provider selection; explicit providers may force
    experimental backends; auto mode only tries backends known to work.
    """
    runtime = _normalize_main_runtime(main_runtime)
    requested, resolved_model, resolved_base_url, resolved_api_key, resolved_api_mode = _resolve_task_provider_model(
        "vision", provider, model, base_url, api_key
    )
    # The raw name keeps a llama.cpp alias distinguishable from bare ``custom`` for the last resolve.
    raw_requested, requested = requested, _normalize_vision_provider(requested)
    if resolved_base_url:
        provider_for_base_override = requested if requested and requested not in {"", "auto"} else "custom"
        client, final_model = resolve_provider_client(
            provider_for_base_override, model=resolved_model, async_mode=async_mode,
            explicit_base_url=resolved_base_url, explicit_api_key=resolved_api_key,
            api_mode=resolved_api_mode, main_runtime=runtime,
        )
        return provider_for_base_override, client, (final_model if client is not None else None)
    if requested == "auto":
        return _vision_auto_route(runtime, resolved_model, resolved_api_mode, async_mode)
    if requested in _VISION_AUTO_PROVIDER_ORDER:
        sync_client, default_model = _resolve_strict_vision_backend(requested, resolved_model)
        return _finalize_vision_client(requested, sync_client, default_model, resolved_model, async_mode)
    if requested == "zai":
        for _zai_url in _ZAI_OPENAI_VISION_URLS:
            client, final_model = _get_cached_client(
                requested, resolved_model, async_mode, base_url=_zai_url,
                api_key=resolved_api_key or None, api_mode="chat_completions", main_runtime=runtime,
                is_vision=True,
            )
            if client is not None:
                return _finalize_vision_client(requested, client, final_model, resolved_model, async_mode)
        # Fallback: try without explicit base_url (old behavior)
    client, final_model = _get_cached_client(
        raw_requested, resolved_model, async_mode, api_mode=resolved_api_mode, main_runtime=runtime, is_vision=True,
    )
    return requested, client, (final_model if client is not None else None)


def _resolve_task_provider_model(
    task: str = None, provider: str = None, model: str = None, base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Determine (provider, model, base_url, api_key, api_mode) for a call.

    Priority: explicit args > config auxiliary.{task}.* > "auto". A bare base_url means custom,
    but a first-class provider + base_url keeps the provider identity so its auth/transport
    shaping still applies. api_mode is "chat_completions", "codex_responses", or None (auto).
    """
    from hermes_cli import friday_credential_admission as admission
    if admission.managed():
        return admission.auxiliary(task, provider, model, base_url, api_key)
    cfg_provider = cfg_model = cfg_base_url = cfg_api_key = resolved_api_mode = None
    if task:
        task_config = _get_auxiliary_task_config(task)
        cfg_provider = str(task_config.get("provider", "")).strip() or None
        cfg_model = str(task_config.get("model", "")).strip() or None
        cfg_base_url = str(task_config.get("base_url", "")).strip() or None
        cfg_api_key = str(task_config.get("api_key", "")).strip() or None
        if not cfg_api_key:  # key_env → env var when api_key is not set directly
            cfg_key_env = str(task_config.get("key_env") or task_config.get("api_key_env") or "").strip()
            if cfg_key_env:
                cfg_api_key = _scoped_key_env(cfg_key_env) or None
        # User-facing spellings (``responses``, ``anthropic``, …) canonicalize here so every
        # branch downstream compares against the transport names only (#39750).
        resolved_api_mode = _canonical_api_mode(str(task_config.get("api_mode") or "")).lower() or None
    # 'auto' is a sentinel ("inherit / auto-detect"), not a model id — leaking it to the wire
    # yields a 200 with an error-text body that consumers accept as output. The explicit `model`
    # kwarg needs the same normalization: MoA slots forward preset `model:` fields through it.
    if model and model.lower() == "auto":
        model = None
    if cfg_model and cfg_model.lower() == "auto":
        cfg_model = None
    resolved_model = model or cfg_model
    # Any moa:// facade endpoint belongs to the facade, not the aggregator's real provider —
    # drop it (mirrors _resolve_auto_route()).
    if provider and str(provider).strip().lower() == "moa":
        provider, resolved_model = _unwrap_moa_provider(provider, resolved_model)
        if provider and provider.lower() != "moa":
            base_url = None
            api_key = None
    elif cfg_provider and str(cfg_provider).strip().lower() == "moa":
        cfg_provider, cfg_model = _unwrap_moa_provider(cfg_provider, resolved_model)
        if cfg_provider and cfg_provider.lower() != "moa":
            resolved_model = cfg_model
            cfg_base_url = None
            cfg_api_key = None
    # One shared alias table with resolve_runtime_provider(): ``provider: openai`` routes the same
    # way here (compression/vision/title) and on the runtime path (background review, curator, MoA).
    from hermes_cli.runtime_provider_custom import expand_direct_api_alias
    if provider:
        provider, base_url = expand_direct_api_alias(provider, base_url)
    if cfg_provider:
        cfg_provider, cfg_base_url = expand_direct_api_alias(cfg_provider, cfg_base_url)
    # An explicit provider without base_url adopts the task's configured endpoint (same or
    # unnamed provider) so the early return below carries it. Explicit "auto" is excluded — it
    # must keep flowing through auto-resolution.
    # See #58515.
    if provider and provider != "auto" and not base_url and cfg_base_url and cfg_provider in (None, provider):
        base_url = cfg_base_url
        if not api_key:
            api_key = cfg_api_key
    if base_url:
        kept = provider if _preserve_provider_with_base_url(provider) else "custom"
        return kept, resolved_model, base_url, api_key, resolved_api_mode
    if provider:
        return provider, resolved_model, base_url, api_key, resolved_api_mode
    if cfg_base_url and cfg_api_key:
        from agent.bounded_context import is_bounded_provider
        kept = cfg_provider if (str(cfg_provider or "").strip().lower() in _LOCAL_SERVER_ALIASES
                                or is_bounded_provider(cfg_provider)) else "custom"
        return kept, resolved_model, cfg_base_url, cfg_api_key, resolved_api_mode
    if cfg_base_url and cfg_provider and cfg_provider != "auto":
        # base_url without api_key: keep the provider so it can resolve credentials from env
        # vars instead of locking into "custom".
        return cfg_provider, resolved_model, cfg_base_url, None, resolved_api_mode
    if cfg_provider and cfg_provider != "auto":
        return cfg_provider, resolved_model, cfg_base_url, cfg_api_key, resolved_api_mode
    return "auto", resolved_model, None, None, resolved_api_mode

