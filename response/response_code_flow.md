# `"52 vm을 복구해줘"` 입력 시 실행 코드 흐름 분석

## 먼저 결론

현재 저장소 기준으로 이 요청은 다음 순서로 흘러간다.

1. Horizon UI가 먼저 JWT를 발급받는다. 이 부분은 실제 코드가 저장소에 없고 README 설명만 있다.
2. Horizon UI가 `ws://.../ws/chat?token=...` 으로 FastAPI WebSocket에 연결한다.
3. FastAPI가 JWT와 Redis 세션을 검증한다.
4. 사용자가 `"52 vm을 복구해줘"` 를 보내면 `answer_generator()` 가 LangGraph supervisor를 실행한다.
5. supervisor가 이 요청을 OpenStack 계열 요청으로 해석하면 `openstack_agent` 에게 위임한다.
6. `openstack_agent` 가 MCP tool을 호출하면 `openstack-mcp-server/main.py` 의 `call_tool()` 이 실행된다.
7. 여기서 `get_server_info` 또는 `execute_recovery` 같은 핸들러가 호출된다.
8. 최종 결과 문자열이 다시 WebSocket으로 브라우저에 전송된다.

다만 중요한 점이 있다.

- 현재 구현에는 `"52"` 를 OpenStack 서버 ID로 변환하는 코드가 없다.
- 현재 복구 실행은 실제 OpenStack 복구가 아니라 mock handler다.
- 현재 Human-in-the-loop 승인 단계도 없다.
- 따라서 `"52 vm을 복구해줘"` 가 실제로 자동 복구까지 간다고 단정할 수는 없다.

아래는 현재 코드 기준의 "실행 순서"를 더 자세히 풀어쓴 것이다.

---

## 1. 서버 기동 시 먼저 준비되는 코드

사용자 입력보다 먼저 FastAPI 앱이 시작될 때 아래 코드가 실행된다.

### 1-1. FastAPI lifespan에서 MCP tool 로딩

- 파일: `agent_server/main.py`
- 핵심 위치: `lifespan()` (`11~21`라인)

실행 순서:

1. `MultiServerMCPClient(_slack_mcp_config)` 생성
2. `MultiServerMCPClient(_filesystem_mcp_config)` 생성
3. `MultiServerMCPClient(_openstack_mcp_config)` 생성
4. 각 client에서 `get_tools()` 호출
5. `build_supervisor(slack_tools, filesystem_tools, openstack_tools)` 호출
6. 결과를 `app.state.supervisor` 에 저장

즉, 실제 채팅 메시지가 들어올 때는 이미 supervisor와 OpenStack tool 목록이 메모리에 올라와 있는 상태다.

### 1-2. Supervisor/Agent 구성

- 파일: `agent_server/app/agent/agent.py`
- 핵심 위치:
  - LLM 생성: `14~19`라인
  - supervisor 프롬프트: `25~31`라인
  - OpenStack agent 프롬프트: `46~51`라인
  - supervisor 생성: `84~93`라인

여기서 중요한 해석 포인트:

- supervisor prompt가 "OpenStack 관련 요청은 `openstack_agent` 로 위임" 하도록 명시한다.
- OpenStack agent prompt는 "server info, VM creation, recovery, recovery status" 도구를 쓸 수 있다고 정의한다.

즉 `"52 vm을 복구해줘"` 는 의도상 OpenStack agent로 라우팅되는 요청이다.

---

## 2. Horizon UI에서 채팅을 보내기 직전

이 저장소에는 Horizon 프론트 코드가 들어 있지 않지만, README 설명상 다음 흐름이 선행된다.

- 파일: `README.md`
- 핵심 위치: `93~97`라인

설명된 순서:

1. 페이지 로드 시 `POST /dashboard/ai/session/issue/` 로 JWT 발급
2. 브라우저가 `ws://192.168.88.4:8000/ws/chat?token={aiJwt}` 로 WebSocket 연결
3. 연결 후 채팅 메시지 송수신

즉 `"52 vm을 복구해줘"` 는 HTTP POST가 아니라 WebSocket 텍스트 메시지로 들어온다.

