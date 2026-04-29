import asyncio
import json
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from tools import ALL_TOOLS
from handlers import (
    handle_generate_policy,
    handle_generate_report,
    handle_save_history,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

app = Server("test-mock-server")


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
        case "generate_policy":
            result = await handle_generate_policy(
                policy_name=arguments["policy_name"],
                resource_type=arguments["resource_type"],
                rules=arguments["rules"],
            )

        case "generate_report":
            result = await handle_generate_report(
                report_type=arguments["report_type"],
                target=arguments["target"],
                period=arguments["period"],
            )

        case "save_history":
            result = await handle_save_history(
                action=arguments["action"],
                target=arguments["target"],
                detail=arguments["detail"],
            )

        case _:
            result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
