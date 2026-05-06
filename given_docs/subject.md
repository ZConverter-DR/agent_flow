# 프로젝트 현황 분석

## 전체 아키텍처

```
브라우저 (Horizon UI)
  │  ① JWT 발급 요청 (50초마다)
  │  ② WebSocket 연결 + 채팅
  ▼
[agent / Horizon Django]  ←── Keystone 세션 기반 인증 SSOT
  │  JWT 발급 (RS256, 60초)
  │  Redis에 세션 메타데이터 저장
  ▼
[agent_server / FastAPI]  ←── AI 채팅 엔진
  │  JWT 검증 + replay 방지
  │  LangGraph Supervisor Agent 실행
  │  MCP Server 호출 (Slack, Filesystem, OpenStack)
  │  AsyncRedisSaver로 대화 체크포인트 저장
  ▼
Redis (공유)              ←── 세션·JTI·LangGraph 체크포인트
[redis/redis-stack-server] ←── RediSearch 모듈 필요 (AsyncRedisSaver 인덱스)
```

---

## 폴더별 현황

### agent/ (Horizon Django 플러그인)

Horizon에 붙는 Django 앱으로, 인증 SSOT 역할을 담당한다.

| 파일 | 역할 | 상태 |
|------|------|------|
| `ai/views.py` | JWT 발급 엔드포인트 (`POST /ai/session/issue/`) | ✅ 구현 완료 |
| `ai/urls.py` | URL 라우팅 | ✅ 구현 완료 |
| `jwt/jwt_utils.py` | RS256 서명으로 JWT 발급 | ✅ 구현 완료 |
| `common/redis_client.py` | Django용 Redis 동기 클라이언트 | ✅ 구현 완료 |

**구현된 내용:**
- 로그인된 Horizon 유저의 `user_id`, `username`, `project_id`, `roles`, `session_id`를 JWT payload에 포함
- JWT 유효기간 60초, RS256 서명 (private key 사용)
- Redis에 `chat:session:{session_key} = "1"` 저장 (FastAPI 세션 검증용)

**미구현 항목:**
- `POST /ai/confirm` — 파괴적 작업 승인 API
- 세션 메타데이터(keystone_token 포함) Redis 적재 훅
- Celery 감사 로그 파이프라인 (AuditLog 모델, Task)

---

### agent_server/ (FastAPI AI Gateway)

LangGraph 기반 AI 채팅 서버. WebSocket으로 클라이언트와 통신한다.

| 파일 | 역할 | 상태 |
|------|------|------|
| `main.py` | lifespan에서 MCP 초기화 + AsyncRedisSaver + Supervisor 빌드 | ✅ 구현 완료 |
| `app/auth/jwt_verify.py` | JWT 검증 (iss/aud/exp/jti/session 5단계) | ✅ 구현 완료 |
| `app/auth/dependencies.py` | `get_current_user`, `require_roles` Depends | ✅ 구현 완료 |
| `app/auth/schema.py` | `TokenPayload` Pydantic 모델 (`sub` = Keystone user_id) | ✅ 구현 완료 |
| `app/common/redis.py` | FastAPI용 Redis 비동기 클라이언트 (`decode_responses=True`) | ✅ 구현 완료 |
| `app/common/config.py` | 환경변수 설정 | ✅ 구현 완료 |
| `app/agent/agent.py` | LangGraph Supervisor + 3개 sub-agent + `wrap_destructive_tools` 적용 | ✅ 구현 완료 |
| `app/agent/tools.py` | 파괴적 툴 래퍼 (`interrupt()` 기반 human-in-the-loop) | 🔶 부분 완료 |
| `app/ws/chat.py` | WebSocket 채팅: 인증·히스토리 복원·interrupt 처리·메시지 루프 | ✅ 구현 완료 |
| `app/mcp_servers/openstack-mcp-server/` | OpenStack MCP Server (stdio, Mock 핸들러) | ✅ Mock 완료 |
| `app/knowledge/runbooks/` | 런북 RAG (빈 디렉토리) | ❌ 미구현 |

**구현된 내용:**

**인증·세션:**
- JWT 5단계 검증: iss → aud → exp(±10초 leeway) → jti replay → session 존재
- `thread_id = data.sub` (Keystone user_id) — 재접속·새로고침 후에도 동일 히스토리 유지

**LangGraph Supervisor:**
- `create_supervisor` + `create_react_agent` (prebuilt) 패턴
  - `slack_agent` — `@modelcontextprotocol/server-slack` (npx stdio)
  - `filesystem_agent` — `@modelcontextprotocol/server-filesystem` (npx stdio, `/app`)
  - `openstack_agent` — 로컬 Python MCP 서버 (stdio, Mock)
