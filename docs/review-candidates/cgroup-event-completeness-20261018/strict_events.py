"""Pure DATA validation; this module neither reads cgroups nor grants execution."""

MAX_COUNTER = (1 << 64) - 1
MAX_DOCUMENT_BYTES = 65536
PROFILES = ('memory-events-6', 'memory-events-7-sock-throttled')
MEMORY_BASE = ('low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill')
DOCUMENTS = ('memory.events', 'pids.events', 'cgroup.events')


class IncompleteEvents(ValueError):
    """Unsupported, incomplete or changed evidence; never an observed zero."""


def require(condition, reason):
    if not condition:
        raise IncompleteEvents(reason)


def fields(document, *, profile):
    require(type(profile) is str and profile in PROFILES, 'explicit_supported_event_profile_required')
    require(type(document) is str and document in DOCUMENTS, 'supported_event_document_required')
    if document == 'memory.events':
        return MEMORY_BASE + (('sock_throttled',) if profile == PROFILES[1] else ())
    if document == 'pids.events':
        return ('max',)
    return ('populated', 'frozen')


def validate_document(document, counters, *, profile):
    expected = fields(document, profile=profile)
    require(type(counters) is dict and set(counters) == set(expected), 'complete_exact_event_fields_required')
    for key in expected:
        value = counters[key]
        require(type(value) is int and 0 <= value <= MAX_COUNTER, 'nonnegative_bounded_integer_event_required')
        if document == 'cgroup.events':
            require(value in (0, 1), 'binary_cgroup_state_required')
    return dict(counters)


def parse_document(document, raw, *, profile):
    fields(document, profile=profile)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_DOCUMENT_BYTES, 'bounded_nonempty_event_bytes_required')
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError as exc:
        raise IncompleteEvents('ASCII_kernel_event_text_required') from exc
    require(text.endswith('\n'), 'complete_event_final_newline_required')
    counters = {}
    for line in text[:-1].split('\n'):
        parts = line.split(' ')
        require(len(parts) == 2 and all(parts), 'exact_kernel_event_line_required')
        key, word = parts
        require(key not in counters, 'duplicate_kernel_event_field')
        require(len(word) <= 20 and all('0' <= char <= '9' for char in word), 'unsigned_decimal_event_required')
        value = int(word)
        require(str(value) == word, 'canonical_decimal_event_required')
        counters[key] = value
    return validate_document(document, counters, profile=profile)


def validate_snapshot(snapshot, *, profile):
    require(type(snapshot) is dict and set(snapshot) == set(DOCUMENTS), 'complete_exact_event_documents_required')
    return {name: validate_document(name, snapshot[name], profile=profile) for name in DOCUMENTS}


def no_control_event_change(baseline, current, *, profile):
    """Preserve the original max/OOM/pids comparison with complete inputs."""
    before = validate_snapshot(baseline, profile=profile)
    after = validate_snapshot(current, profile=profile)
    for key in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
        require(after['memory.events'][key] == before['memory.events'][key], 'aggregate_memory_control_event:' + key)
    require(after['pids.events']['max'] == before['pids.events']['max'], 'aggregate_pids_control_event')
    return {'relation': 'COMPLETE_CONTROL_COUNTERS_UNCHANGED',
            'profile': profile, 'baseline': before, 'current': after,
            'optional_support': {'sock_throttled': 'OBSERVED' if profile == PROFILES[1] else 'UNSUPPORTED_NOT_ZERO'},
            'kernel_or_runtime_qualification': False}
