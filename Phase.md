# ZIASTACK DR 복구 자동화 — 개발 Phase 현황

> 기준일: 2026-05-07

---

## 전체 개발 일정 (SRS 기준 12주)

| 주차 | 핵심 목표 | Phase | 상태 |
|------|-----------|-------|------|
| 1주 | 수동 복구 프로세스 분석, 타깃 시나리오 정의 | Phase 1 | ✅ 완료 |
| 2주 | AI 복구 프로세스 설계, 정책 승인 구조 정의 | Phase 1 | ✅ 완료 |
| 3주 | 데이터 모델·정책 정의, 복구 단위 프로퍼티 정의 | Phase 1 | ✅ 완료 |
| 4주 | OpenStack 연결 기초 구현, SDK 검증 | Phase 1 | 🔄 진행 중 |
| 5주 | 정책 수립 로직 구현, AI 정책 추론 프로토타입 | Phase 1 | 🔄 진행 중 |
| 6주 | Tool Calling 템플릿 구성, SDK Wrapper 완성 | Phase 1 | 🔄 진행 중 |
| 7주 | Target VM 자동 생성 구현 | Phase 2 | ⏳ 예정 |
| 8주 | 복구 상태 수집, 실패 로그 저장 | Phase 2 | ⏳ 예정 |
| 9주 | 리포트 자동화, AI 결과 정리 | Phase 2 | ⏳ 예정 |
| 10주 | 장애 분석 RAG 구축, 과거 케이스 벡터화 | Phase 2 | ⏳ 예정 |
| 11주 | 벡터 DB 지식 축적, 정책 지식베이스 자동 갱신 | Phase 2 | ⏳ 예정 |
| 12주 | 통합 테스트 및 시연 준비 | Phase 2 | ⏳ 예정 |

---

## 마일스톤

| 마일스톤 | 목표 주차 | 달성 기준 | 상태 |
|----------|-----------|-----------|------|
| M1: OpenStack 연동 완료 | 4주 차 | Nova VM 조회 및 기본 생성 API 동작 확인 | 🔄 진행 중 |
| M2: AI 기반 복구 정책 생성 | 5~6주 차 | LLM Tool Calling으로 복구 정책 초안 자동 생성 성공 | 🔄 진행 중 |
| M3: End-to-End 복구 자동화 | 7주 차 | 이미지 → Glance 등록 → Nova VM 생성 전 과정 자동 완료 | ⏳ 예정 |
| M4: 모니터링 + 보고서 | 9주 차 | 복구 결과 DB 저장 + Slack 알림 + HTML 보고서 생성 | ⏳ 예정 |
| M5: 최종 통합 검증 | 12주 차 | 전체 시나리오 E2E 테스트 통과 | ⏳ 예정 |

---

## Phase 1 — LangGraph 그래프 로직 + 기반 인프라

> 목표: 복구 흐름의 골격 구현, Horizon 인증·WebSocket 연결, HITL 완성

### 완료 항목 ✅

#### Horizon (Django 플러그인)
- JWT 발급 엔드포인트 (`POST /ai/session/issue/`) — RS256, 60초 유효기간
- 50초마다 JWT 자동 갱신 (탭 포커스 복귀 시 즉시 갱신)
- Redis에 세션 메타데이터 저장 (`chat:session:{session_key}`)
- 채팅 UI + WebSocket 연결 + 히스토리 복원 + confirm 처리

#### FastAPI (agent_server)
- JWT 5단계 검증: `iss → aud → exp(±10초 leeway) → jti replay → session 존재`
- WebSocket 엔드포인트 (`/ws/chat`) — 인증·히스토리 복원·interrupt 처리
- AsyncRedisSaver 체크포인터 (TTL 60분, refresh_on_read)
- LangGraph StateGraph 전체 구조 (8개 노드)

#### LangGraph 노드 (모두 완료)