- FastAPI lifespan에서 MCP 클라이언트 1회 초기화 → `app.state.supervisor` 저장
- LLM: Ollama `qwen2.5:7b` (호스트 `10.0.2.2:11434`, OpenAI-compatible API)

**대화 이력 (AsyncRedisSaver):**
- `langgraph-checkpoint-redis`의 `AsyncRedisSaver` 사용
- Redis 이미지: `redis/redis-stack-server` (RediSearch 모듈 필요)
- TTL: `default_ttl=60분`, `refresh_on_read=True` (마지막 대화 후 60분)
- WebSocket 연결 시 `aget_state()`로 이전 대화 복원 → `type:"history"` 전송
- 히스토리 필터링: `last_ai` 덮어쓰기 방식으로 내부 라우팅 메시지(`Transferring`) 및 중복 응답 제거

**Human-in-the-loop:**
- `app/agent/tools.py`: `DESTRUCTIVE_TOOL_NAMES = {"create_vm", "execute_recovery"}`
- 파괴적 툴 호출 시 `interrupt()` → 그래프 일시 정지 → WS로 `type:"confirm"` 전송
- 사용자 응답 (`type:"confirm_response"`) → `Command(resume=True/False)` → 그래프 재개
- 승인 시 툴 실행, 거부 시 "작업이 취소되었습니다." 반환

**미구현 / 보완 필요 항목:**
- `qwen2.5:7b` 컨텍스트 누적 시 tool calling 불안정 → 더 큰 모델 검토 필요
- 감사 로그 push (`chat:audit:queue`) 미구현
- 장시간 작업 비동기 처리 (`chat:job:{job_id}`) 미구현
- Filesystem MCP는 테스트용 (추후 운영 목적 서버로 교체 검토)
- OpenStack MCP 핸들러가 Mock 구현 → 실제 openstacksdk 연동 필요
- `get_server_info` ID/이름 동시 검색 미구현 (Option A: `server_identifier` 단일 파라미터 방식 검토 중)

---

### horizon/ (Horizon 프론트엔드)

| 파일 | 역할 | 상태 |
|------|------|------|
| `static/dashboard/chat/chat.js` | JWT 갱신(50초) | ✅ 구현 완료 |
| `dashboards/project/overview/templates/overview/usage.html` | 채팅 UI + WebSocket + 히스토리 복원 + confirm 처리 | ✅ 구현 완료 |

**구현된 내용:**
- 페이지 로드 시 JWT 발급 (`POST /dashboard/ai/session/issue/`)
- 50초마다 JWT 자동 갱신, 탭 포커스 복귀 시 즉시 갱신
- `ws://192.168.88.4:8000/ws/chat?token={aiJwt}`로 WebSocket 연결
- 연결 상태 표시 (connected / disconnected / connecting)
- 메시지 송수신, 마크다운 렌더링, 로딩 애니메이션
- `type:"history"` 수신 시 이전 대화 복원 렌더링
- `type:"confirm"` 수신 시 승인/거부 버튼 UI 표시 → `confirm_response` 전송

**미구현 / 보완 필요 항목:**
- 장시간 작업 진행 상태 표시 없음

---

## Redis 키 사용 현황

| 키 패턴 | 타입 | 용도 | 구현 |
|---------|------|------|------|
| `chat:session:{session_id}` | String | 세션 메타데이터 (JSON) | ✅ 구현 완료 |
| `chat:jti:{jti}` | String | Replay 방지 | ✅ 구현 완료 |
| `checkpoint:*` | Hash/Index | LangGraph 체크포인트 (AsyncRedisSaver) | ✅ 구현 완료 |
| `chat:audit:queue` | List | 감사 로그 큐 | ❌ 미구현 |
| `chat:confirm:{confirm_id}` | String | 파괴적 작업 확인 상태 | ❌ 미구현 (WS 방식으로 대체) |
| `chat:job:{job_id}` | String | 장시간 작업 상태 | ❌ 미구현 |

> `chat:session:{session_id}:history` — AsyncRedisSaver 체크포인트로 대체되어 별도 구현 불필요 판단

---

## 다음 구현 우선순위

### Phase 2 — 안전성·감사
1. 감사 로그 `chat:audit:queue` push + Celery drain
2. `POST /ai/confirm` Django 엔드포인트 구현 (현재 WS 방식으로 우회 중)

