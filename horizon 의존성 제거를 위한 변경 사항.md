# horizon 의존성 제거를 위한 변경 사항

** 김운강 정리 : horizon 의존성을 제거하기 위해 몇 가지 작업을 했습니다 !

1) horizon 없이도 fastAPI, redis, ollama를 띄운 뒤에 http://localhost:8000/dev/chat 에서 채팅을 보낼 수 있도록 수정했습니다.
2) 채팅 페이지에 들어가면 "토큰 발급 후 연결" 버튼이 있습니다. 해당 버튼을 누르면 fastAPI에 저장된 비대칭키를 바탕으로 인증에 사용 가능한 JWT가 생성되어 채팅 페이지로 내려집니다.
3) JWT를 발급 받은 뒤엔 정상적으로 fastAPI의 오케스트레이션 로직을 활성화 시킬 수 있습니다. 

## 1. 어떤 기능을 구현한 것인가

이 작업의 목적은 **Horizon 없이도 개발자가 브라우저에서 바로 채팅 UI를 열고, 서버가 dev 전용 JWT를 발급한 뒤, 그 JWT를 사용해 기존 WebSocket 채팅 엔진과 orchestration 로직을 그대로 활성화할 수 있게 만드는 것**이다.

기존 운영 흐름은 대략 아래와 같다.

1. Horizon이 사용자 인증을 처리한다.
2. Horizon이 JWT를 발급한다.
3. 브라우저나 클라이언트가 `/ws/chat?token=...` 으로 접속한다.
4. FastAPI가 JWT를 검증한다.
5. 검증이 끝나면 LangGraph 기반 orchestration 로직이 동작한다.

dev 전용 채팅 페이지를 붙이면서 바뀐 점은 **Horizon이 하던 "JWT 발급자" 역할만 FastAPI dev endpoint로 대체했다는 것**이다.

즉, 현재 dev 흐름은 아래와 같다.

1. 개발자가 `/dev/chat` 페이지를 연다.
2. 페이지에서 username을 입력한다.
3. 프런트 JS가 `POST /dev/chat/token`으로 username을 전송한다.
4. FastAPI가 dev 전용 JWT를 발급하고 Redis에 세션도 준비한다.
5. 프런트 JS가 발급받은 JWT를 붙여 기존 `/ws/chat?token=...` 경로로 WebSocket 연결을 연다.
6. FastAPI는 운영과 동일하게 `verify_jwt()`로 JWT를 검증한다.
7. 검증 성공 후 기존 orchestration 로직인 `answer_generator()`가 그대로 실행된다.

핵심은 다음 두 가지다.

1. **새 WebSocket 경로를 만들지 않았다.**
2. **채팅 엔진 본체를 우회하지 않고 기존 JWT 검증과 기존 orchestration 흐름을 그대로 재사용했다.**

---

## 2. 전체 구조에서 바뀐 점

dev 전용 채팅 기능을 붙이기 위해 실제로 추가된 구조는 아래와 같다.

1. `GET /dev/chat`
   개발용 채팅 UI HTML을 반환한다.
2. `POST /dev/chat/token`
   username을 받아 dev JWT를 발급한다.
3. 기존 `GET/POST` HTTP 진입은 새로 추가했지만, **실제 채팅은 여전히 `/ws/chat`로 들어간다.**
4. JWT 검증은 `app.auth.jwt_verify.verify_jwt()`가 그대로 담당한다.
5. `main.py`는 별도의 신규 라우터를 추가하지 않고, 기존처럼 `app.ws.chat.router`를 include한 상태에서 새 HTTP endpoint까지 함께 노출한다.

정리하면, **Horizon 의존성 제거는 "JWT 발급의 앞단 대체"에 집중되어 있고, WebSocket 채팅 및 orchestration 본체는 유지되는 형태**다.

---

## 3. 파일별 상세 설명

### 3.1 `agent_server/app/ws/chat.py`

이 파일은 dev 채팅 기능의 중심 진입점이다. 원래 WebSocket 채팅 로직만 있던 파일에 dev UI와 dev token 발급 endpoint가 추가되었다.

#### 추가된 import

- `re`
  username 형식 검증용 정규식에 사용한다.
- `uuid`
  dev token의 `jti` 생성과 confirm id 생성에 사용한다.
- `datetime`, `timedelta`, `timezone`
  JWT의 `iat`, `exp`, 로그 시각 계산에 사용한다.
- `jwt`
  dev token 발급 시 서명에 사용한다.
- `HTTPException`, `status`
  dev endpoint에서 에러 응답을 만들 때 사용한다.
