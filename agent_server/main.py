import logging
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from fastapi import FastAPI
from app.agent.agent import build_agent, _slack_mcp_config, _openstack_mcp_config
# from app.agent.agent import build_agent, answer_generator, _slack_mcp_config, _openstack_mcp_config, _mock_mcp_config

_ALLOWED_SLACK_TOOLS = {
    "slack_post_message",
    "slack_reply_to_thread",
    "slack_add_reaction",
    "slack_get_channel_history",
}
from app.common.config import settings
from app.ws.chat import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    slack_client = MultiServerMCPClient(_slack_mcp_config)
    # filesystem_client = MultiServerMCPClient(_filesystem_mcp_config)
    openstack_client = MultiServerMCPClient(_openstack_mcp_config)
    # mock_client = MultiServerMCPClient(_mock_mcp_config)

    slack_tools = [t for t in await slack_client.get_tools() if t.name in _ALLOWED_SLACK_TOOLS]
    # filesystem_tools = await filesystem_client.get_tools()
    openstack_tools = await openstack_client.get_tools()
    # mock_tools = await mock_client.get_tools()

    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
    async with AsyncRedisSaver.from_conn_string(
        redis_url,
        ttl={"default_ttl": 60, "refresh_on_read": True}
    ) as checkpointer:
        app.state.agent = build_agent(
            slack_tools,
            openstack_tools,
            checkpointer,
        )
        yield
        # app.state.agent = build_agent(
        #     slack_tools,
        #     openstack_tools,
        #     mock_tools,
        #     checkpointer,
        # )
        # yield

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(lifespan=lifespan)
app.include_router(ws_router)
