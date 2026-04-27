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
  │  pydantic-ai Agent 실행
  │  MCP Server 호출
  ▼
Redis (공유)              ←── 세션·이력·JTI·감사 큐
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

**미구현 항목 (role.md 기준):**
- `POST /ai/confirm` — 파괴적 작업 승인 API
- 세션 메타데이터(keystone_token 포함) Redis 적재 훅
- Celery 감사 로그 파이프라인 (AuditLog 모델, Task)

---

### agent_server/ (FastAPI AI Gateway)

pydantic-ai 기반 AI 채팅 서버. WebSocket으로 클라이언트와 통신한다.

| 파일 | 역할 | 상태 |
|------|------|------|
| `main.py` | FastAPI 앱 진입점, 라우터 등록 | ✅ 구현 완료 |
| `app/auth/jwt_verify.py` | JWT 검증 (iss/aud/exp/jti/session 5단계) | ✅ 구현 완료 |
| `app/auth/dependencies.py` | `get_current_user`, `require_roles` Depends | ✅ 구현 완료 |
| `app/auth/schema.py` | `TokenPayload` Pydantic 모델 | ✅ 구현 완료 |
| `app/common/redis.py` | FastAPI용 Redis 비동기 클라이언트 | ✅ 구현 완료 |
| `app/common/config.py` | 환경변수 설정 | ✅ 구현 완료 |
| `app/agent/agent.py` | pydantic-ai Agent 정의 (Notion, Slack) | 🔶 부분 완료 |
| `app/agent/deps.py` | `DRDeps` 데이터클래스 (WebSocket, Redis, session_id) | ✅ 구현 완료 |
| `app/agent/models.py` | 비어있음 | ❌ 미구현 |
| `app/ws/chat.py` | WebSocket 채팅 엔드포인트 | 🔶 부분 완료 |
| `app/mcp_servers/openstack/mock.py` | OpenStack MCP Mock (VM 조회/생성/복구) | ✅ Mock 완료 |
| `app/knowledge/runbooks/` | 런북 RAG (빈 디렉토리) | ❌ 미구현 |

**구현된 내용:**
- JWT 5단계 검증: iss → aud → exp(±10초 leeway) → jti replay → session 존재
- WebSocket 연결, JWT 인증 후 메시지 루프
- pydantic-ai Slack Agent, Notion Agent 정의
- OpenStack MCP Mock (서버 조회, VM 생성, 복구 실행)

**미구현 / 보완 필요 항목:**
- `ws/chat.py`: `answer_generator` 호출 시 `message_history` 미전달 → 대화 맥락 없음
- `ws/chat.py`: `verify_jwt` 반환값(`TokenPayload`)에서 `user_id`, `project_id` 미활용
- Redis history 연동 없음 (`chat:session:{id}:history` 미사용)
- Human-in-the-loop (파괴적 작업 전 확인) 미구현
- 감사 로그 push (`chat:audit:queue`) 미구현
- 장시간 작업 비동기 처리 (`chat:job:{job_id}`) 미구현
- OpenStack 전용 Agent 미구현 (현재 Slack/Notion만 존재)

---

### horizon/ (Horizon 프론트엔드)

| 파일 | 역할 | 상태 |
|------|------|------|
| `static/dashboard/chat/chat.js` | JWT 갱신(50초) | ✅ 구현 완료 |
| `dashboards/project/overview/templates/overview/usage.html` | 채팅 UI + WebSocket 연결 | ✅ 구현 완료 |

**구현된 내용:**
- 페이지 로드 시 JWT 발급 (`POST /dashboard/ai/session/issue/`)
- 50초마다 JWT 자동 갱신, 탭 포커스 복귀 시 즉시 갱신
- `ws://192.168.88.4:8000/ws/chat?token={aiJwt}`로 WebSocket 연결
- 연결 상태 표시 (connected / disconnected / connecting)
- 메시지 송수신, 마크다운 렌더링, 로딩 애니메이션

**미구현 / 보완 필요 항목:**
- Human-in-the-loop 확인 모달 UI 없음
- 장시간 작업 진행 상태 표시 없음

---

## Redis 키 사용 현황

| 키 패턴 | 명세 | 구현 |
|---------|------|------|
| `chat:session:{session_id}` | 세션 메타데이터 (JSON) | 🔶 세션 전체 데이터 저장 구현 중 |
| `chat:session:{session_id}:history` | 대화 이력 LIST | ❌ 미구현 |
| `chat:jti:{jti}` | Replay 방지 | ✅ 구현 완료 |
| `chat:confirm:{confirm_id}` | 파괴적 작업 확인 상태 | ❌ 미구현 |
| `chat:audit:queue` | 감사 로그 큐 | ❌ 미구현 |
| `chat:job:{job_id}` | 장시간 작업 상태 | ❌ 미구현 |

---

## 다음 구현 우선순위

### Phase 1 — 기본 채팅 동작 완성
1. `ws/chat.py`: `verify_jwt` 반환값에서 `user_id`, `project_id` 추출
2. `ws/chat.py`: WebSocket 연결 중 `message_history` 인메모리 유지
3. `ws/chat.py`: WebSocketDisconnect 시 Redis `chat:session:{id}:history`에 저장
4. `agent.py`: `answer_generator(input, message_history)` 시그니처 변경
5. `chat:session:{session_id}`: `"1"` 대신 유저 메타데이터 JSON으로 교체

### Phase 2 — 안전성·감사
6. Human-in-the-loop: 파괴적 MCP 툴 실행 전 확인 요청 (Redis Pub/Sub)
7. `POST /ai/confirm` Django 엔드포인트 구현
8. 감사 로그 `chat:audit:queue` push + Celery drain

### Phase 3 — OpenStack 연동
9. OpenStack 전용 pydantic-ai Agent 구현 (Mock → 실제 MCP Server)
10. 런북 RAG (`app/knowledge/runbooks/`) 구현
11. `chat:job:{job_id}` 장시간 작업 비동기 처리
