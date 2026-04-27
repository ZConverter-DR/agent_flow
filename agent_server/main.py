import logging
from fastapi import FastAPI, Depends
from app.auth.dependencies import get_current_user
from app.auth.schema import TokenPayload
from app.ws.chat import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI()

app.include_router(ws_router)

@app.post("/ai/chat")
async def chat(
    user: TokenPayload = Depends(get_current_user)
):
    return {
        "message": f"{user.username}님 안녕하세요.",
        "project": user.project_id,
    }
    