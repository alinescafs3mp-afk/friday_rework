"""Supported Hermes entry point. No process, model, network or timer at load."""
from .boundary import work_handler


def register(ctx):
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
                },
                "required": ["worker", "brief", "goal_check"],
                "additionalProperties": False,
            },
        },
        handler=work_handler,
        override=False,
    )
