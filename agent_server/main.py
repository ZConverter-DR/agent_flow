import logging
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from fastapi import FastAPI
from app.agent.agent import build_supervisor, answer_generator, _slack_mcp_config, _filesystem_mcp_config, _openstack_mcp_config
from app.auth.dependencies import get_current_user
from app.auth.schema import TokenPayload
from app.common.config import settings
from app.ws.chat import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    slack_client = MultiServerMCPClient(_slack_mcp_config)
    filesystem_client = MultiServerMCPClient(_filesystem_mcp_config)
    openstack_client = MultiServerMCPClient(_openstack_mcp_config)
    
    slack_tools = await slack_client.get_tools()
    filesystem_tools = await filesystem_client.get_tools()
    openstack_tools = await openstack_client.get_tools()
    
    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
    async with AsyncRedisSaver.from_conn_string(
        redis_url,
        ttl={"default_ttl": 60, "refresh_on_read": True}    # 마지막 대화 후 60분
    ) as checkpointer:
        app.state.supervisor = build_supervisor(
            slack_tools,
            filesystem_tools,
            openstack_tools,
            checkpointer,
        )
        yield

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(lifespan=lifespan)
app.include_router(ws_router)
