import logging
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastapi import FastAPI, Depends
from app.agent.agent import build_supervisor, _slack_mcp_config, _filesystem_mcp_config, _openstack_mcp_config
from app.auth.dependencies import get_current_user
from app.auth.schema import TokenPayload
from app.ws.chat import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    slack_client = MultiServerMCPClient(_slack_mcp_config)
    filesystem_client = MultiServerMCPClient(_filesystem_mcp_config)
    openstack_client = MultiServerMCPClient(_openstack_mcp_config)
    
    slack_tools = await slack_client.get_tools()
    filesystem_tools = await filesystem_client.get_tools()
    openstack_tools = await openstack_client.get_tools()

    app.state.supervisor = build_supervisor(slack_tools, filesystem_tools, openstack_tools)
    yield

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(lifespan=lifespan)

app.include_router(ws_router)

@app.post("/ai/chat")
async def chat(
    user: TokenPayload = Depends(get_current_user)
):
    return {
        "message": f"{user.username}님 안녕하세요.",
        "project": user.project_id,
    }
    