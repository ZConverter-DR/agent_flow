from mcp.types import Tool

generate_policy_tool = Tool(
    name="generate_policy",
    description="""Generate a policy document for a given resource and rule set.
Use this when the user asks to create, define, or generate a policy.
If any required value is missing, ask the user for clarification first.
Returns: policy ID, name, resource type, and generated rules.""",
    inputSchema={
        "type": "object",
        "properties": {
            "policy_name": {
                "type": "string",
                "description": "Name of the policy to generate",
            },
            "resource_type": {
                "type": "string",
                "description": "Target resource type (e.g. 'vm', 'network', 'storage')",
            },
            "rules": {
                "type": "string",
                "description": "Description of rules or constraints to apply in the policy",
            },
        },
        "required": ["policy_name", "resource_type", "rules"],
    },
)

generate_report_tool = Tool(
    name="generate_report",
    description="""Generate a summary report for a given target and period.
Use this when the user asks to create, produce, or generate a report.
If any required value is missing, ask the user for clarification first.
Returns: report ID, title, target, period, and summary content.""",
    inputSchema={
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["usage", "incident", "performance", "audit"],
                "description": "Type of report to generate",
            },
            "target": {
                "type": "string",
                "description": "Target resource or system to report on (e.g. 'vm-01', 'network')",
            },
            "period": {
                "type": "string",
                "description": "Time period for the report (e.g. '2025-04', 'last 7 days')",
            },
        },
        "required": ["report_type", "target", "period"],
    },
)

save_history_tool = Tool(
    name="save_history",
    description="""Save an action or event record to the history log.
Use this when the user asks to log, record, or save an action or event.
Returns: record ID and saved timestamp.""",
    inputSchema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action or event name to record (e.g. 'vm_created', 'policy_applied')",
            },
            "target": {
                "type": "string",
                "description": "Resource or entity the action was performed on",
            },
            "detail": {
                "type": "string",
                "description": "Additional detail or context about the action",
            },
        },
        "required": ["action", "target", "detail"],
    },
)