---

## 3. WebSocket 연결 시 실행되는 코드

- 파일: `agent_server/app/ws/chat.py`
- 핵심 위치: `17~57`라인

### 3-1. `/ws/chat` 엔드포인트 진입

사용자가 WebSocket을 열면 `websocket_chat()` 이 실행된다.

순서:

1. `get_redis()` 호출로 Redis 연결 객체 확보 (`26`라인)
2. `await websocket.accept()` 로 핸드셰이크 완료 (`29`라인)
3. `verify_jwt(token, redis)` 호출 (`33`라인)
4. 성공 시 `history_key = f"chat:session:{data.session_id}:history"` 계산 (`34`라인)
5. `supervisor = websocket.app.state.supervisor` 로 미리 준비된 supervisor 참조 (`42`라인)
6. 이후 무한 루프에서 메시지를 계속 받는다 (`44`라인)

### 3-2. JWT 검증 상세

- 파일: `agent_server/app/auth/jwt_verify.py`
- 핵심 위치: `13~59`라인

`verify_jwt()` 내부 순서:

1. `jwt.decode(...)` 로 서명, audience, exp 등을 검증 (`22~30`라인)
2. `iss == settings.jwt_issuer` 확인 (`40~41`라인)
3. payload에서 `session_id` 추출 (`43`라인)
4. `await redis.exists(session_id)` 로 세션 존재 확인 (`44~45`라인)
5. `chat:jti:{jti}` 키로 replay 방지용 `SET NX EX` 수행 (`47~54`라인)
6. 통과 시 `TokenPayload` 반환 (`59`라인)

### 3-3. 여기서 짚고 넘어갈 점

코드상 약간 어색한 부분이 있다.

- README와 문서들은 Redis 세션 키를 `chat:session:{session_id}` 형태로 설명한다.
- 그런데 실제 `verify_jwt()` 는 `redis.exists(session_id)` 를 검사한다.
- 반면 `ws/chat.py` 는 history key를 `chat:session:{session_id}:history` 로 만든다.

즉 현재 구현 기준으로는:

- JWT payload의 `session_id` 값과
- Redis에 실제로 저장해 둔 세션 키 형식이

정확히 맞아야 WebSocket 연결이 통과한다.

---

## 4. `"52 vm을 복구해줘"` 메시지를 보냈을 때

- 파일: `agent_server/app/ws/chat.py`
- 핵심 위치: `44~51`라인

메시지 1건이 들어오면 순서는 단순하다.

1. `message = await websocket.receive_text()` (`45`라인)
2. `result = await answer_generator(supervisor, message)` (`47`라인)
3. `response = f"{result}"` (`50`라인)
4. `await websocket.send_text(response)` (`51`라인)

즉 WebSocket 레이어는 거의 오케스트레이션만 하고, 실제 판단은 `answer_generator()` 아래로 내려간다.

---

## 5. `answer_generator()` 에서 실제 AI 라우팅

- 파일: `agent_server/app/agent/agent.py`
- 핵심 위치: `95~97`라인

실행 순서:

1. `supervisor.ainvoke({"messages": [("human", input)]})` 호출
2. LangGraph supervisor가 사용자 문장을 보고 어느 agent가 처리할지 결정
3. 마지막 메시지의 `content` 를 반환

여기서 `"52 vm을 복구해줘"` 는 문장 의미상 OpenStack 작업으로 분류될 가능성이 높다. 근거는 supervisor prompt다.

- `SUPERVISOR_PROMPT` 에 OpenStack 관련 요청은 `openstack_agent` 로 위임하라고 명시 (`25~31`라인)

즉 논리적 실행 순서는 다음처럼 보는 게 맞다.

1. supervisor가 입력 해석
2. `openstack_agent` 선택
3. `openstack_agent` 가 필요한 MCP tool 호출
4. tool 결과를 바탕으로 한국어 응답 생성

---

## 6. OpenStack agent가 MCP tool을 호출하면 실행되는 코드

OpenStack agent가 실제 tool call을 하면 별도 stdio 프로세스로 띄운 MCP 서버가 받는다.

