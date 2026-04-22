from fastapi import FastAPI, Depends
from app.auth.dependencies import get_current_user, require_roles
from app.auth.schema import TokenPayload

app = FastAPI()

@app.post("/ai/chat")
async def chat(
    user: TokenPayload = Depends(get_current_user)
):
    return {
        "message": f"{user.username}님 안녕하세요.",
        "project": user.project_id,
    }