| 노드 | 역할 | 상태 |
|------|------|------|
| `intent_router` | 사용자 요청 분류 (recover_server / direct_response) | ✅ |
| `get_server_info` | OpenStack Nova에서 서버 상세 조회 | ✅ |
| `generate_policy` | LLM으로 복구 VM 정책 초안 생성 (거절 이유 반영) | ✅ |
| `review_policy` | HITL — interrupt()로 그래프 일시 정지, 운영자 승인/거절 | ✅ |
| `execute_recovery` | create_vm MCP 호출로 복구 VM 생성 | ✅ |
| `generate_report` | state 값 기반 복구 보고서 문자열 조합 | ✅ |
| `response` | direct_response 흐름 — response_agent 위임 | ✅ |
| `error_handler` | 에러·retry 초과 시 메시지 분기 처리 | ✅ |

#### HITL (Human-in-the-Loop)
- `review_policy` 노드: `interrupt({"type": "policy_review", "policy": ..., "server_info": ...})`
- WebSocket 프로토콜:
  - 서버 → 클라이언트: `{"type": "policy_review", "policy": {...}}`
  - 클라이언트 → 서버: `{"type": "confirm_response", "approved": true/false, "reason": "..."}`
- 거절 시 `reject_reason` 반영 후 `generate_policy` 재실행 (최대 3회)
- 3회 초과 시 `error_handler` → `blocked` 상태 전환

#### OpenStack MCP Server (`openstack-mcp-server`)
- `get_server_info`: `conn.compute.find_server()` 실제 SDK 연동 완료
  - 동명 서버 복수 존재 시 후보 목록 반환 (`action: "select_required"`)
  - `asyncio.to_thread`로 동기 SDK 비동기 처리
- `create_vm`: 이미지·네트워크·flavor 검증 후 `conn.compute.create_server()` 호출 완료
- Keystone token 주입 방식: `nodes.py`가 Redis에서 fetch → MCP tool 인자로 전달 (token 마스킹)

#### 상태 관리 (Redis)
- `chat:session:{session_id}` — Keystone 세션 메타데이터
- `chat:jti:{jti}` — replay 방지
- `checkpoint:*` — LangGraph 체크포인트 (AsyncRedisSaver)

### 진행 중 항목 🔄

- OpenStack SDK 연동 검증 (실환경 통합 테스트)
- `server_identifier` 단일 파라미터로 UUID/이름 동시 검색 통합
- `flavor_id` 하드코딩 버그 수정 (`create_vm` compute.py:70 → `flavor.id` 사용 필요)

### 미구현 항목 ❌

- `POST /ai/confirm` Django 엔드포인트 (현재 WebSocket으로 우회 중)
- Celery 감사 로그 파이프라인 (AuditLog 모델, `chat:audit:queue`)
- `execute_recovery` / `get_recovery_status` — ZConverter API 실제 연동
- `find_server` 복수 결과 시 `interrupt()`로 사용자 선택 흐름

---

## Phase 2 — OpenStack SDK 연동 + RAG 플로우

> 목표: 실제 OpenStack 환경에서 복구 파이프라인 E2E 동작, Chroma RAG 연동

### 예정 항목

| 항목 | 내용 | 우선순위 |
|------|------|----------|
| execute_recovery 실제 구현 | ZConverter API 연동, 복구 상태 폴링 | 필수 |
| 복구 이력 DB 저장 | PostgreSQL/MariaDB에 시작·종료시간·결과·VM ID 영구 저장 | 필수 |
| Slack MCP 알림 | 복구 완료/실패 시 지정 채널 자동 발송 | 필수 |
| Chroma RAG 구축 | 런북·과거 복구 이력 벡터화, 정책 생성 시 유사 사례 검색 | 필수 |
| 장시간 작업 비동기 처리 | `chat:job:{job_id}` Redis 키로 진행 상태 관리 | 필수 |
| WebSocket → Stream 전환 | `ainvoke` → `astream`으로 실시간 스트리밍 | 필수 |
| Userdata ZConverter 설치 | cloud-init 스크립트로 VM 내 에이전트 자동 설치 | 필수 |
| Jira MCP 연동 | 복구 태스크 기반 이슈 자동 생성·상태 갱신 | 권장 |