### Phase 3 — OpenStack 연동
3. OpenStack MCP 핸들러 Mock → 실제 openstacksdk 연동
4. `get_server_info`: `server_identifier` 단일 파라미터로 ID/이름 동시 검색 지원
5. 런북 RAG (`app/knowledge/runbooks/`) 구현
6. `chat:job:{job_id}` 장시간 작업 비동기 처리
7. Filesystem MCP → 운영 목적에 맞는 MCP 서버로 교체 검토

---

## OpenStack 연동 설계 결정 (Phase 3 상세)

### 문제: MCP 서버에 Keystone Token을 어떻게 전달할 것인가

유저의 Keystone token은 Redis `chat:session:{session_id}`에 평문으로 저장되어 있다.
openstack-mcp-server가 `openstacksdk`로 OpenStack API를 호출하려면 이 token이 필요하다.

### 검토한 방안 및 기각 이유

| 방안 | 내용 | 기각 이유 |
|------|------|-----------|
| A | `keystone_token`을 `ChatState`에 저장 | LangGraph checkpoint에 token 평문 저장됨 |
| B | token을 MCP tool 인자로 직접 전달 | MCP 서버 `call_tool()`이 `arguments` 전체를 로깅 → 평문 노출 |
| C | MCP 서버가 Redis에서 직접 fetch | 최소 권한 원칙 위반 (Redis 전체 접근: 모든 유저 token·대화 이력·JTI 데이터) |
| D | token 암호화 후 인자 전달 | MCP 서버에 복호화 키 필요 → 새로운 공격 포인트 추가 |

### 결정된 방안: nodes.py가 Redis fetch → MCP tool 인자 전달 + 로그 마스킹

```
chat.py         → session_id를 graph_input에 포함
ChatState       → session_id 필드 추가 (token 아님, checkpoint 저장 무해)
nodes.py        → state["session_id"]로 Redis에서 keystone_token fetch
                   → mcp_tools[...].ainvoke({"server_id": ..., "keystone_token": token})
MCP main.py     → 로깅 시 SENSITIVE_KEYS 마스킹 처리
handlers/*.py   → keystone_token 인자 받아 openstack.connect(token=...) 호출
```

**핵심 근거:**
- `nodes.py`는 FastAPI 앱 내부 → Redis 접근이 이미 정당한 컴포넌트
- MCP 서버는 Redis 접근 불필요 → 최소 권한 유지
- token은 FastAPI 프로세스 경계 안에서만 Redis 접근, MCP 서버에는 tool 인자로만 전달
- MCP 서버 로그 마스킹으로 stdio 경계 통과 시 노출 차단

### openstack.connect() 방식

- MCP tool 호출마다 `with openstack.connect(auth_type="token", token=keystone_token) as conn:` 생성
- token이 user마다 다르고 TTL이 있어 사전 생성(pre-create) 불가
- `openstack.connect()` 자체는 네트워크 호출 없는 경량 객체 생성 → per-call 방식 적합

### session_id 변경 시점 (Horizon)

| 이벤트 | session_id 변경 |
|--------|-----------------|
| 로그인 (`auth.login()`) | **변경됨** — Django 세션 고정 공격 방지 |
| 로그아웃 (`auth.logout()`) | **변경됨** — 세션 flush |
| Keystone provider 전환 | **변경됨** — `auth.login()` 재호출 |
| 프로젝트 전환 (`switch()`) | **유지됨** — `set_session_from_user()`만 호출 |
| 리전 전환 | **유지됨** — `set_session_from_user()`만 호출 |

**프로젝트 전환 시 주의:** session_id는 유지되지만 Keystone token은 교체됨.
UI가 50초마다 `/ai/session/issue`를 호출하므로 최대 50초간 stale token 가능.
→ 향후 프로젝트 전환 시점에 즉시 `/ai/session/issue` 재호출하는 Horizon 훅 추가 권장.

### 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `app/graph_agent/state.py` | `ChatState`에 `session_id: str \| None` 필드 추가 |
| `app/ws/chat.py` | `graph_input`에 `session_id` 포함 (새 메시지 입력 시) |
| `app/graph_agent/nodes.py` | OpenStack tool 호출 노드에서 Redis fetch 후 `keystone_token` 주입 |
| `mcp_servers/openstack-mcp-server/main.py` | `call_tool()` 로그 마스킹 (`SENSITIVE_KEYS`) |
| `mcp_servers/openstack-mcp-server/handlers/compute.py` | `keystone_token` 인자 추가, `openstack.connect(token=...)` 실제 호출 |

### Phase 4 — 안정성
8. LLM 모델 교체 검토 (`qwen2.5:14b` 이상) — 컨텍스트 누적 시 tool calling 불안정 이슈
9. DB volume 마운트 추가 (`docker compose down` 후에도 체크포인트 유지)
