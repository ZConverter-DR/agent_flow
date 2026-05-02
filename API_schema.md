# API Specification: ZIASTACK DR Recovery Automation

## 1. 문서 목적

이 문서는 ZIASTACK DR 복구 자동화 프로젝트에서 사용하는 API 인터페이스를 사람이 빠르게 이해할 수 있도록 정리한 사양서다.

- 현재 구현된 FastAPI 엔드포인트
- WebSocket 채팅 인터페이스
- 인증용 JWT 규칙
- Redis 기반 세션/작업 상태 구조
- AI Agent가 호출하는 OpenStack MCP Tool 스키마
- 설계상 예정된 보조 API

구현 상태가 섞여 혼동되지 않도록 각 항목에 `현재 구현` 또는 `설계 예정`을 명시한다.

---

## 2. 시스템 경계

이 프로젝트의 요청 흐름은 아래와 같다.

`Horizon/Django UI -> FastAPI AI Gateway -> AI Supervisor -> MCP Tools -> OpenStack / ZConverter Agent`

역할 구분:

- Django/Horizon: 사용자 세션 발급, UI 렌더링, 승인 처리
- FastAPI: JWT 검증, WebSocket 채팅, AI 오케스트레이션 진입점
- MCP Tools: OpenStack 조회/생성/복구 실행 도구
- Redis: 세션, 승인 상태, 작업 상태, 감사 로그 큐 저장

---

## 3. 인증 방식

### 3.1 인증 개요

- 발급자: Django
- 소비자: FastAPI
- 방식: JWT
- 기본 사용 위치
  - HTTP: `Authorization: Bearer <token>`
  - WebSocket: Query Parameter `?token=<jwt>`

### 3.2 JWT Claim

| Claim | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `iss` | string | Y | 고정값 `horizon-django` |
| `aud` | string | Y | 고정값 `ai-gateway` |
| `sub` | string | Y | Keystone 사용자 ID |
| `session_id` | string | Y | Redis 세션 식별자 |
| `project_id` | string | Y | Keystone 프로젝트 ID |
| `username` | string | Y | 사용자명 |
| `roles` | list[string] | Y | 사용자 역할 목록 |
| `scope` | string | Y | 현재 `chat` |
| `iat` | int | Y | 발급 시각 |
| `exp` | int | Y | 만료 시각 |
| `jti` | string | Y | replay 방지용 nonce |

### 3.3 검증 규칙

FastAPI는 JWT 수신 시 아래를 검증한다.

1. `iss == "horizon-django"`
2. `aud == "ai-gateway"`
3. 만료 시간 검증 (`exp`, clock skew 허용)
4. `jti` 중복 사용 여부 확인
5. `session_id`에 대응하는 Redis 세션 존재 여부 확인

### 3.4 인증 실패 응답

| 상황 | 상태/코드 |
|---|---|
| 만료된 토큰 | HTTP `401` / WebSocket close `1008` |
| 잘못된 audience | HTTP `401` / WebSocket close `1008` |
| 서명 검증 실패 | HTTP `401` / WebSocket close `1008` |
| 세션 없음 또는 만료 | HTTP `403` / WebSocket close `1008` |
| 이미 사용된 토큰(replay) | HTTP `409` / WebSocket close `1008` |

---

## 4. 공통 규칙

### 4.1 콘텐츠 형식

- HTTP 요청/응답: `application/json`
- WebSocket 메시지: plain text

### 4.2 시간 형식

- 기본 형식: ISO 8601 UTC
- 예: `2026-04-17T10:05:00Z`

### 4.3 상태 값 표기

복구 워크플로우 상위 상태:

- `pending`
- `planning`
- `confirming`
- `executing`
- `completed`
- `failed`
- `blocked`
- `cancelled`

복구 Job 내부 상태:

- `PENDING`
- `RUNNING`
- `SUCCESS`
- `FAILURE`

---

## 5. FastAPI External API

### 5.1 `POST /ai/chat`

- 상태: `현재 구현`
- 목적: JWT 인증이 정상 동작하는지 확인하는 간단한 HTTP 엔드포인트

### 요청 헤더

```http
Authorization: Bearer <jwt>
```

### 요청 본문

없음

### 성공 응답

```json
{
  "message": "testuser님 안녕하세요.",
  "project": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"
}
```

### 비고

- 현재는 실제 채팅 요청을 처리하지 않는다.
- 인증된 사용자 컨텍스트를 반환하는 확인용 엔드포인트에 가깝다.

---

### 5.2 `GET /ws/chat?token=<jwt>`

- 상태: `현재 구현`
- 목적: 사용자 채팅 메시지를 받아 AI Supervisor를 실행하고 응답을 반환

### 연결 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---:|---|
| `token` | query | string | Y | Django가 발급한 AI JWT |

### 처리 순서

