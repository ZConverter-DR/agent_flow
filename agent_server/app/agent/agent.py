import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from app.common.config import settings

print(f"NOTION_API_KEY 로드됨: {bool(settings.notion_api_key)}")
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

SUPERVISOR_PROMPT = """
Analyze the user's request and delegate to the appropriate agent.
- Slack-related requests (channels, messages, users) → slack_agent
- File/Directory-related requests (read, write, list) → filesystem_agent
- OpenStack-related requests (server info, VM creation, recovery) → openstack_agent
You MUST always respond in Korean.
"""

SLACK_PROMPT = """
You are a Slack assistant.
Call each tool ONLY ONCE. Never repeat tool calls.
You MUST always respond in Korean.
Respond only in JSON format.
"""

FILESYSTEM_PROMPT = """You are a filesystem assistant.
You can read files, write files, and list directories.
Call each tool ONLY ONCE. Never repeat tool calls.
You MUST always respond in Korean.
"""

OPENSTACK_PROMPT = """
You are an OpenStack infrastructure assistant.
You can get server info, create VMs, execute recovery, and check recovery status.
Call each tool ONLY ONCE. Never repeat tool calls.
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

_filesystem_mcp_config = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app"],
        "transport": "stdio",
    }
}

_openstack_mcp_config = {
    "openstack": {
        "command": "python",
        "args": ["main.py"],
        "cwd": _OPENSTACK_SERVER_DIR,
        "env": {**os.environ},
        "transport": "stdio",
    }
}

def build_supervisor(slack_tools, filesystem_tools, openstack_tools) -> str:
    slack_agent = create_react_agent(llm, slack_tools, name="slack_agent", prompt=SLACK_PROMPT)
    filesystem_agent = create_react_agent(llm, filesystem_tools, name="filesystem_agent", prompt=FILESYSTEM_PROMPT)
    openstack_agent = create_react_agent(llm, openstack_tools, name="openstack_agent", prompt=OPENSTACK_PROMPT)

    return create_supervisor(
        agents=[slack_agent, filesystem_agent, openstack_agent],
        model=llm,
        prompt=SUPERVISOR_PROMPT,
    ).compile()

async def answer_generator(supervisor, input: str, history: list = []) -> str:
    result = await supervisor.ainvoke({
        "messages": history + [("human", input)]
    })
    return result["messages"][-1].content

