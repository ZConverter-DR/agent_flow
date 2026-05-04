import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from .schemas import RouteDecision, RecoveryPolicy
from app.common.config import settings

mcp_tools: dict = {}
intent_llm    = None
policy_llm    = None
response_agent = None

# INTENT_SYSTEM = """사용자 요청을 분석해 intent를 분류하세요.
# - 서버 복구/장애 처리 요청 → recover_server
# - 그 외 (조회, VM 생성, 일반 질문) → direct_response
# 서버 ID가 명시된 경우 server_id에 추출하세요.
# 반드시 JSON 형식으로만 응답하세요."""

INTENT_SYSTEM = """Analyze the user's request and classify the intent.
- Server recovery or failure handling requests → recover_server
- Anything else (status check, VM creation, general questions) → direct_response
- Slack-related commands or requests → direct_response
If a server ID is mentioned, extract it into server_id.
Respond in JSON format only."""

POLICY_SYSTEM = """You are an OpenStack disaster recovery policy expert.
Given the failed server information, generate a recovery VM policy.

Available resources:
- flavor: m1.tiny, m1.small, m1.medium, m1.large, m1.xlarge
- image_id: img-001 (cirros), img-002 (ubuntu-22.04)
- network_id: net-001 (default), net-002 (private)
- recovery_type: snapshot_restore, fresh_install, config_replicate

If a rejection reason is provided, you MUST choose a different flavor/image combination.

Respond ONLY with the following JSON structure. Do NOT wrap it in any outer key.
{
  "name": "recovery VM name",
  "flavor": "m1.small",
  "image_id": "img-001",
  "network_id": "net-001",
  "recovery_type": "snapshot_restore",
  "reason": "reason for this policy"
}
"""

RESPONSE_SYSTEM = """
Answer the user's question or use the available tools as needed.
You MUST always respond in Korean."""

_OLLAMA_BASE_URL = "http://10.0.2.2:11434/v1"

_OPENSTACK_SERVER_DIR = str(
    Path(__file__).parent.parent / "mcp_servers" / "openstack-mcp-server"
)

# _MOCK_SERVER_DIR = str(
#     Path(__file__).parent.parent / "mcp_servers" / "test_mock_server"
# )

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

_openstack_mcp_config = {
    "openstack": {
        "command": "python",
        "args": ["main.py"],
        "cwd": _OPENSTACK_SERVER_DIR,
        "env": {**os.environ},
        "transport": "stdio",
    }
}


async def init_agents(tools: list):
    global mcp_tools, intent_llm, policy_llm, response_agent

    mcp_tools = {tool.name: tool for tool in tools}
    base_llm = ChatOpenAI(
        model="qwen2.5:7b",
        base_url=_OLLAMA_BASE_URL,
        api_key="ollama",
        temperature=0,
    )
    intent_llm = base_llm.with_structured_output(RouteDecision, method="json_mode")
    policy_llm = base_llm.with_structured_output(RecoveryPolicy, method="json_mode")

    response_agent = create_agent(
        model=ChatOpenAI(
            model="qwen2.5:7b",
            base_url=_OLLAMA_BASE_URL,
            api_key="ollama",
            temperature=0.3,
        ),
        tools=tools,
        system_prompt=RESPONSE_SYSTEM,
    )

async def answer_generator(agent, graph_input, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return await agent.ainvoke(graph_input, config=config)