- `HTMLResponse`
  `/dev/chat`에서 HTML 페이지를 직접 반환하기 위해 사용한다.
- `BaseModel`
  `POST /dev/chat/token` 요청 body 스키마 정의에 사용한다.
- `build_dev_chat_html`
  dev HTML 본문을 별도 파일에서 가져오기 위해 `app.ws.dev_chat_html`에서 import한다.

#### 추가된 상수와 모델

- `_DEV_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")`
  dev username에 허용할 문자 범위를 제한한다.

- `class DevChatTokenRequest(BaseModel)`
  `POST /dev/chat/token` 요청 body를 `{"username": "alice"}` 형태로 받기 위한 모델이다.

#### 추가된 보조 함수

- `_ensure_dev_chat_enabled()`
  `settings.dev_chat_enabled`가 `False`이면 `404 dev chat disabled`를 반환한다.
  운영 환경에서 dev 채팅을 쉽게 비활성화하기 위한 가드 역할이다.

- `_load_dev_private_key()`
  `settings.dev_private_key_path`에 있는 private key 파일을 읽어 dev JWT 서명에 사용한다.

#### 추가된 HTTP endpoint: `GET /dev/chat`

```python
@router.get("/dev/chat", response_class=HTMLResponse)
async def dev_chat_page():
    _ensure_dev_chat_enabled()
    return HTMLResponse(build_dev_chat_html())
```

이 endpoint는 브라우저에서 dev 채팅 페이지를 열 때 사용된다.

역할은 단순하다.

1. dev 채팅 기능이 활성화되어 있는지 확인한다.
2. `dev_chat_html.py`가 반환하는 HTML 문자열을 그대로 응답한다.

즉, 별도 템플릿 엔진 없이 **FastAPI가 즉시 렌더링 가능한 정적 HTML 문자열을 반환하는 구조**다.

#### 추가된 HTTP endpoint: `POST /dev/chat/token`

이 endpoint가 Horizon 대신 dev JWT를 발급하는 핵심이다.

흐름은 아래와 같다.

1. `_ensure_dev_chat_enabled()`로 기능 활성화 여부를 확인한다.
2. 요청 body의 `username`을 `strip()`한다.
3. 빈 값이면 `400 username is required`를 반환한다.
4. 정규식에 맞지 않으면 `400 invalid username`을 반환한다.
5. Redis 연결을 가져온다.
6. 현재 UTC 시각을 기준으로 `iat`, `exp`를 계산한다.
7. `session_id = f"dev-session:{username}"`를 만든다.
8. `jti = str(uuid.uuid4())`로 고유 토큰 ID를 만든다.
9. Redis에 `session_id`를 TTL과 함께 저장한다.
10. JWT payload를 구성한다.
11. private key와 `settings.jwt_algorithm`으로 서명한다.
12. `{"token": token, "username": username}`를 반환한다.

여기서 중요한 점은 **단순히 JWT만 발급하는 것이 아니라 Redis 세션도 같이 만든다는 것**이다.

이유는 `verify_jwt()`가 아래 조건을 요구하기 때문이다.

1. 서명 유효성
2. issuer 일치
3. audience 일치
4. `session_id`가 Redis에 존재할 것
5. `jti` replay 방지 규칙을 통과할 것

즉, dev endpoint는 기존 검증기가 기대하는 조건을 미리 맞춰 주는 역할을 한다.

#### 발급되는 dev JWT payload

현재 payload는 아래 구조를 따른다.

```json
{
  "iss": "horizon-django",
  "aud": "ai-gateway",
  "sub": "dev:alice",
  "project_id": "dev-project",
  "username": "alice",
  "roles": ["dev"],
  "scope": "dev-chat",
  "session_id": "dev-session:alice",
  "jti": "uuid",
  "iat": 1710000000,
  "exp": 1710000120
}
```

이 구조는 기존 `TokenPayload` 스키마와 맞도록 구성되어 있다.

특히 `sub`에 `dev:` prefix를 넣은 이유는, WebSocket 채팅 루프에서 `data.sub`를 곧바로 `thread_id`로 사용하기 때문이다. 그래서 dev 사용자별로 대화 thread를 분리할 수 있다.

#### 기존 `/ws/chat`와의 관계

`chat.py`의 가장 중요한 설계 포인트는 **dev 전용 WebSocket 경로를 만들지 않았다는 점**이다.

기존 endpoint는 그대로 유지된다.

```python
@router.websocket('/ws/chat')
async def websocket_chat(...)
```

이 함수의 흐름은 다음과 같다.

