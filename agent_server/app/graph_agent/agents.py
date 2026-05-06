import json
import os
from pathlib import Path
from typing import Annotated
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.prebuilt import InjectedState

from .schemas import RouteDecision, RecoveryPolicy
from .state import ChatState
from app.common.config import settings
from app.common.redis import get_redis

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
- flavor: m1.tiny
- image_id: d8cf79e9-9902-485f-9025-62d093cbf3b5
- network_id: c82c7c3a-150b-4ec4-b149-04b565253fda
- recovery_type: snapshot_restore, fresh_install, config_replicate

If a rejection reason is provided, you MUST choose a different flavor/image combination.

Respond ONLY with the following JSON structure. Do NOT wrap it in any outer key.
{
  "name": "recovery VM name",
  "flavor": "m1.tiny",
  "image_id": "d8cf79e9-9902-485f-9025-62d093cbf3b5",
  "network_id": "c82c7c3a-150b-4ec4-b149-04b565253fda",
  "recovery_type": "snapshot_restore",
  "reason": "reason for this policy"
}
"""

RESPONSE_SYSTEM = """You are a concise assistant that handles OpenStack and Slack tasks.

Rules:
- Respond ONLY to what the user explicitly asked. Do not add unrequested information, suggestions, or follow-up actions.
- Use a tool ONLY if the user's request directly requires it. Do not call tools proactively or "just in case."
- If the user asks a question, answer it. If the user asks to perform an action, perform only that action.
- Do not explain what you are about to do. Do not summarize what you just did unless the user asked for a summary.
- If a tool returns more data than the user asked about, extract and return only the relevant fields.
- If the request is ambiguous, ask one clarifying question. Do not guess intent and act on it.
- You MUST always respond in Korean."""

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

async def _get_auth(session_id: str) -> dict:
    redis = await get_redis()
    data = await redis.get(f"chat:session:{session_id}")
    return json.loads(data)

def _make_openstack_wrapped(raw_tools: dict) -> list:
    @tool("get_server_info")
    async def get_server_info_wrapped(
        server_id: str,
        state: Annotated[dict, InjectedState],
    ) -> dict:
        """Get detailed information about a specific OpenStack VM instance.
Use this when the user asks about server status, IP address, specs, or current state of a VM.
        """
        auth = await _get_auth(state["session_id"])
        return await raw_tools["get_server_info"].ainvoke({
            "server_id": server_id,
            "token": auth["token_id"],
            "auth_url": auth["auth_url"],
            "project_id": auth["project_id"],
        })
    
    @tool("create_vm")
    async def create_vm_wrapped(
        name: str,
        flavor: str,
        image_id: str,
        network_id: str,
        state: Annotated[dict, InjectedState],
    ) -> dict:
        """Create a new virtual machine instance in OpenStack.
Use this when the user explicitly requests to create, launch, provision, or deploy a VM."""
        auth = await _get_auth(state["session_id"])
        return await raw_tools["create_vm"].ainvoke({
            "name": name,
            "flavor": flavor,
            "image_id": image_id,
            "network_id": network_id,
            "auth_url": auth["auth_url"],
            "token": auth["token_id"],
            "project_id": auth["project_id"],
    })
    
    return [get_server_info_wrapped, create_vm_wrapped]

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

    openstack_tool_names = {"get_server_info", "create_vm"}
    openstack_wrappers = _make_openstack_wrapped(mcp_tools)
    other_tools = [t for t in tools if t.name not in openstack_tool_names]
    response_tools = openstack_wrappers + other_tools

    # 단순 호출, 단순 작업을 위해 따로 agent를 만들어둠.
    response_agent = create_agent(
        model=ChatOpenAI(
            model="qwen2.5:7b",
            base_url=_OLLAMA_BASE_URL,
            api_key="ollama",
            temperature=0.3,
        ),
        tools=response_tools,
        system_prompt=RESPONSE_SYSTEM,
        state_schema=ChatState,
    )

async def answer_generator(agent, graph_input, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return await agent.ainvoke(graph_input, config=config)