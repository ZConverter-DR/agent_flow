import logging
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse          # [TEST] 삭제 시 제거
from fastapi.staticfiles import StaticFiles         # [TEST] 삭제 시 제거
from pydantic import BaseModel                      # [TEST] 삭제 시 제거
from app.agent.agent import build_supervisor, answer_generator, _slack_mcp_config, _filesystem_mcp_config, _openstack_mcp_config
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
app.mount("/static", StaticFiles(directory="static"), name="static")  # [TEST] 삭제 시 제거
app.include_router(ws_router)

# [TEST] 아래 두 엔드포인트 삭제 시 위 mount("/static") 및 관련 import도 함께 제거
@app.get("/ai/test/ui")
async def test_ui():
    return FileResponse("static/test.html")



@app.post("/ai/chat")
async def chat(
    user: TokenPayload = Depends(get_current_user)
):
    return {
        "message": f"{user.username}님 안녕하세요.",
        "project": user.project_id,
    }
    
# [TEST] 아래 블록 전체 삭제 가능 (TestRequest, test_chat)
class TestRequest(BaseModel):
    message: str

@app.post("/ai/test")
async def test_chat(request: Request, body: TestRequest):
    supervisor = request.app.state.supervisor
    result = await answer_generator(supervisor, body.message)
    return {"result": result}
# [TEST] end