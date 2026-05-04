import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastapi import FastAPI
from app.graph_agent.graph import build_graph
from app.graph_agent.agents import init_agents, _slack_mcp_config, _openstack_mcp_config

from app.common.config import settings
from app.ws.chat import router as ws_router

_ALLOWED_SLACK_TOOLS = {
    "slack_post_message",
    "slack_reply_to_thread",
    "slack_add_reaction",
    "slack_get_channel_history",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    slack_client = MultiServerMCPClient(_slack_mcp_config)
    openstack_client = MultiServerMCPClient(_openstack_mcp_config)

    slack_tools = [t for t in await slack_client.get_tools() if t.name in _ALLOWED_SLACK_TOOLS]
    openstack_tools = await openstack_client.get_tools()
    all_tools = slack_tools + openstack_tools

    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
    async with AsyncRedisSaver.from_conn_string(
        redis_url,
        ttl={"default_ttl": 60, "refresh_on_read": True}
    ) as checkpointer:
        await init_agents(all_tools) # MCP연결 + LLM 초기화
        app.state.agent = build_graph(checkpointer)
        yield

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(lifespan=lifespan)
app.include_router(ws_router)
