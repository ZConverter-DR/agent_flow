# 감사 로그 — FastAPI → Django


# 감사로그 -> ai가 동작한 과정 및 결과를 추적하기 위함 -> fast api에서 수행한 결과를 장고 db에 전달하기 위함

fastapi
1. audit log 데이터 생성
2. 민감 정보 마스킹
3. 레디스 큐 삽입
 
## 개요

FastAPI가 MCP 도구를 실행한 후 감사 로그를 **Redis 큐**에 push 한다.
Django Celery beat가 10초마다 큐를 drain 해서 `AuditLog` 테이블에 저장한다.

> **설계 결정:** HTTP 웹훅(HMAC) 대신 Redis 큐를 쓰는 이유:
> - FastAPI가 Django URL을 직접 호출할 필요 없음 → 장고와 fast api 의존성 분리
> - FastAPI 실패해도 Redis에 쌓여 있음 → 유실 방지
> - 비동기 → LLM 응답 속도에 영향 없음

## 흐름

```
[1] FastAPI: MCP 도구 실행
[2] FastAPI: LPUSH chat:audit:queue '<감사 JSON>' -> redis에 삽입
[3] FastAPI: LLM 응답 계속 스트리밍 (감사 기록과 무관)
[4] Django Celery beat (10초 주기): RPOP → AuditLog 테이블 저장 -> 장고(마리아db) 전달
```

## 페이로드 형식

FastAPI가 Redis 큐에 push 하는 JSON:

```json
{
  "session_id": "7e3a1f2b4c5d6e7f8a9b0c1d2e3f4a5b",
  "user_id": "a3f2b1c0d4e5f6a7b8c9d0e1f2a3b4c5",
  "username": "testuser",
  "project_id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
  "tool_name": "list_instances",
  "tool_args": {"status": "ACTIVE"},
  "status": "success",
  "result_summary": "ACTIVE 상태 인스턴스 3개 반환",
  "keystone_token_hash": "<sha256 hex of keystone token>",
  "duration_ms": 342,
  "audit_priority": "low",
  "timestamp": "2026-04-17T10:05:30Z"
}
```

## 필드 정의

| 필드                  | 타입   | 필수 | 설명                                           |
|-----------------------|--------|------|------------------------------------------------|
| `session_id`          | string | ✅   | Redis 세션 키                                  |
| `user_id`             | string | ✅   | Keystone 사용자 ID (JWT `sub`)                 |
| `username`            | string | ✅   | 사용자 이름                                    |
| `project_id`          | string | ✅   | Keystone 프로젝트 ID                           |
| `tool_name`           | string | ✅   | MCP 도구 이름                                  |
| `tool_args`           | object | ✅   | 도구 실행 인자 (민감 정보 마스킹 후)           |
| `status`              | string | ✅   | `success` \| `failure` \| `cancelled`          |
| `result_summary`      | string | ✅   | 성공 시 최대 500자, 실패 시 최대 2000자        |
| `keystone_token_hash` | string | ✅   | `sha256(keystone_token)` — 원문 저장 절대 금지 |
| `duration_ms`         | int    | ✅   | 도구 실행 소요 시간                            |
| `audit_priority`      | string | ✅   | `low` \| `medium` \| `high` (도구 메타데이터 참조) |
| `timestamp`           | string | ✅   | ISO8601 UTC (도구 호출 완료 시각)              |

## 민감 정보 마스킹

`tool_args`에서 아래 키는 FastAPI가 **push 전에 자동 마스킹** 한다:

- `password`, `passwd`, `secret`, `token`, `api_key`, `private_key` 등
- 값은 `"***MASKED***"` 로 치환

Django도 저장 직전에 **재검증**한다 (이중 방어).

----------------------------->
아래는 장고 참고용 장고로직입니다.

## Django AuditLog 모델

```python
class AuditLog(models.Model):
    session_id = models.CharField(max_length=64, db_index=True)
    user_id = models.CharField(max_length=64, db_index=True)
    username = models.CharField(max_length=128)
    project_id = models.CharField(max_length=64, db_index=True)
    tool_name = models.CharField(max_length=128, db_index=True)
    tool_args = models.JSONField()
    status = models.CharField(max_length=16, db_index=True)
    result_summary = models.TextField()
    keystone_token_hash = models.CharField(max_length=64)
    duration_ms = models.IntegerField()
    audit_priority = models.CharField(max_length=8, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['tool_name', 'timestamp']),
        ]
```

## 보존 기간 (audit_priority 기준)

| priority | 보존 기간 | 해당 도구 예시                              |
|----------|-----------|---------------------------------------------|
| `high`   | 1년       | delete_*, terminate_*, 인스턴스 생성        |
| `medium` | 90일      | 볼륨 연결/해제, 보안그룹 변경               |
| `low`    | 30일      | 목록 조회, 상태 확인                        |

Django 주간 배치 작업으로 오래된 로그 삭제.

## 실패 처리

### FastAPI 측
- Redis LPUSH 실패 시: 로컬 로그(`logger.error`)에 기록 후 LLM 응답 계속
- **감사 기록 실패가 사용자 요청을 막지 않음**

### Django 측
- JSON 파싱 실패, DB 저장 실패: `chat:audit:deadletter` 큐로 이동
- 운영자가 주기적으로 dead letter 확인

## Celery 태스크 예시

```python
# horizon/ai_chat/tasks.py
from celery import shared_task
from celery.schedules import crontab
import redis, json

r = redis.Redis.from_url(settings.REDIS_URL)

@shared_task
def drain_audit_queue(batch_size=100):
    saved = 0
    for _ in range(batch_size):
        raw = r.rpop("chat:audit:queue")
        if not raw:
            break
        try:
            data = json.loads(raw)
            AuditLog.objects.create(
                session_id=data["session_id"],
                user_id=data["user_id"],
                username=data["username"],
                project_id=data["project_id"],
                tool_name=data["tool_name"],
                tool_args=mask_sensitive(data["tool_args"]),
                status=data["status"],
                result_summary=data["result_summary"][:2000],
                keystone_token_hash=data["keystone_token_hash"],
                duration_ms=data["duration_ms"],
                audit_priority=data["audit_priority"],
                timestamp=data["timestamp"],
            )
            saved += 1
        except Exception as e:
            r.lpush("chat:audit:deadletter", raw)
            logger.error(f"Audit log save failed: {e}")
    return saved

# celery beat schedule
CELERY_BEAT_SCHEDULE = {
    'drain-audit-queue': {
        'task': 'horizon.ai_chat.tasks.drain_audit_queue',
        'schedule': 10.0,  # 10초마다
    },
}
```

## Horizon Admin 뷰

Django Admin에 `AuditLog` 모델을 등록. 필터 필수:
- 사용자별
- 프로젝트별
- 도구별
- 상태별 (success/failure/cancelled)
- 우선순위별
- 기간별

## 운영자 쿼리 예시

```python
# 최근 1시간 동안 실패한 파괴적 작업
AuditLog.objects.filter(
    timestamp__gte=now() - timedelta(hours=1),
    status='failure',
    audit_priority='high',
).select_related()

# 특정 사용자의 오늘 활동
AuditLog.objects.filter(
    user_id='...',
    timestamp__date=today(),
).order_by('-timestamp')
```