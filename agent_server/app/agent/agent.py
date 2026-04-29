import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from app.agent.tools import wrap_destructive_tools
from app.common.config import settings

print(f"slack_bot_token 로드됨: {bool(settings.slack_bot_token)}")
print(f"slack_team_id 로드됨: {bool(settings.slack_team_id)}")

llm = ChatOpenAI(
    model="qwen2.5:7b",
    base_url="http://10.0.2.2:11434/v1",
    api_key="ollama",
    temperature=0,
)

_OPENSTACK_SERVER_DIR = str(
    Path(__file__).parent.parent / "mcp_servers" / "openstack-mcp-server"
)

_MOCK_SERVER_DIR = str(
    Path(__file__).parent.parent / "mcp_servers" / "test_mock_server"
)

# - Mock: generate policies, generate reports, save history records
AGENT_PROMPT = """
You are an infrastructure assistant.
You can use the following tools to help the user:
- Slack: post messages, reply to threads, add reactions
- OpenStack: get server info, create VMs, execute recovery, check recovery status

Call each tool ONLY ONCE. Never repeat tool calls.
If a tool returns [CANCELLED], the action was NOT performed. Inform the user it was cancelled and stop.
You MUST always respond in Korean.
"""


_slack_mcp_config = {
    "slack": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {
            **os.environ,
            "SLACK_BOT_TOKEN": settings.slack_bot_token or "",
            "SLACK_TEAM_ID": settings.slack_team_id or "",
        },
        "transport": "stdio",
    }
}

# _filesystem_mcp_config = {
#     "filesystem": {
#         "command": "npx",
#         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app"],
#         "transport": "stdio",
#     }
# }

_openstack_mcp_config = {
    "openstack": {
        "command": "python",
        "args": ["main.py"],
        "cwd": _OPENSTACK_SERVER_DIR,
        "env": {**os.environ},
        "transport": "stdio",
    }
}

# _mock_mcp_config = {
#     "mock": {
#         "command": "python",
#         "args": ["main.py"],
#         "cwd": _MOCK_SERVER_DIR,
#         "env": {**os.environ},
#         "transport": "stdio",
#     }
# }

# def build_agent(slack_tools, openstack_tools, mock_tools, checkpointer):
def build_agent(slack_tools, openstack_tools, checkpointer):
    openstack_tools = wrap_destructive_tools(openstack_tools)
    # all_tools = slack_tools +  openstack_tools + mock_tools
    all_tools = slack_tools +  openstack_tools

    return create_react_agent(
        llm,
        all_tools,
        prompt=AGENT_PROMPT,
        checkpointer=checkpointer,
    )

async def answer_generator(agent, input, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return await agent.ainvoke(input, config=config)
