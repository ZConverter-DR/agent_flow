import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, Query
from fastapi.websockets import WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from redis.asyncio import Redis
from starlette.websockets import WebSocketState
from app.auth.jwt_verify import verify_jwt
from app.common.redis import get_redis
from app.agent.agent import answer_generator

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket('/ws/chat')
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...)
):
    history_key: str
    client = websocket.client
    logger.info(f"[WS] 연결 시도 - client={client}")

    redis = await get_redis()
    logger.info(f"[WS] Redis 연결 획득 - state={websocket.client_state}")

    await websocket.accept()
    logger.info(f"[WS] 핸드셰이크 완료 - state={websocket.client_state}")

    try:
        data = await verify_jwt(token, redis)
        history_key = f"chat:session:{data.session_id}:history"
        logger.info(f"[WS] 인증 성공 - client={client}")
    except Exception as e:
        logger.warning(f"[WS] 인증 실패 - client={client}, error={e}")
        await websocket.close(code=1008)
        return

    logger.info(f"[WS] 메시지 루프 시작 - client={client}")
    supervisor = websocket.app.state.supervisor
    try:
        while True:
            message = await websocket.receive_text()
            logger.debug(f"[WS] 수신 - client={client}, message={message!r}")
            result = await answer_generator(supervisor, message)
            # await save_history(redis, history_key, result.new_messages())
            
            response = f"{result}"
            await websocket.send_text(response)
    except WebSocketDisconnect as e:
        logger.info(f"[WS] 클라이언트 정상 종료 - client={client}, code={e.code}")
    except Exception as e:
        logger.error(f"[WS] 루프 오류 - client={client}, state={websocket.client_state}, error={e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011)

async def load_history(redis: Redis, history_key: str) -> list[BaseMessage]:
    raw_list = await redis.lrange(history_key, 0, -1)
    messages = []
    for raw in raw_list:
        data = json.loads(raw)
        if data["role"] == "user":
            messages.append(HumanMessage(content=data["content"]))
        elif data["role"] == "assistant":
            messages.append(AIMessage(content=data["content"]))
    return messages

async def save_history(redis: Redis, history_key: str, messages: list):
    for msg in messages:
        if isinstance(msg, HumanMessage):
            await redis.rpush(history_key, json.dumps({
                "role": "user",
                "content": msg.content,
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
        elif isinstance(msg, AIMessage):
            await redis.rpush(history_key, json.dumps({
                "role": "assistant",
                "content": msg.content,
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
