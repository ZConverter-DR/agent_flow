import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from tools import ALL_TOOLS
from handlers import (
    handle_get_server_info,
    handle_create_vm,
    handle_execute_recovery,
    handle_get_recovery_status,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

app = Server("openstack-mcp-server")

@app.list_tools()
async def list_tools():
    return ALL_TOOLS

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info(
        "Received CallToolRequest: %s",
        json.dumps(
            {"method": "tools/call", "params": {"name": name, "arguments": arguments}},
            indent=2,
            ensure_ascii=False,
        ),
    )

    match name:
        case "get_server_info":
            result = await handle_get_server_info(
                server_id=arguments["server_id"],
            )

        case "create_vm":
            result = await handle_create_vm(
                name=arguments["name"],
                flavor=arguments["flavor"],
                image_id=arguments["image_id"],
                network_id=arguments["network_id"],
            )

        case "execute_recovery":
            result = await handle_execute_recovery(
                server_id=arguments["server_id"],
                recovery_type=arguments["recovery_type"],
                reason=arguments["reason"],
            )

        case "get_recovery_status":
            result = await handle_get_recovery_status(
                job_id=arguments["job_id"],
            )

        case _:
            result = {"error": f"Unknown tool: {name}"}
    
    logger.info(
        "CallToolResponse: %s",
        json.dumps(
            {"method": "tools/call", "result": {"name": name, "content": result}},
            indent=2,
            ensure_ascii=False,
        ),
    )

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

async def main():
    _validate_env()
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )

def _validate_env():
    required = ["OS_AUTH_URL", "OS_USERNAME", "OS_PASSWORD", "OS_PROJECT_NAME"]
    missing = [key for key in required if not os.getenv(key)]
    
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Check your .env file"
        )

if __name__ == "__main__":
    asyncio.run(main())