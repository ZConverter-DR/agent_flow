# Redis 스키마

## 개요

Django와 FastAPI가 **공유하는 Redis 인스턴스**의 키 레이아웃.
모든 키는 `chat:` prefix 를 사용한다.

## 키 목록 요약

| 키 패턴                            | 타입     | TTL   | 용도                  |
|------------------------------------|----------|-------|-----------------------|
| `chat:session:{session_id}`        | String   | 3600s | 세션 메타데이터 (JSON) |
| `chat:session:{session_id}:history`| List     | 3600s | 대화 이력 (append)    |
| `chat:confirm:{confirm_id}`        | String   | 300s  | 파괴적 작업 확인 상태 |
| `chat:jti:{jti}`                   | String   | 120s  | JWT replay 방지       |
| `chat:audit:queue`                 | List     | -     | 감사 로그 큐          |
| `chat:job:{job_id}`                | String   | 3600s | 장시간 작업 상태 (JSON)|
| `chat:confirm:events`              | Pub/Sub  | -     | confirm 상태 변경 알림|
| `chat:job:events`                  | Pub/Sub  | -     | job 상태 변경 알림    |

---

## `chat:session:{session_id}` — 세션 메타데이터 (장고 세션)

| 항목 | 값                                                      |
|------|---------------------------------------------------------|
| 타입 | String (JSON)                                           |
| TTL  | 3600초 (1시간)                                          |
| 쓰기 | Django (생성), FastAPI (`last_activity` 갱신만)         |
| 읽기 | FastAPI                                                 |

**Value (JSON):**

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

**필드 규칙:**

| 필드                      | 작성자  | 변경 가능 | 설명                                     |
|---------------------------|---------|-----------|------------------------------------------|
| `user_id`                 | Django  | ❌        | 생성 시 고정                             |
| `username`                | Django  | ❌        | 생성 시 고정                             |
| `project_id`              | Django  | ❌        | 생성 시 고정                             |
| `roles`                   | Django  | ❌        | 생성 시 고정 (갱신은 신규 세션 발급으로) |
| `keystone_token`          | Django  | ❌        | 평문 보관. FastAPI가 직접 꺼내어 사용 (추후 암호화 고려)    |
| `created_at`              | Django  | ❌        | 생성 시 고정                             |
| `last_activity`           | FastAPI | ✅        | 메시지 수신마다 갱신                     |


---

## `chat:session:{session_id}:history` — 대화 이력 -> 추후 db 또는 브라우저 등으로 전환 고려

| 항목 | 값                                              |
|------|-------------------------------------------------|
| 타입 | List (Redis LIST)                               |
| TTL  | 3600초 (세션과 동일)                            |
| 쓰기 | FastAPI (`RPUSH`로 append, `LTRIM`으로 크기 관리)|
| 읽기 | FastAPI (`LRANGE`)                              |

**왜 별도 키인가?**
메타데이터와 history를 하나의 JSON으로 묶으면 동시 쓰기 시 경쟁 조건 발생.
Redis LIST의 `RPUSH`는 원자적이므로 여러 요청이 동시에 와도 안전.

**쓰기:**
```
RPUSH chat:session:{id}:history '{"role":"user","content":"..."}'
LTRIM chat:session:{id}:history -50 -1   # 최근 50개만 유지
EXPIRE chat:session:{id}:history 3600    # TTL 갱신
```

**읽기:**
```
LRANGE chat:session:{id}:history 0 -1
```

**각 아이템 형식:**
```json
{"role": "user", "content": "인스턴스 목록 보여줘", "ts": "2026-04-17T10:05:00Z"}
{"role": "assistant", "content": "현재 3개 실행 중입니다.", "ts": "2026-04-17T10:05:02Z"}
```

---

## `chat:confirm:{confirm_id}` — 중요 작업 확인 상태

