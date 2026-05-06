import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import APIRouter, WebSocket, Query, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from pydantic import BaseModel
from starlette.websockets import WebSocketState
from app.auth.jwt_verify import verify_jwt
from app.graph_agent.agents import answer_generator
from app.common.redis import get_redis
from app.common.config import settings
from app.ws import build_dev_chat_html

logger = logging.getLogger(__name__)

# FastAPI로 들어오는 요청을 특정 함수로 매핑해주는 라우팅 단위
router = APIRouter()
_DEV_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


class DevChatTokenRequest(BaseModel):
    username: str


def _ensure_dev_chat_enabled() -> None:
    if not settings.dev_chat_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dev chat disabled")


def _load_dev_private_key() -> str:
    with open(settings.dev_private_key_path, "r") as f:
        return f.read()


@router.get("/dev/chat", response_class=HTMLResponse)
async def dev_chat_page():
    _ensure_dev_chat_enabled()
    return HTMLResponse(build_dev_chat_html())


@router.post("/dev/chat/token")
async def issue_dev_chat_token(body: DevChatTokenRequest):
    _ensure_dev_chat_enabled()

    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username is required")
    if not _DEV_USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid username")

    redis = await get_redis()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=settings.dev_jwt_ttl)
    session_id = f"dev-session:{username}"
    jti = str(uuid.uuid4())

    await redis.set(session_id, username, ex=settings.dev_session_ttl)

    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": f"dev:{username}",
        "project_id": "dev-project",
        "username": username,
        "roles": ["dev"],
        "scope": "dev-chat",
        "session_id": session_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = jwt.encode(
        payload,
        _load_dev_private_key(),
        algorithm=settings.jwt_algorithm,
    )
    logger.info(
        "[DEV JWT] 발급 성공 - username=%s, sub=%s, session_id=%s, issued_at=%s, expires_at=%s",
        username,
        payload["sub"],
        session_id,
        now.isoformat(),
        exp.isoformat(),
    )
    return {"token": token, "username": username}

@router.websocket('/ws/chat')
async def websocket_chat(
    # FastAPI가 websocket을 DI해줌
    websocket: WebSocket,
    #  API query parameter을 받는 로직이다 
    # 파라미터 이름이 "token"이어야 하며 type은 str로 받는다.
    token: str = Query(...)
):
    # 핸드쉐이크 TCP 4계층
    client = websocket.client
    logger.info(f"[WS] 연결 시도 - client={client}")

    redis = await get_redis()
    logger.info(f"[WS] Redis 연결 획득 - state={websocket.client_state}")

    await websocket.accept()
    logger.info(f"[WS] 핸드셰이크 완료 - state={websocket.client_state}")

    try:
        data = await verify_jwt(token, redis) # JWT 검증 로직
        thread_id = data.sub    # user_id를 thread_id로 사용 (각 사용자 별 Message history 관리용)
        logger.info(f"[WS] 인증 성공 - client={client}, thread_id={thread_id}")
    except Exception as e:
        logger.warning(f"[WS] 인증 실패 - client={client}, error={e}")
        await websocket.close(code=1008)
        return
    
    # websocket.app은 싱글톤 객체로써 모든 스레드가 공유하는 처리를 할 때 사용한다.
    agent = websocket.app.state.agent
    # checkpoint 생성 / state.values는 LangGraph가 관리하는 상태 객체임
    state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    # 웹을 새로고침 했을 때에도 대화이력을 이어서 확인할 수 있게끔 진행
    if state and state.values:
        # HumanMessage, AIMessage는 LangChain에서 제공하는 메세지 객체
        prev_message = [
            {"role": "user" if isinstance(m, HumanMessage) else "assistant",
             "content": m.content}
            for m in state.values.get("messages", [])
            if isinstance(m, (HumanMessage, AIMessage)) and m.content
        ]
        if prev_message:
            # 이전 대화 내용을 채팅창에 띄어주는 역할
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
                if parsed.get("type") == "select_server":
                    logger.info(
                        "[WS] confirm 응답 수신 - username=%s, thread_id=%s, approved=%s, received_at=%s",
                        data.username,
                        thread_id,
                        parsed.get("approved", False),
                        datetime.now(timezone.utc).isoformat(),
                    )
                    graph_input = Command(resume={
                        "server_id": parsed.get("server_id"),
                    })
                elif parsed.get("type") == "confirm_response":
                    graph_input = Command(resume={
                        "approved": parsed.get("approved"),
                        "reason": parsed.get("reason", ""),
                    })
                else:
                    graph_input = {"messages": [("human", parsed.get("content", message))],
                                   "session_id": data.session_id,
                    }
            except (json.JSONDecodeError, AttributeError):
                graph_input = {
                    "messages": [("human", message)],
                    "session_id": data.session_id,
                }            
            result = await answer_generator(agent, graph_input, thread_id)

            # Human in the loop 처리
            interrupts = result.get("__interrupt__", ())
            if interrupts:
                val = interrupts[0].value
                if val.get("type") == "select_server":
                    await websocket.send_text(json.dumps({
                        "type":       "select_server",
                        "message":    val.get("message"),
                        "candidates": val.get("candidates"),
                    }, ensure_ascii=False))
                elif val.get("type") == "policy_review":
                    await websocket.send_text(json.dumps({
                        "type":         "policy_review",
                        "policy":       val.get("policy"),
                        "server_info":  val.get("server_info"),
                        "message":      "복구 정책을 검토하고 승인/거절해주세요.",
                    }, ensure_ascii=False))
                else:
                    await websocket.send_text(json.dumps({
                        "type":       "confirm",
                        "confirm_id": str(uuid.uuid4()),
                        "tool":       val.get("tool_name", ""),
                        "args":       val.get("args", {}),
                        "message":    f"'{val.get('tool_name')}' 작업을 실행하시겠습니까?",
                    }, ensure_ascii=False))
            else:
                messages = result.get("messages", [])
                ai_messages = [m for m in messages if isinstance(m, AIMessage) and m.content]
                if ai_messages:
                    await websocket.send_text(ai_messages[-1].content)
            
    except WebSocketDisconnect as e:
        logger.info(f"[WS] 클라이언트 정상 종료 - client={client}, code={e.code}")
    except Exception as e:
        logger.error(f"[WS] 루프 오류 - client={client}, state={websocket.client_state}, error={type(e).__name__}: {e}", exc_info=True)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011)
