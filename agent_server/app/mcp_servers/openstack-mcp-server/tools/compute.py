from mcp.types import Tool

get_server_info_tool = Tool(
    name="get_server_info",
    description="""Get detailed information about a specific OpenStack VM instance.
Use this when the user asks about server status, IP address, specs, or current state of a VM.
IMPORTANT: Always call this before execute_recovery to confirm the server is in ERROR or SHUTOFF state.
Returns: instance ID, name, status (ACTIVE/SHUTOFF/ERROR), flavor, IP addresses, created time.""",
    inputSchema={
        "type": "object",
        "properties": {
            "server_id": {
                "type": "string",
                "description": "The OpenStack instance UUID (e.g. 'a1b2c3d4-...') or name",
            }
        },
        "required": ["server_id"],
    },
)

create_vm_tool = Tool(
    name="create_vm",
    description="""Create a new virtual machine instance in OpenStack.
Use this tool when the user explicitly requests to create, launch, provision, or deploy a VM/server.
Only call this tool when all required parameters are provided or can be clearly inferred.
If any required value is missing, ask the user for clarification first.
""",
    inputSchema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name for the new VM instance",
            },
            "flavor": {
                "type": "string",
                "description": "OpenStack flavor name (e.g. 'm1.small', 'm1.large')",
            },
            "image_id": {
                "type": "string",
                "description": "OS image UUID to boot from",
            },
            "network_id": {
                "type": "string",
                "description": "Network UUID to attach the VM to",
            },
        },
        "required": ["name", "flavor", "image_id", "network_id"],
    },
)