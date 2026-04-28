from mcp.types import Tool

execute_recovery_tool = Tool(
    name="execute_recovery",
    description="""Trigger a recovery action on a failed OpenStack VM via ZConverter AI Agent.
Use this when the user asks to recover, restart, or fix a problematic server.
This calls the ZConverter AI Agent API already running inside the VM — not cloud-init.
IMPORTANT: Always call get_server_info first to confirm the server is in ERROR or SHUTOFF state.
If this tool returns [CANCELLED], the action was NOT performed. Inform the user it was cancelled and stop.
Returns: recovery job ID and initial status (PENDING).""",
    inputSchema={
        "type": "object",
        "properties": {
            "server_id": {
                "type": "string",
                "description": "The OpenStack instance UUID to recover",
            },
            "recovery_type": {
                "type": "string",
                "enum": ["reboot", "rebuild", "migrate", "evacuate"],
                "description": "Type of recovery action to perform",
            },
            "reason": {
                "type": "string",
                "description": "Reason for recovery (recorded in audit log)",
            },
        },
        "required": ["server_id", "recovery_type", "reason"],
    },
)

get_recovery_status_tool = Tool(
    name="get_recovery_status",
    description="""Trigger a recovery action on a failed OpenStack VM.
Use this when the user asks to recover, restart, or fix a problematic server.
IMPORTANT: Always call get_server_info first to confirm the server is in ERROR or SHUTOFF state.
Returns: recovery job ID — pass this to get_recovery_status to monitor progress.""",
    inputSchema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Recovery job ID returned by execute_recovery",
            },
        },
        "required": ["job_id"],
    },
)