1. `token` query parameter를 받는다.
2. `verify_jwt(token, redis)`를 호출한다.
3. 반환된 `data.sub`를 `thread_id`로 사용한다.
4. 기존 checkpoint 상태에서 history를 복원한다.
5. 클라이언트가 보낸 메시지를 `answer_generator()`에 넘긴다.
6. orchestration 결과를 다시 WebSocket으로 응답한다.

즉, dev 채팅 페이지는 **JWT 발급 방식만 바꾸고, WebSocket 이후의 실행 경로는 운영과 동일하게 유지**한다.

#### 추가된 로그

dev 채팅과 관련해 다음 로그가 추가되었다.

1. `[DEV JWT] 발급 성공`
   어떤 username으로 어떤 `sub`, `session_id`가 만들어졌는지 로그를 남긴다.
2. `[WS] 인증 성공`
   어떤 client가 어떤 thread_id로 인증되었는지 남긴다.
3. `[WS] 사용자 메시지 수신`
   누가 어떤 메시지를 몇 시에 보냈는지 남긴다.
4. `[WS] confirm 응답 수신`
   human-in-the-loop confirm 응답도 별도 추적 가능하게 했다.

이 로그들은 dev 테스트 과정에서 JWT 발급, JWT 검증, 실제 메시지 진입 시점을 모두 FastAPI 로그로 확인할 수 있게 해준다.

---

### 3.2 `agent_server/app/ws/dev_chat_html.py`

이 파일은 **dev 전용 채팅 UI HTML 문자열만 담당하는 분리된 모듈**이다.

원래 `chat.py` 안에 `_build_dev_chat_html()` 함수로 들어 있던 긴 HTML/JS/CSS 문자열을 별도 파일로 분리했다.

현재 구조는 아래와 같다.

```python
def build_dev_chat_html() -> str:
    return """..."""
```

이 파일을 분리한 이유는 다음과 같다.

1. `chat.py`가 너무 커지는 것을 막기 위해
2. WebSocket/토큰 발급 로직과 UI 문자열을 분리하기 위해
3. dev 채팅 화면만 따로 수정할 때 서버 로직과 충돌을 줄이기 위해

#### 이 파일 안의 실제 역할

이 파일은 단순 HTML만 담고 있는 것이 아니라, dev 채팅 페이지의 프런트 동작도 포함한다.

주요 UI 동작은 다음과 같다.

1. username 입력 필드 렌더링
2. `토큰 발급 후 연결` 버튼 제공
3. `연결 종료` 버튼 제공
4. 메시지 입력 textarea와 전송 버튼 제공
5. WebSocket history 메시지 렌더링
6. interrupt 기반 confirm UI 렌더링
7. approve / reject 전송

#### 프런트 JavaScript 흐름

`build_dev_chat_html()` 안의 JS는 아래 순서로 동작한다.

1. 사용자가 username을 입력한다.
2. `connect()`가 호출된다.
3. `issueToken(username)`가 `/dev/chat/token`으로 POST 요청을 보낸다.
4. 응답으로 받은 `token`과 `username`을 state에 저장한다.
5. `new WebSocket(.../ws/chat?token=...)`으로 기존 WebSocket 엔드포인트에 연결한다.
6. `sendMessage()`는 `{ content }` JSON 형태로 메시지를 전송한다.
7. 서버에서 `history` 타입이 오면 과거 대화를 복원해서 보여 준다.
8. 서버에서 `confirm` 타입이 오면 approve/reject UI를 띄운다.
9. `sendConfirm()`은 `{ type: "confirm_response", confirm_id, approved }` 형식으로 다시 서버에 보낸다.

즉, `dev_chat_html.py`는 **Horizon이 없는 개발 환경에서 최소한의 dev client 역할을 하는 내장 프런트엔드**라고 볼 수 있다.

---

### 3.3 `agent_server/app/auth/jwt_verify.py`

이 파일은 dev 전용 구현에서 "새 검증기"를 만들지 않고 **기존 검증기를 그대로 재사용하는 핵심 포인트**다.

`verify_jwt()`는 현재 다음 검증을 수행한다.

1. public key 기반 서명 검증
2. `audience` 검증
3. `issuer` 검증
4. Redis의 `session_id` 존재 여부 검증
5. Redis를 이용한 `jti` replay 방지
6. `TokenPayload` 변환

즉, dev UI가 보낸 토큰도 운영과 동일한 검증 규칙을 통과해야 한다.

이 덕분에 dev 환경이라고 해서 보안 경로를 우회하지 않는다. 대신 `POST /dev/chat/token`이 **검증기가 요구하는 형식과 Redis 상태를 미리 맞춰 주는 방식**으로 설계되었다.