| 항목 | 값                                        |
|------|-------------------------------------------|
| 타입 | String                                    |
| TTL  | 300초 (5분)                               |
| 쓰기 | FastAPI (`pending` 생성), Django (`approved`/`rejected`) |
| 읽기 | FastAPI (Pub/Sub 수신 후 확인)            |

**Value:** `"pending"` | `"approved"` | `"rejected"`

**흐름 (Pub/Sub 사용):**

```
[1] FastAPI: SETEX chat:confirm:{id} 300 "pending"
             SUBSCRIBE chat:confirm:events
             UI에 confirm_required SSE 이벤트 전송

[2] UI: 사용자가 "확인" 버튼 클릭
        POST /ai/confirm { confirm_id: ... }

[3] Django: SET chat:confirm:{id} "approved"
            PUBLISH chat:confirm:events "{confirm_id}:approved"

[4] FastAPI: 이벤트 수신 → GET chat:confirm:{id} 로 상태 확인
             "approved" → MCP 도구 실행 계속
             "rejected" / 타임아웃(300s) → cancelled 처리
```

**주의:** Pub/Sub 구독은 요청당 1회만. 장기 구독 금지 (메모리 누수).

---

## `chat:jti:{jti}` — JWT replay 방지

| 항목 | 값       |
|------|----------|
| 타입 | String   |
| TTL  | 120초    |
| 쓰기 | FastAPI  |
| 읽기 | FastAPI  |

**Value:** `"1"` (존재 여부만 확인)

FastAPI가 JWT 검증 성공 직후 저장. 이미 존재하면 replay 공격으로 간주하고 거부.

```
SET chat:jti:{jti} "1" NX EX 120
# NX: 키가 없을 때만 저장 → 이미 있으면 False 반환 → replay로 간주
```

---

## `chat:audit:queue` — 감사 로그 큐

| 항목 | 값                                 |
|------|-----------------------------------|
| 타입 | List                               |
| TTL  | 없음 (Django Celery가 주기적으로 drain) |
| 쓰기 | FastAPI (`LPUSH`)                 |
| 읽기 | Django Celery beat (`RPOP`)       |

**FastAPI가 MCP 도구 호출 후 즉시 push:**
```
LPUSH chat:audit:queue '<감사 로그 JSON>'
```

**Django Celery beat가 10초마다 drain:**
```python
while (item := redis.rpop("chat:audit:queue")):
    AuditLog.objects.create(**json.loads(item))
```

페이로드 상세 구조는 `audit_log.md` 참조.

**재시도 정책:** Celery task 실패 시 최대 3회 재시도 (지수 백오프).
3회 실패해도 큐에서는 이미 pop됐으므로, 실패한 JSON은 별도 `chat:audit:deadletter` 리스트에 저장.

---

## `chat:job:{job_id}` — 장시간 작업 상태(인스턴스 생성과 같은 작업)

| 항목 | 값                                 |
|------|-----------------------------------|
| 타입 | String (JSON)                      |
| TTL  | 3600초                             |
| 쓰기 | FastAPI                            |
| 읽기 | FastAPI (`/v1/jobs/{id}` 요청 시)  |

**Value (JSON):**
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

**상태 전이:** `pending` → `running` → `success` | `failure` | `cancelled`

상태 변경 시 `chat:job:events` 채널에 PUBLISH.

---

## 동시성 주의사항

**세션 메타데이터 쓰기:** Django만 전체 JSON을 쓴다. FastAPI는 `last_activity`만
별도 키(`chat:session:{id}:last_activity`)로 분리하거나, 읽기 전용으로 사용.

> Phase 1에서는 `last_activity` 갱신을 생략해도 무방 (접속 통계용).

**history 쓰기:** 항상 `RPUSH` 사용. `GET → MODIFY → SET` 금지.

**Pub/Sub 누락 방지:** 네트워크 불안정 시 메시지 유실 가능.
따라서 Pub/Sub 수신 후에도 반드시 `GET`으로 실제 상태를 재확인.