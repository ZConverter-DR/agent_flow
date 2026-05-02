# agent_flow


## 브랜치 전략

- master: 최종 제출 브랜치
- develop: 통합 개발 브랜치
- feat: 기능 개발 브랜치

## 협업 가이드

- [CONTRIBUTING.md](./CONTRIBUTING.md)


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
  │  LangGraph ReAct Agent 실행 (Flat Single Agent)
  │  MCP Server 호출 (Slack, OpenStack)
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
| `main.py` | lifespan에서 MCP 초기화 + AsyncRedisSaver + Agent 빌드 | ✅ 구현 완료 |
| `app/auth/jwt_verify.py` | JWT 검증 (iss/aud/exp/jti/session 5단계) | ✅ 구현 완료 |
| `app/auth/dependencies.py` | `get_current_user`, `require_roles` Depends | ✅ 구현 완료 |
| `app/auth/schema.py` | `TokenPayload` Pydantic 모델 (`sub` = Keystone user_id) | ✅ 구현 완료 |
| `app/common/redis.py` | FastAPI용 Redis 비동기 클라이언트 (`decode_responses=True`) | ✅ 구현 완료 |
| `app/common/config.py` | 환경변수 설정 | ✅ 구현 완료 |
| `app/agent/agent.py` | LangGraph Flat ReAct Agent + `wrap_destructive_tools` 적용 | ✅ 구현 완료 |
| `app/agent/tools.py` | 파괴적 툴 래퍼 (`interrupt()` 기반 human-in-the-loop) | ✅ 구현 완료 |
| `app/ws/chat.py` | WebSocket 채팅: 인증·히스토리 복원·interrupt 처리·메시지 루프 | ✅ 구현 완료 |
| `app/mcp_servers/openstack-mcp-server/` | OpenStack MCP Server (stdio, Mock 핸들러) | ✅ Mock 완료 |
| `app/mcp_servers/test_mock_server/` | 테스트용 Mock MCP Server (generate_policy, generate_report, save_history) | ✅ Mock 완료 / 연동 대기 |
| `app/knowledge/runbooks/` | 런북 RAG (빈 디렉토리) | ❌ 미구현 |

**구현된 내용:**

**인증·세션:**
- JWT 5단계 검증: iss → aud → exp(±10초 leeway) → jti replay → session 존재
- `thread_id = data.sub` (Keystone user_id) — 재접속·새로고침 후에도 동일 히스토리 유지

**LangGraph Flat Single Agent:**
- `create_react_agent` (prebuilt) 단일 에이전트 패턴 — Supervisor 패턴에서 전환
- 연결된 MCP 서버:
  - Slack — `@modelcontextprotocol/server-slack` (npx stdio), 허용 툴 4개로 제한
  - OpenStack — 로컬 Python MCP 서버 (stdio, Mock)
- FastAPI lifespan에서 MCP 클라이언트 1회 초기화 → `app.state.agent` 저장
- LLM: Ollama `qwen2.5:7b` (호스트 `10.0.2.2:11434`, OpenAI-compatible API)

**Slack 허용 툴 (4개):**
```
slack_post_message       — 채널에 메시지 전송
slack_reply_to_thread    — 스레드에 답글
slack_add_reaction       — 메시지에 이모지 반응 추가
slack_get_channel_history — 채널 히스토리 조회 (채널 ID로 특정 메시지 ts 획득 시 필요)
```
> Slack App 필요 OAuth Scope: `chat:write`, `chat:write.public`, `reactions:write`, `channels:history`

**OpenStack 툴 (4개):**
```
get_server_info      — VM 상세 정보 조회
create_vm            — VM 생성 (파괴적 툴 — human-in-the-loop 적용)
execute_recovery     — VM 복구 실행 (파괴적 툴 — human-in-the-loop 적용)
get_recovery_status  — 복구 작업 상태 조회
```

**대화 이력 (AsyncRedisSaver):**
- `langgraph-checkpoint-redis`의 `AsyncRedisSaver` 사용
- Redis 이미지: `redis/redis-stack-server` (RediSearch 모듈 필요)
- TTL: `default_ttl=60분`, `refresh_on_read=True` (마지막 대화 후 60분)
- WebSocket 연결 시 `aget_state()`로 이전 대화 복원 → `type:"history"` 전송

