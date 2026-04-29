import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, Query
from fastapi.websockets import WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
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
    client = websocket.client
    logger.info(f"[WS] 연결 시도 - client={client}")

    redis = await get_redis()
    logger.info(f"[WS] Redis 연결 획득 - state={websocket.client_state}")

    await websocket.accept()
    logger.info(f"[WS] 핸드셰이크 완료 - state={websocket.client_state}")

    try:
        data = await verify_jwt(token, redis)
        thread_id = data.sub    # user_id를 thread_id로 사용
        logger.info(f"[WS] 인증 성공 - client={client}, thread_id={thread_id}")
    except Exception as e:
        logger.warning(f"[WS] 인증 실패 - client={client}, error={e}")
        await websocket.close(code=1008)
        return
    
    agent = websocket.app.state.agent
    state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    if state and state.values:
        prev_message = [
            {"role": "user" if isinstance(m, HumanMessage) else "assistant",
             "content": m.content}
            for m in state.values.get("messages", [])
            if isinstance(m, (HumanMessage, AIMessage)) and m.content
        ]
        if prev_message:
            await websocket.send_text(json.dumps({
                "type": "history",
                "messages": prev_message,
            }))

    logger.info(f"[WS] 메시지 루프 시작 - client={client}")
    try:
        while True:
            message = await websocket.receive_text()
            logger.debug(f"[WS] 수신 - client={client}, message={message!r}")
            
            try:
                parsed = json.loads(message)
                if parsed.get("type") == "confirm_response":
                    graph_input = Command(resume=parsed.get("approved", False))
                else:
                    graph_input = {"messages": [("human", parsed.get("content", message))]}
            except (json.JSONDecodeError, AttributeError):
                graph_input = {"messages": [("human", message)]}
            
            result = await answer_generator(agent, graph_input, thread_id)

            interrupts = result.get("__interrupt__", ())
            if interrupts:
                val = interrupts[0].value
                await websocket.send_text(json.dumps({
                    "type": "confirm",
                    "confirm_id": str(uuid.uuid4()),
                    "tool": val.get("tool_name", ""),
                    "args": val.get("args", {}),
                    "message": f"'{val.get('tool_name')}' 작업을 실행하시겠습니까?",
                }))
            else:
                await websocket.send_text(result["messages"][-1].content)
            
    except WebSocketDisconnect as e:
        logger.info(f"[WS] 클라이언트 정상 종료 - client={client}, code={e.code}")
    except Exception as e:
        logger.error(f"[WS] 루프 오류 - client={client}, state={websocket.client_state}, error={type(e).__name__}: {e}", exc_info=True)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011)
