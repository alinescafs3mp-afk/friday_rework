"""Supported Hermes entry point. No process, model, network or timer at load."""
from .admission import IngressAdmissions, native_call_scope


def register(ctx):
    admission = IngressAdmissions(ctx.state)
    from .host import register_host
    host = register_host(ctx, admission)
    from .result_tool import register_result_tool
    register_result_tool(ctx, host)
    ctx.register_hook("post_gateway_admission", admission.record)
    ctx.register_middleware("tool_execution", native_call_scope)
    ctx.register_tool(
        name="friday_work",
        toolset="friday_rework",
        description="Request coding or engineering work through an owned worker.",
        schema={
            "name": "friday_work",
            "description": (
                "Request a coding (dsh) or engineering (a0) worker. "
                "A request is not accepted until supervised execution is available. "
                "Describe the goal and its check; never supply credentials or routing IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "worker": {"type": "string", "enum": ["dsh", "a0"]},
                    "brief": {"type": "string", "description": "Bounded task brief."},
                    "goal_check": {"type": "string", "description": "Observable completion check."},
                    "retained_inputs": {
                        "type": "object",
                        "description": "For a Telegram coding correction, select complete files from a prior DSH result in this conversation. The current original attachment is still required.",
                        "properties": {
                            "reference": {"type": "string", "pattern": "^native-[0-9a-f]{64}$"},
                            "paths": {"type": "array", "minItems": 1, "maxItems": 16,
                                      "uniqueItems": True,
                                      "items": {"type": "string", "maxLength": 2048}},
                        },
                        "required": ["reference", "paths"],
                        "additionalProperties": False,
                    },
                },
                "required": ["worker", "brief", "goal_check"],
                "additionalProperties": False,
            },
        },
        handler=host.handle,
        override=False,
    )
