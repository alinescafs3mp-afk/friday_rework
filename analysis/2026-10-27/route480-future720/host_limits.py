# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never use as an installed module.
# Source/export correspondence is structural only after declared substitutions.
# Selected statements only; surrounding validator/dispatch is omitted.
def selected_route_limits(row, route, native, runtime, _current_main=None):
    limits = route['daemon_limits']
    if (not isinstance(limits,dict) or set(limits) != {'runtime_seconds', 'start_seconds', 'stop_seconds', 'admitted_remaining_seconds'}
            or any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in limits.values())
            or limits['admitted_remaining_seconds'] > row['budget_seconds']-25
            # Retained legacy routes keep their original ceiling. The installed
            # qualified 480-second producer/unit pair is the only longer route;
            # source pins identify it without reopening launch files at recovery.
            or (limits['runtime_seconds'] > 120 and
                (limits['runtime_seconds'] != 480 or
                 tuple(native[k]['sha256'] for k in ('runtime','launcher','daemon_unit')) != (
                     'UNBOUND_NATIVE_RUNTIME_SHA',
                     'UNBOUND_NATIVE_LAUNCHER_SHA',
                     'UNBOUND_NATIVE_UNIT_SHA')))
            or limits['start_seconds'] > 45 or limits['stop_seconds'] > 20
            or sum(limits[k] for k in ('runtime_seconds','start_seconds','stop_seconds')) + 5 > limits['admitted_remaining_seconds']):
        raise ValueError('invalid_a0_route_deadline')