또한 현재는 아래 로그가 추가되어 있다.

```python
logger.info(
    "[JWT] 검증 성공 - username=%s, sub=%s, session_id=%s, verified_at=%s",
    ...
)
```

이 로그를 통해 dev token이 실제로 기존 검증기에서 정상 통과했는지를 FastAPI 로그에서 확인할 수 있다.

주의할 점은 `verified_at`에 현재 시각이 아니라 `token_payload.iat`가 찍히도록 구현되어 있다는 것이다. 의미상 "토큰 발급 시각"에 가깝고, 실제 검증 시각을 기록하려면 `datetime.now(timezone.utc).isoformat()` 같은 값을 써야 한다.

---

### 3.4 `agent_server/app/common/config.py`

dev 채팅 구현을 위해 설정 항목도 추가되었다.

관련 항목은 아래와 같다.

1. `dev_chat_enabled: bool = False`
   dev 채팅 기능 활성화 여부
2. `dev_private_key_path: str = "secrets/private_key.pem"`
   dev JWT 서명용 private key 경로
3. `dev_jwt_ttl: int = 120`
   dev JWT 만료 시간
4. `dev_session_ttl: int = 120`
   Redis에 저장하는 dev session TTL

이 설정들은 dev 채팅 기능을 운영 환경과 분리해 on/off 할 수 있게 하고, JWT 발급과 Redis session 수명을 짧게 유지하게 해 준다.

또한 `ollama_base_url`도 설정값으로 정의되어 있으며, 이후 LLM 연결 하드코딩 제거 작업에서 이 값을 실제로 사용하도록 수정되었다.

---

### 3.5 `agent_server/main.py`

`main.py`는 별도의 dev 전용 라우터를 새로 만들지 않았다.

대신 기존처럼 아래 코드로 `chat.py`의 router를 include한다.

```python
from app.ws.chat import router as ws_router
...
app.include_router(ws_router)
```

중요한 점은 `chat.py` 안에 이제 다음이 모두 함께 들어 있다는 것이다.

1. `GET /dev/chat`
2. `POST /dev/chat/token`
3. `WebSocket /ws/chat`

즉, `main.py` 입장에서는 추가 작업이 거의 필요 없고, **기존 router include만으로 dev UI, dev token 발급, 기존 WS 채팅까지 모두 노출되는 구조**가 되었다.

---

## 4. 구현의 핵심 설계 요약

이번 dev 전용 채팅 페이지 구현은 단순히 "테스트용 HTML을 붙였다" 수준이 아니라, 다음 설계를 따른다.

1. Horizon이 하던 JWT 발급만 FastAPI dev endpoint가 대신한다.
2. WebSocket 경로는 새로 만들지 않고 기존 `/ws/chat`를 재사용한다.
3. JWT 검증은 기존 `verify_jwt()`를 그대로 사용한다.
4. 검증기가 요구하는 Redis session과 `jti` 조건도 dev token 발급 시점에 맞춰 준다.
5. orchestration 본체인 `answer_generator()` 호출 경로는 변경하지 않는다.

결과적으로 이 구조는 **Horizon 의존성은 제거하면서도, 실제 채팅 서버의 핵심 실행 경로는 최대한 운영과 동일하게 유지하는 방식**이라고 정리할 수 있다.

---

## 5. 파일 단위 변경 요약

### 추가된 파일

1. `agent_server/app/ws/dev_chat_html.py`
   dev 채팅 UI HTML/JS/CSS 문자열을 담당하는 파일

### 주요 변경 파일

1. `agent_server/app/ws/chat.py`
   dev UI endpoint, dev token 발급 endpoint, 기존 WS 채팅 재사용, dev 관련 로그 추가
2. `agent_server/app/auth/jwt_verify.py`
   기존 JWT 검증기 유지, 검증 성공 로그 추가
3. `agent_server/app/common/config.py`
   dev 채팅 활성화 및 dev JWT 관련 설정 추가
4. `agent_server/main.py`
   기존 router include 구조로 새 endpoint들을 함께 노출

---

## 6. 결론

이번 변경은 **Horizon이 없는 개발 환경에서도, 브라우저에서 직접 dev 채팅 UI를 열고, 서버가 dev JWT를 발급하고, 그 JWT로 기존 `/ws/chat`를 통과해 실제 orchestration 로직을 그대로 실행할 수 있도록 만든 작업**이다.

즉, 새로 만든 것은 앞단 dev 진입부이고, 최대한 유지한 것은 기존 서버의 인증 후 채팅 실행 경로다.