1. WebSocket handshake 수락
2. JWT 검증
3. Redis 세션 확인
4. 메시지 수신 루프 진입
5. 사용자 메시지를 AI Supervisor에 전달
6. 결과를 문자열로 변환해 WebSocket으로 전송

### 클라이언트 -> 서버 메시지

현재 구현은 텍스트 프레임 하나를 사용자 발화로 취급한다.

예시:

```text
52 vm을 복구해줘
```

### 서버 -> 클라이언트 메시지

현재 구현은 구조화 JSON이 아니라 최종 문자열을 그대로 전송한다.

예시:

```text
대상 서버 상태를 확인한 뒤 복구 절차를 진행하겠습니다.
```

### 에러 처리

| 상황 | 동작 |
|---|---|
| JWT 검증 실패 | close `1008` |
| 서버 내부 오류 | close `1011` |
| 클라이언트 정상 종료 | disconnect 처리 |

### 제약 사항

- 현재는 스트리밍 chunk 포맷이 정의되어 있지 않다.
- 현재는 대화 이력 저장 코드가 주석 처리되어 있다.
- 현재는 메시지 요청/응답이 구조화된 envelope 없이 plain text 기반이다.

---

## 6. 설계 예정 API

아래 항목은 주변 문서에 존재하지만 현재 FastAPI 코드에는 아직 구현되지 않은 보조 API다.

### 6.1 `POST /ai/session/issue`

- 상태: `설계 예정`
- 구현 주체: Django
- 목적: FastAPI 접속용 JWT 발급

### 성공 응답 예시

```json
{
  "token": "<jwt>",
  "expires_in": 60,
  "session_id": "7e3a1f2b4c5d6e7f8a9b0c1d2e3f4a5b"
}
```

---

### 6.2 `POST /ai/confirm`

- 상태: `설계 예정`
- 구현 주체: Django
- 목적: 파괴적 작업 승인/거절 처리

### 요청 본문 예시

```json
{
  "confirm_id": "cfm_12345",
  "decision": "approved"
}
```

### 허용값

- `approved`
- `rejected`

### 동작

- Redis `chat:confirm:{confirm_id}` 값을 변경
- `chat:confirm:events` 채널로 Pub/Sub 이벤트 발행

---

### 6.3 `GET /v1/jobs/{job_id}`

- 상태: `설계 예정`
- 구현 주체: FastAPI
- 목적: 장시간 작업 상태 조회

### 성공 응답 예시

```json
{
  "job_id": "abc123",
  "session_id": "7e3a1f2b...",
  "tool_name": "create_instance",
  "status": "running",
  "progress": 0.4,
  "started_at": "2026-04-17T10:05:00Z",
  "finished_at": null,
  "result_summary": null
}
```

---

## 7. AI Agent Tool API

이 섹션은 사용자가 직접 호출하는 REST API가 아니라, FastAPI 내부 AI Supervisor가 호출하는 MCP Tool 계약이다.

### 7.1 `get_server_info`

- 상태: `현재 구현`
- 목적: 특정 OpenStack VM의 상태와 기본 정보를 조회
- 선행 조건: 없음

### 입력 스키마

```json
{
  "type": "object",
  "properties": {
    "server_id": {
      "type": "string",
      "description": "The OpenStack instance UUID"
    }
  },
  "required": ["server_id"]
}
```

### 성공 응답 예시

```json
{
  "id": "a1b2c3d4-0002",
  "name": "db-server-01",
  "status": "ERROR",
  "flavor": "m1.large",
  "ip_addresses": {
    "default": [
      {
        "addr": "192.168.1.11"
      }
    ]
  },
  "created": "2025-03-15T12:00:00Z"
}
```

### 실패 응답 예시

```json
{
  "error": "Server a1b2c3d4-9999 not found"
}
```

---

### 7.2 `create_vm`

- 상태: `현재 구현`
- 목적: ZConverter AI Agent가 탑재될 신규 VM 생성
- 주의: 실제 인프라 비용이 발생하는 파괴적 작업으로 간주

### 입력 스키마

```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string" },
    "flavor": { "type": "string" },
    "image_id": { "type": "string" },
    "network_id": { "type": "string" }
  },
  "required": ["name", "flavor", "image_id", "network_id"]
}
```

### 성공 응답 예시

```json
{
  "id": "7d3e7f42-5b98-4f2b-a9db-75d8938d61f7",
  "name": "recovery-target-01",
  "status": "BUILD",
  "flavor": "m1.large",
  "image_id": "img-123",
  "network_id": "net-456",
  "created": "2026-04-28T12:00:00Z",
  "note": "ZConverter AI Agent will be installed via cloud-init on first boot"
}
```

---

### 7.3 `execute_recovery`

- 상태: `현재 구현`
- 목적: 특정 VM에 대해 복구 작업 실행
- 선행 조건: `get_server_info`로 상태 확인 후 호출 권장

### 입력 스키마