### 6-1. OpenStack MCP 서버 실행 방식

- 파일: `agent_server/app/agent/agent.py`
- 핵심 위치: `_openstack_mcp_config` (`74~81`라인)

여기서 OpenStack MCP 서버는 아래 방식으로 붙는다.

- 명령: `python main.py`
- 작업 디렉토리: `agent_server/app/mcp_servers/openstack-mcp-server`
- transport: `stdio`

즉 supervisor 내부에서 tool call이 발생하면 결국 이 MCP 서버 프로세스로 전달된다.

### 6-2. MCP 서버의 tool dispatch

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/main.py`
- 핵심 위치: `35~75`라인

`call_tool(name, arguments)` 의 순서:

1. tool 호출 요청 로깅 (`37~44`라인)
2. `match name:` 으로 tool 이름 분기 (`46`라인)
3. 이름에 따라 handler 호출
4. handler 결과를 JSON 문자열로 감싸서 `TextContent` 로 반환 (`75`라인)

가능한 주요 분기:

- `get_server_info` -> `handle_get_server_info(...)` (`47~50`라인)
- `execute_recovery` -> `handle_execute_recovery(...)` (`60~65`라인)
- `get_recovery_status` -> `handle_get_recovery_status(...)` (`67~70`라인)

---

## 7. `"복구"` 요청에서 실제로 호출될 가능성이 높은 tool 순서

현재 tool description을 보면, 정상적인 흐름은 아래와 같다.

### 7-1. 먼저 `get_server_info`

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/tools/compute.py`
- 핵심 위치: `3~19`라인

설명에 이렇게 적혀 있다.

- `execute_recovery` 전에 항상 `get_server_info` 를 먼저 호출해서 상태가 `ERROR` 또는 `SHUTOFF` 인지 확인하라.

그리고 실제 조회 handler는 아래다.

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/handlers/compute.py`
- 핵심 위치: `6~33`라인

실행 내용:

1. `server_id` 를 입력받음
2. mock 서버 딕셔너리에서 ID 검색 (`10~27`라인)
3. 있으면 서버 정보 반환
4. 없으면 `{"error": "Server ... not found"}` 반환 (`29~31`라인)

현재 mock 데이터에서 존재하는 서버는 2개뿐이다.

- `a1b2c3d4-0001` -> `ACTIVE`
- `a1b2c3d4-0002` -> `ERROR`

### 7-2. 그 다음 `execute_recovery`

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/tools/recovery.py`
- 핵심 위치: `3~30`라인

설명에 요구되는 입력:

- `server_id`
- `recovery_type`
- `reason`