---

## Phase 3 — ZConverter 에이전트 연동

> 목표: 생성된 Target VM 내부에 ZConverter 에이전트 설치 후 복구 작업 자동 진행

- Userdata 방식 ZConverter Cloud AI 에이전트 설치 확인
- 에이전트 등록 완료 후 세부 복구 동작 연동 (세부 스펙 TBD)
- VM 내부 복구 상태를 FastAPI로 폴링·스트리밍

---

## Phase 4 — 플로우 고도화

> 목표: 각 단계별 SDK 로직 보완, 스트리밍 전환, Redis 키 체계 정비

- 각 OpenStack SDK 호출 고도화 (필요 데이터 보완, 에러 처리 강화)
- `invoke` → `stream` 전환으로 실시간 응답 구현
- Redis 키 체계 정리 및 TTL 정책 확정
- LLM 모델 교체 검토 (`qwen2.5:14b` 이상) — 컨텍스트 누적 시 tool calling 불안정 이슈
- Docker volume 마운트로 체크포인트 영속성 확보

---

## Phase 5 — 안전성 + 감사

> 목표: 운영 환경 수준의 보안·감사 체계 구축

- 감사 로그 `chat:audit:queue` push + Celery drain 구현
- `POST /ai/confirm` Django 엔드포인트 완성
- 상황별 agent graph 추가 (부분 복구, 롤백, 멀티 VM 등)
- 코드 커버리지 70% 이상 단위 테스트

---

## Phase 6 — 고도화 (TBD)

- Kafka 전환 (Redis Stream → Kafka Execute Phase 이벤트)
- Chroma 지식 자동 누적 파이프라인 (복구 성공·실패 사례 자동 벡터화)
- 복구 정책 규칙 API 기반 관리 (관리자 UI 없이 CRUD)
- Terraform 기반 OpenStack 리소스 프로비저닝 템플릿

---

## 컴포넌트별 현재 구현 상태 요약

| 컴포넌트 | 항목 | 상태 |
|----------|------|------|
| Horizon | JWT 발급·갱신 | ✅ 완료 |
| Horizon | WebSocket 연결·채팅 UI | ✅ 완료 |
| Horizon | HITL confirm UI | ✅ 완료 |
| Horizon | `POST /ai/confirm` 엔드포인트 | ❌ 미구현 |
| FastAPI | JWT 검증 (5단계) | ✅ 완료 |
| FastAPI | WebSocket 채팅·HITL 처리 | ✅ 완료 |
| FastAPI | Redis 세션·체크포인트 | ✅ 완료 |
| LangGraph | 전체 그래프 (8노드) | ✅ 완료 |
| LangGraph | HITL (interrupt/resume) | ✅ 완료 |
| LangGraph | 스트리밍 응답 | ❌ 미구현 |
| MCP | get_server_info (실제 SDK) | ✅ 완료 |
| MCP | create_vm (실제 SDK) | ✅ 완료 |
| MCP | execute_recovery | ❌ Mock |
| MCP | get_recovery_status | ❌ Mock |
| RAG | Chroma 런북 인제스트 | ❌ 미구현 |
| RAG | 유사 복구 사례 검색 | ❌ 미구현 |
| 보고서 | 기본 문자열 보고서 | ✅ 완료 |
| 보고서 | Slack 알림 | ❌ 미구현 |
| 보고서 | Jira 티켓 자동 생성 | ❌ 미구현 |
| DB | 복구 이력 영구 저장 | ❌ 미구현 |
| 감사 | 감사 로그 파이프라인 | ❌ 미구현 |

---

## 당장 다음 작업 (우선순위 순)

1. `create_vm` `flavor_id` 하드코딩 버그 수정 (`compute.py:70`)
2. OpenStack SDK 실환경 통합 테스트 (get_server_info, create_vm)
3. `execute_recovery` ZConverter API 연동 방식 확정
4. 복구 이력 DB 스키마 설계 및 저장 구현
5. Slack MCP 복구 완료 알림 연동