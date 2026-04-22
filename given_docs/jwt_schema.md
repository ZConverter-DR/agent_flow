# JWT 스키마 — Django → FastAPI

jwt를 이용해서 장고 시스템 검증(Keystone 직접 의존도 제거)
- fastapi
1. jwt 수신 (post 헤더)
2. jwt 검증
3. jti replay 방지 처리

- django
1. /ai/session/issue (jwt 발급)
2. jwt payload 생성
3. 서명 수행 (로그인 유저 기반)


## 개요

Django `/ai/session/issue` 가 발급하고, FastAPI가 `Authorization: Bearer <token>`
헤더로 수신해 검증한다. 유효기간은 **60초**. UI가 50초마다 재발급
 -> 검증용으로 60초로 잡았으나 필요 시 조정
## Claims

| Claim        | 타입         | 필수 | 설명                                           |
|--------------|--------------|------|------------------------------------------------|
| `iss`        | string       | ✅   | `"horizon-django"` (고정)                      |
| `aud`        | string       | ✅   | `"ai-gateway"` (고정)                          |
| `sub`        | string       | ✅   | Keystone 사용자 ID                             |
| `session_id` | string       | ✅   | Redis 세션 키 (`chat:session:{id}`)            |
| `project_id` | string       | ✅   | Keystone 프로젝트 ID                           |
| `username`   | string       | ✅   | 사용자 이름 (로그용)                           |
| `roles`      | list[string] | ✅   | Keystone 역할 목록 (예: `["member"]`)          |
| `scope`      | string       | ✅   | `"chat"` (향후 확장 대비)                      |
| `iat`        | int          | ✅   | 발급 시각 (Unix timestamp)                     |
| `exp`        | int          | ✅   | 만료 시각 — 발급 후 **60초**                   |
| `jti`        | string       | ✅   | 중복 사용 방지 nonce (uuid4)                   |

project-scoped token의 데이터를 가져오면 되는건가?

## 예시 페이로드

```json
{
  "iss": "horizon-django",
  "aud": "ai-gateway",
  "sub": "a3f2b1c0d4e5f6a7b8c9d0e1f2a3b4c5",
  "session_id": "7e3a1f2b4c5d6e7f8a9b0c1d2e3f4a5b",
  "project_id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
  "username": "testuser",
  "roles": ["member", "_member_"],
  "scope": "chat",
  "iat": 1745000000,
  "exp": 1745000060,
  "jti": "f1e2d3c4-b5a6-7890-abcd-ef1234567890"
}
```

## 서명 알고리즘

| 단계 | 알고리즘 | 비고                                         |
|------|----------|----------------------------------------------|
| PoC  | HS256    | 공개키 (환경변수 `AI_JWT_SECRET`)(장고,fastapi 모두 사전에 키를 알고 있음)       |
| 운영 | RS256    | Django: private key / FastAPI: public key만 |

/var/lib/horizon/keys에  private key 저장

## FastAPI 검증 규칙

1. `iss == "horizon-django"` 확인
2. `aud == "ai-gateway"` 확인
3. `exp > now` 만료 확인 (clock skew ±10초 허용)
4. `jti` Redis에서 중복 확인 (replay 방지, `chat:jti:{jti}` 키 존재 시 거부)
5. `session_id` Redis에서 세션 존재 확인 → 없으면 403
6. `required_roles` 검증 (MCP 도구별) — `roles` 중 하나라도 포함 시 통과

## jti Redis TTL

JWT replay 방지용. 검증 성공 시 즉시 Redis에 기록.

```
SETEX chat:jti:{jti} 120 "1"
```
-> jwt 중복 발급 방지
**TTL 120초 고정 이유**: JWT 만료(60초) + clock skew 버퍼(60초).
이보다 짧으면 시계 오차로 만료 전 재사용 가능.

## UI 갱신 주기

- JWT 유효기간: 60초
- UI는 **50초마다** `/ai/session/issue` 재호출해서 갱신
- SSE or Websocket 스트림 진행 중 JWT가 만료되어도 **진행 중인 요청은 유지**
  (FastAPI는 요청 시작 시점에만 JWT 검증)

## 보안 주의사항

- JWT는 **in-memory 변수**로만 보관. `localStorage` 저장 금지 (XSS 취약)
- CORS는 Horizon 도메인만 허용. `*` 금지
- HTTPS 운영 필수. HTTP는 로컬 개발만

---

login()은 user_logged_in 시그널이 발생하지만, 프로젝트를 변경하는 switch()의 경우 시그널이 없어서 @receiver로 잡아낼 수 없기 때문에 별도의 미들웨어를 생성

JWT 확인: 개발자도구 -> application -> cookies 확인