실제 실행 handler:

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/handlers/recovery.py`
- 핵심 위치: `8~36`라인

실행 순서:

1. `await asyncio.sleep(0.2)` 로 mock 지연 (`15`라인)
2. `server_id` 가 `a1b2c3d4-0001`, `a1b2c3d4-0002` 중 하나인지 검사 (`18~19`라인)
3. 아니면 `Server not found` 반환
4. 맞으면 `job_id` 생성 (`21`라인)
5. `_job_store` 에 `PENDING` 상태 작업 저장 (`23~31`라인)
6. `{"job_id": ..., "status": "PENDING"}` 반환 (`33~36`라인)

### 7-3. 필요하면 `get_recovery_status`

- 파일: `agent_server/app/mcp_servers/openstack-mcp-server/handlers/recovery.py`
- 핵심 위치: `39~69`라인

이 함수는 polling 시뮬레이션이다.

호출할 때마다:

1. `PENDING -> RUNNING`
2. progress 증가
3. 100% 도달 시 `SUCCESS`

로 바뀐다.

---

## 8. `"52 vm"` 이라는 표현 때문에 실제 분기에서 생기는 문제

이 요청에서 가장 중요한 분석 포인트는 `"52"` 다.

현재 코드에는 아래 기능이 없다.

- `"52"` 를 VM 이름으로 해석하는 로직
- `"52"` 를 OpenStack instance UUID로 매핑하는 로직
- `"52번 VM"` 과 같은 자연어 별칭을 검색하는 로직

반면 OpenStack tool schema는 `server_id` 를 요구한다.

- `get_server_info`: OpenStack instance UUID 필요
- `execute_recovery`: OpenStack instance UUID 필요

그리고 mock handler가 인식하는 값은 오직 아래 2개다.

- `a1b2c3d4-0001`
- `a1b2c3d4-0002`

따라서 `"52 vm을 복구해줘"` 만으로는 현재 구현상 다음 둘 중 하나가 된다.

1. LLM이 `"52"` 를 그대로 `server_id` 로 넣고 tool 호출 -> `Server 52 not found`
2. LLM이 tool 호출을 주저하고 추가 질문을 생성 -> 예: "정확한 서버 ID를 알려달라"

즉 현재 코드만 놓고 보면 `"52 vm"` 요청은 성공 복구보다 "식별 불가" 쪽으로 흐를 가능성이 높다.

---

## 9. 현재 코드 기준의 가장 현실적인 전체 실행 시나리오

현재 구현만 기준으로 가장 그럴듯한 순서를 한 줄씩 쓰면 아래와 같다.

1. Horizon이 JWT 발급 요청
2. 브라우저가 `/ws/chat?token=...` 연결
3. `websocket_chat()` 실행
4. `get_redis()` 실행
5. `websocket.accept()` 실행
6. `verify_jwt()` 실행
7. replay/session 검증 통과
8. 메시지 루프 진입
9. 브라우저가 `"52 vm을 복구해줘"` 전송
10. `receive_text()` 로 메시지 수신
11. `answer_generator()` 실행
12. `supervisor.ainvoke()` 실행
13. supervisor가 `openstack_agent` 선택 시도
14. `openstack_agent` 가 필요 시 `get_server_info` 또는 `execute_recovery` tool 호출
15. OpenStack MCP 서버 `call_tool()` 실행
16. 대응 handler 실행
17. handler 결과가 JSON 문자열로 agent에 반환
18. agent가 최종 한국어 응답 생성
19. `send_text()` 로 브라우저에 응답 전송

---

## 10. 문서상 의도와 현재 구현의 차이

문서 아키텍처만 보면 원래는 다음 단계가 더 있어야 한다.

- VM 식별
- 런북/RAG 검색
- 복구 정책 생성
- 사용자 승인
- 실제 복구 실행
- 상태 스트리밍
- 결과 리포트 저장

하지만 현재 저장소 기준으로는 아직 빠져 있다.

- RAG 구현 없음
- 승인 단계 없음
- 실제 OpenStack SDK 호출 없음
- 실제 VM 내부 recovery API 호출 없음
- audit/job/history 저장 없음

따라서 질문에 대한 가장 정확한 답은 다음이다.

> `"52 vm을 복구해줘"` 를 입력하면 현재 코드는
> `WebSocket -> JWT 검증 -> LangGraph supervisor -> openstack_agent -> OpenStack MCP tool 호출`
> 순서로 실행된다.
> 다만 `"52"` 를 실제 서버로 식별하는 구현이 없어서, 현재 상태에서는 복구 성공보다는 조회 실패 또는 추가 질문 응답으로 끝날 가능성이 높다.

---

## 11. 핵심 파일 요약

- WebSocket 진입점: `agent_server/app/ws/chat.py`
- JWT 검증: `agent_server/app/auth/jwt_verify.py`
- 앱 시작 시 supervisor 구성: `agent_server/main.py`
- supervisor / agent 정의: `agent_server/app/agent/agent.py`
- OpenStack MCP tool 라우팅: `agent_server/app/mcp_servers/openstack-mcp-server/main.py`
- 서버 조회 tool 정의: `agent_server/app/mcp_servers/openstack-mcp-server/tools/compute.py`
- 서버 조회 mock handler: `agent_server/app/mcp_servers/openstack-mcp-server/handlers/compute.py`
- 복구 tool 정의: `agent_server/app/mcp_servers/openstack-mcp-server/tools/recovery.py`
- 복구 mock handler: `agent_server/app/mcp_servers/openstack-mcp-server/handlers/recovery.py`