**Human-in-the-loop:**
- `app/agent/tools.py`: `DESTRUCTIVE_TOOL_NAMES = {"create_vm", "execute_recovery"}`
- 파괴적 툴 호출 시 `interrupt()` → 그래프 일시 정지 → WS로 `type:"confirm"` 전송
- 사용자 응답 (`type:"confirm_response"`) → `Command(resume=True/False)` → 그래프 재개
- 승인 시 툴 실행, 거부 시 `[CANCELLED]` 반환

**미구현 / 보완 필요 항목:**
- `test_mock_server` 연동 코드 작성 완료, 현재 `main.py`에서 주석 처리 상태 — 툴 선택 검증 후 활성화 예정
- 감사 로그 push (`chat:audit:queue`) 미구현
- 장시간 작업 비동기 처리 (`chat:job:{job_id}`) 미구현
- OpenStack MCP 핸들러가 Mock 구현 → 실제 openstacksdk 연동 필요
- `get_server_info` ID/이름 동시 검색 미구현

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

## 설계 변경 이력

### Supervisor 패턴 → Flat Single Agent 전환

**변경 전:**
- `langgraph_supervisor`의 `create_supervisor` 사용
- Supervisor 1개 + sub-agent 3개 (slack / filesystem / openstack)
- LLM 호출 2회 (라우팅 + 툴 선택)

**변경 후:**
- `create_react_agent` 단일 에이전트
- LLM 호출 1회 (툴 선택만)
- 툴 총합 기준으로 관리 (qwen2.5:7b 안정 범위: 10개 이하)

**변경 이유:**
- Supervisor 패턴은 LLM이 `transfer_to_*` 툴콜을 생성해야 하는 추가 판단 단계가 있음
- qwen2.5:7b(7B) 소형 모델에서 2단계 LLM 체인이 불안정했음
- 툴 총합 6~8개 수준에서는 Flat Agent가 더 안정적이고 단순함

### Filesystem MCP 제거

- 운영 목적에 맞는 MCP 서버로 교체 예정, 현재 비활성화

### Slack 툴 필터링 추가

- `@modelcontextprotocol/server-slack`의 전체 툴 대신 필요한 4개만 노출
- `main.py`에서 `get_tools()` 결과를 허용 목록으로 필터링

---

## Redis 키 사용 현황

| 키 패턴 | 타입 | 용도 | 구현 |
|---------|------|------|------|
| `chat:session:{session_id}` | String | 세션 메타데이터 (JSON) | ✅ 구현 완료 |
| `chat:jti:{jti}` | String | Replay 방지 | ✅ 구현 완료 |
| `checkpoint:*` | Hash/Index | LangGraph 체크포인트 (AsyncRedisSaver) | ✅ 구현 완료 |
| `chat:audit:queue` | List | 감사 로그 큐 | ❌ 미구현 |
| `chat:job:{job_id}` | String | 장시간 작업 상태 | ❌ 미구현 |

---

## 다음 구현 우선순위

### Phase 2 — 툴 선택 검증
1. `test_mock_server` 활성화 후 qwen2.5:7b 툴 선택 정확도 검증
2. 검증 완료 후 실 MCP 서버 3개 구성 확정 (각 2~3개 툴, 총합 6~9개)

### Phase 3 — 안전성·감사
3. 감사 로그 `chat:audit:queue` push + Celery drain
4. `POST /ai/confirm` Django 엔드포인트 구현 (현재 WS 방식으로 우회 중)

### Phase 4 — OpenStack 연동
5. OpenStack MCP 핸들러 Mock → 실제 openstacksdk 연동
6. `get_server_info`: `server_identifier` 단일 파라미터로 ID/이름 동시 검색 지원
7. 런북 RAG (`app/knowledge/runbooks/`) 구현
8. `chat:job:{job_id}` 장시간 작업 비동기 처리

### Phase 5 — 안정성
9. LLM 모델 교체 검토 (`qwen2.5:14b` 이상) — 컨텍스트 누적 시 tool calling 불안정 이슈
10. DB volume 마운트 추가 (`docker compose down` 후에도 체크포인트 유지)
