## 프로젝트 개요
ZIASTACK(OpenStack 기반) 환경에서 ZConverter 백업 이미지 기반 VM 자동 생성 및 복구를 수행하는 LLM 에이전트 시스템.

## 기술 스택
- LangGraph StateGraph (Supervisor 패턴 X, 그래프가 라우팅 담당)
- LLM: qwen2.5:7b (Ollama, http://10.0.2.2:11434)
- MCP 서버 (stdio transport, langchain-mcp-adapters)
- OpenStack SDK
- FastAPI + WebSocket
- Redis (AsyncRedisSaver — 체크포인터 + 세션 저장)
- ZConverter 에이전트 (cloud-init/userdata 자동 설치 예정)

---

## 플로우차트

```
START → intent_router
  ├── recover_server + server_id → get_server_info
  └── direct_response 또는 server_id 없음 → response

get_server_info
  ├── 성공 → generate_policy
  └── error → error_handler

generate_policy
  ├── 성공 → review_policy
  └── error → error_handler

review_policy (HITL)
  ├── 승인 → execute_recovery
  ├── 거절 + retry < 3 → generate_policy
  └── 거절 + retry ≥ 3 또는 error → error_handler

execute_recovery
  ├── 성공 → generate_report
  └── error → error_handler

generate_report
  ├── 성공 → END
  └── error → error_handler

response → END
error_handler → END
```

---

## 실제 프로젝트 구조

```
agent_server/
└── agent_server/
    ├── main.py                        # FastAPI lifespan, MCP 클라이언트, 라우터 등록
    └── app/
        ├── graph_agent/
        │   ├── state.py               # ChatState 정의
        │   ├── schemas.py             # RouteDecision, RecoveryPolicy Pydantic 모델
        │   ├── agents.py              # LLM 초기화, mcp_tools, answer_generator
        │   ├── nodes.py               # 각 노드 함수
        │   └── graph.py               # StateGraph 조립 + 라우팅 함수
        ├── mcp_servers/
        │   └── openstack-mcp-server/
        │       ├── main.py            # MCP 서버 진입점 (stdio)
        │       ├── handlers/
        │       │   ├── compute.py     # handle_get_server_info, handle_create_vm (현재 mock)
        │       │   └── recovery.py    # handle_execute_recovery, handle_get_recovery_status (mock)
        │       └── tools/
        │           ├── compute.py     # MCP 툴 정의 (get_server_info, create_vm)
        │           └── recovery.py    # MCP 툴 정의 (execute_recovery, get_recovery_status)
        ├── ws/
        │   └── chat.py                # WebSocket 엔드포인트, HITL 처리
        └── auth/
            ├── jwt_verify.py          # JWT 검증 + Redis 세션 확인
            └── schema.py              # TokenPayload (Keystone user_id, project_id 등 포함)
```

---

## State 정의

```python
class ChatState(MessagesState):
    # 라우팅
    intent:          str | None
    server_id:       str | None

    # 복구 플로우
    server_info:     dict | None   # name, flavor, image, addresses, networks, security_groups 등
    recovery_policy: dict | None   # name, flavor, image_id, network_id, recovery_type, reason
    vm_info:         str | None
    report:          str | None

    # 거절 관리
    retry_count:     int
    reject_reason:   str | None

    # 에러
    error:           str | None
```

## Pydantic 스키마

```python
class RouteDecision(BaseModel):
    intent:    Literal["recover_server", "direct_response"]
    server_id: str | None

class RecoveryPolicy(BaseModel):
    name:          str
    flavor:        Literal["m1.tiny", "m1.small", "m1.medium", "m1.large", "m1.xlarge"]
    image_id:      str
    network_id:    str
    recovery_type: Literal["snapshot_restore", "fresh_install", "config_replicate"]
    reason:        str
```

---

## 에이전트 구성

| 에이전트 | 역할 | LLM | 구조화 출력 |
|----------|------|-----|------------|
| intent_llm | intent 분류 + server_id 추출 | qwen2.5:7b | RouteDecision (json_mode) |
| policy_llm | RecoveryPolicy JSON 생성 | qwen2.5:7b | RecoveryPolicy (json_mode) |
| response_agent | direct_response 플로우 일반 응답 | qwen2.5:7b | create_react_agent |

---

## 핵심 설계 결정사항

**MCP 클라이언트 생명주기**
- `langchain-mcp-adapters 0.1.0`부터 `async with MultiServerMCPClient(...)` 미지원
- `MultiServerMCPClient(...).get_tools()`로 단순 호출, 프로세스 종료는 Docker가 담당
- Slack + OpenStack MCP를 각각 별도 클라이언트로 관리, `init_agents(all_tools)`에 통합 전달

**MCP 서버 경로**
- `main.py` 기준으로 `Path(__file__).parent / "app" / "mcp_servers" / "openstack-mcp-server"`
- `cwd` + `args: ["main.py"]` 방식으로 subprocess 실행

**intent_router 컨텍스트 제한**
- 전체 대화 이력 대신 마지막 HumanMessage만 전달
- 이유: ToolMessage/AIMessage 이력이 포함되면 qwen이 function-calling 포맷으로 오응답

**MCP 툴 응답 파싱**
- `langchain-mcp-adapters`가 응답을 `[{'type': 'text', 'text': '...json...'}]` 형태로 래핑
- `_parse_mcp_result(result)` 헬퍼로 list/str/dict 모두 처리

**HITL 포맷**
- `node_review_policy`: `interrupt({"type": "policy_review", "policy": ..., "server_info": ...})`
- `ws/chat.py` resume: `Command(resume={"approved": bool, "reason": str})`
- 프론트 → 서버: `{"type": "confirm_response", "approved": true/false, "reason": "..."}`

**system_prompt 언어**
- INTENT_SYSTEM, POLICY_SYSTEM: 영어 (JSON 구조화 출력 안정성)
- RESPONSE_SYSTEM: 영어 + "Always respond in Korean" 명시

**Redis 세션**
- Django Horizon이 로그인 시 `chat:session:{session_key}`에 저장
- 포함 데이터: user_id, username, project_id, roles, keystone_token, created_at
- `jwt_verify.py`에서 `f"chat:session:{session_id}"` 키로 존재 확인 필요 (현재 수정 필요)
- Keystone 토큰 활용 시 `ws/chat.py`에서 Redis 조회 후 graph input에 주입 가능

**generate_report**
- LLM/MCP 호출 없음, state 값으로 문자열 직접 조합
- MCP 로그에 나타나지 않는 것이 정상

---

## 노드별 현재 구현 상태

| 노드 | 상태 | 비고 |
|------|------|------|
| intent_router | ✅ 완료 | 마지막 HumanMessage만 사용, 로깅 추가 |
| get_server_info | ✅ 완료 | MCP 응답 list 파싱 처리 |
| generate_policy | ✅ 완료 | 거절 이유 반영, 재시도 카운트 |
| review_policy | ✅ 완료 | interrupt() HITL, 승인/거절/이유 처리 |
| execute_recovery | ✅ 완료 | create_vm MCP 호출, list 파싱 처리 |
| generate_report | ✅ 완료 | 문자열 조합, LLM 없음 |
| response | ✅ 완료 | response_agent 위임 |
| error_handler | ✅ 완료 | retry_count 기반 메시지 분기 |

---

## MCP 툴 현재 상태

| 툴 | 상태 | 비고 |
|----|------|------|
| get_server_info | ⚠️ Mock | 실제 OpenStack SDK 연동 필요 |
| create_vm | ⚠️ Mock | 실제 OpenStack SDK 연동 필요 |
| execute_recovery | ⚠️ Mock | ZConverter API 연동 필요 |
| get_recovery_status | ⚠️ Mock | ZConverter API 연동 필요 |

**실제 get_server_info SDK 구현 계획**
```python
conn.compute.find_server(server_id)   # UUID/이름/부분이름 허용
conn.compute.get_server(server.id)    # 전체 상세
conn.image.get_image(server.image.id) # 이미지 상세 (name, status, disk_format)
conn.network.ports(device_id=server.id) # 포트/네트워크 UUID
```
- OpenStack 인증: 환경변수(OS_AUTH_URL 등) 또는 Redis 세션의 keystone_token 활용
- 동기 SDK → `asyncio.to_thread`로 비동기 처리

---

## WebSocket HITL 메시지 포맷

**서버 → 클라이언트**
```json
// 정책 검토 요청
{"type": "policy_review", "policy": {...}, "server_info": {...}, "message": "..."}

// 대화 이력 (새로고침 시)
{"type": "history", "messages": [{"role": "user/assistant", "content": "..."}]}

// 일반 텍스트 응답 (plain string)
"복구가 완료되었습니다..."
```

**클라이언트 → 서버**
```json
// 일반 메시지
{"content": "a1b2c3d4-0002 서버 복구 진행해줘"}

// 정책 승인
{"type": "confirm_response", "approved": true, "reason": ""}

// 정책 거절
{"type": "confirm_response", "approved": false, "reason": "flavor가 너무 작습니다"}
```

---

## 2차 고도화 항목 (미구현)

- [ ] get_server_info 실제 OpenStack SDK 구현
- [ ] create_vm 실제 OpenStack SDK 구현 (userdata ZConverter 설치 포함)
- [ ] execute_recovery ZConverter API 연동
- [ ] get_recovery_status 상태 폴링
- [ ] find_server 복수 결과 시 interrupt()로 사용자 선택
- [ ] keystone_token 기반 인증 (Redis 세션 활용)
- [ ] jwt_verify.py Redis 키 프리픽스 수정 (`chat:session:{session_id}`)
- [ ] retry_count 승인 시 초기화 여부 결정
- [ ] ZConverter 백업 이미지 자동 검색 (DB 또는 API 연동)
- [ ] RAG 기반 과거 복구 이력 참조
- [ ] direct_response 플로우 고도화

---

## 환경 변수

```
# OpenStack
OS_AUTH_URL
OS_USERNAME
OS_PASSWORD
OS_PROJECT_NAME

# Redis
REDIS_HOST
REDIS_PORT

# Slack MCP
SLACK_BOT_TOKEN
SLACK_TEAM_ID

# JWT
JWT_ALGORITHM
JWT_AUDIENCE
JWT_ISSUER
```
