import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, Query
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState
from pydantic_ai import ModelMessagesTypeAdapter, ModelRequest, ModelRespones, UserPromptPart, TextPart
from redis.asyncio import Redis
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
    try:
        while True:
            message = await websocket.receive_text()
            logger.debug(f"[WS] 수신 - client={client}, message={message!r}")
            result = await answer_generator(message, message_history)
            await save_history(redis, history_key, result.new_messages())
            
            response = f"{result.output}"
            await websocket.send_text(response)
    except WebSocketDisconnect as e:
        logger.info(f"[WS] 클라이언트 정상 종료 - client={client}, code={e.code}")
    except Exception as e:
        logger.error(f"[WS] 루프 오류 - client={client}, state={websocket.client_state}, error={e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011)

async def load_history(redis: Redis, history_key: str) -> list:
    raw = await redis.get(history_key)
    return ModelMessagesTypeAdapter.validate_json(raw) if raw else []

async def save_history(redis: Redis, history_key: str, message_history: list):
    for msg in message_history:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    await redis.rpush(history_key, json.dumps({
                        "role": "user",
                        "content": part.content,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }))
        elif isinstance(msg, ModelRespones):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    await redis.rpush(history_key, json.dumps({
                        "role": "assistant",
                        "content": part.content,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }))
    