```json
{
  "type": "object",
  "properties": {
    "server_id": {
      "type": "string"
    },
    "recovery_type": {
      "type": "string",
      "enum": ["reboot", "rebuild", "migrate", "evacuate"]
    },
    "reason": {
      "type": "string"
    }
  },
  "required": ["server_id", "recovery_type", "reason"]
}
```

### 성공 응답 예시

```json
{
  "job_id": "7f302fe2-1174-4b8e-b443-3ab798739b69",
  "status": "PENDING"
}
```

### 실패 응답 예시

```json
{
  "error": "Server a1b2c3d4-9999 not found"
}
```

---

### 7.4 `get_recovery_status`

- 상태: `현재 구현`
- 목적: 복구 Job 진행 상태 조회

### 입력 스키마

```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string"
    }
  },
  "required": ["job_id"]
}
```

### 성공 응답 예시

```json
{
  "job_id": "7f302fe2-1174-4b8e-b443-3ab798739b69",
  "server_id": "a1b2c3d4-0002",
  "recovery_type": "reboot",
  "status": "RUNNING",
  "progress": 70,
  "logs": [
    "Recovery job created: reboot on a1b2c3d4-0002",
    "Agent received recovery request",
    "Progress: 70%"
  ]
}
```

### 실패 응답 예시

```json
{
  "error": "Job unknown-job-id not found"
}
```

---

## 8. Redis Data Contract

Redis는 API 그 자체는 아니지만, Django/FastAPI 간 계약이므로 함께 명세한다.

### 8.1 키 요약

| 키 패턴 | 타입 | TTL | 설명 |
|---|---|---:|---|
| `chat:session:{session_id}` | String | 3600s | 세션 메타데이터 |
| `chat:session:{session_id}:history` | List | 3600s | 대화 이력 |
| `chat:confirm:{confirm_id}` | String | 300s | 승인 상태 |
| `chat:jti:{jti}` | String | 120s | JWT replay 방지 |
| `chat:audit:queue` | List | 없음 | 감사 로그 적재 |
| `chat:job:{job_id}` | String | 3600s | 장시간 작업 상태 |
| `chat:confirm:events` | Pub/Sub | 없음 | 승인 상태 변경 이벤트 |
| `chat:job:events` | Pub/Sub | 없음 | Job 상태 이벤트 |

### 8.2 `chat:session:{session_id}`

### 값 예시

```json
{
  "user_id": "a3f2b1c0d4e5f6a7b8c9d0e1f2a3b4c5",
  "username": "testuser",
  "project_id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
  "roles": ["member"],
  "keystone_token": "<plaintext_token>",
  "created_at": "2026-04-17T10:00:00Z",
  "last_activity": "2026-04-17T10:05:00Z"
}
```

### 8.3 `chat:confirm:{confirm_id}`

허용 상태:

- `pending`
- `approved`
- `rejected`

### 8.4 `chat:job:{job_id}`

### 값 예시

```json
{
  "job_id": "abc123",
  "session_id": "7e3a1f2b...",
  "tool_name": "create_instance",
  "status": "running",
  "progress": 0.4,
  "started_at": "2026-04-17T10:05:00Z",
  "finished_at": null,
  "result_summary": null
}
```

---

## 9. 오류 응답 원칙

### 9.1 HTTP API

현재 구현 기준:

- 인증 실패: `401`
- 권한/세션 문제: `403`
- replay 감지: `409`

향후 권장 형식:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "유효하지 않은 토큰입니다."
  }
}
```

### 9.2 MCP Tool

현재 구현 기준으로는 예외 대신 아래와 같은 오류 객체를 반환한다.

```json
{
  "error": "Server a1b2c3d4-9999 not found"
}
```

향후에는 다음 원칙으로 정리하는 것이 바람직하다.

- 성공과 실패 응답 구조를 분리
- `error_code` 추가
- 사용자 표시 메시지와 내부 로그 메시지 분리

---

## 10. 권장 문서 사용법

이 문서를 볼 때는 아래 기준으로 읽으면 된다.

- 실제 연결 방식이 궁금하면: `5. FastAPI External API`
- 인증 토큰 구조가 궁금하면: `3. 인증 방식`
- AI가 어떤 도구를 호출하는지 궁금하면: `7. AI Agent Tool API`
- 세션/작업 상태 저장 규칙이 궁금하면: `8. Redis Data Contract`
- 아직 코드에 없는 예정 API를 확인하려면: `6. 설계 예정 API`

---

## 11. 구현 상태 요약

### 현재 구현

- `POST /ai/chat`
- `GET /ws/chat?token=<jwt>`
- JWT 검증 및 replay 방지
- MCP Tool 4종
  - `get_server_info`
  - `create_vm`
  - `execute_recovery`
  - `get_recovery_status`

### 아직 미구현

- 승인 처리 API
- Job 조회 API
- 구조화된 WebSocket 이벤트 포맷
- 대화 이력 저장
- 실제 OpenStack 및 ZConverter Agent 연동의 완전한 운영 버전
