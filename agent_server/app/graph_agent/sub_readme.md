# graph_agent 모듈 문서

LangGraph StateGraph 기반 DR(Disaster Recovery) 에이전트 구현체.

---

## 파일 구성

| 파일 | 역할 |
|------|------|
| `state.py` | ChatState 타입 정의 |
| `schemas.py` | LLM 구조화 출력용 Pydantic 모델 |
| `agents.py` | LLM 인스턴스 초기화, mcp_tools, answer_generator |
| `nodes.py` | 그래프 노드 함수 구현 |
| `graph.py` | StateGraph 조립 및 조건부 엣지 라우팅 |

---

## 플로우차트

```
START
  │
  ▼
intent_router ──────────────────────────────────────────┐
  │ recover_server + server_id                           │ direct_response
  ▼                                                      │ (또는 server_id 없음)
get_server_info                                          │
  │ 성공               │ error                           │
  ▼                   ▼                                  │
generate_policy    error_handler ◄──────────────────────┤
  │ 성공               ▲                                 │
  ▼                   │                                  │
review_policy ────────┤ error / retry ≥ 3               │
  │ 승인               │ 거절                             │
  │                   └─────────────────────────────────┤ (retry < 3 → generate_policy)
  ▼                                                      │
execute_recovery                                         │
  │ 성공               │ error                           │
  ▼                   ▼                                  │
generate_report    error_handler                         │
  │ 성공               │ error                           ▼
  ▼                   ▼                               response
  END               error_handler                        │
                       │                                 ▼
                       ▼                               END
                      END
```

---

## state.py — ChatState

`MessagesState`를 상속한 그래프 공유 상태. 모든 노드가 이 상태를 읽고 부분 업데이트를 반환한다.

```python
class ChatState(MessagesState):
    # 라우팅
    intent:          str | None        # "recover_server" | "direct_response"
    server_id:       str | None        # 복구 대상 서버 UUID

    # 복구 플로우
    server_info:     dict | None       # OpenStack 서버 상세 정보
    recovery_policy: dict | None       # 생성된 복구 정책 (RecoveryPolicy.model_dump())
    vm_info:         str | None        # create_vm 결과 JSON 문자열
    report:          str | None        # 최종 복구 보고서 문자열

    # 거절 관리
    retry_count:     int               # 정책 생성 시도 횟수
    reject_reason:   str | None        # 사용자 거절 이유 (다음 generate_policy에 반영)

    # 에러 관리
    error:           str | None        # 에러 메시지 (노드가 설정, 라우터가 분기 판단에 사용)
```

> `MessagesState`는 `messages: Annotated[list[BaseMessage], add_messages]`를 포함한다. 각 노드는 반환 dict에 `"messages"` 키를 포함시켜 대화 이력에 AIMessage를 추가한다.

---

## schemas.py — Pydantic 모델

LLM의 `with_structured_output(..., method="json_mode")` 출력 파싱에 사용된다.

### RouteDecision

```python
class RouteDecision(BaseModel):
    intent:    Literal["recover_server", "direct_response"]
    server_id: str | None  # 요청에 서버 ID가 명시된 경우만 추출
```

### RecoveryPolicy

```python
class RecoveryPolicy(BaseModel):
    name:          str
    flavor:        Literal["m1.tiny", "m1.small", "m1.medium", "m1.large", "m1.xlarge"]
    image_id:      str
    network_id:    str
    recovery_type: Literal["snapshot_restore", "fresh_install", "config_replicate"]
    reason:        str
```

---

## agents.py — LLM 초기화

### 전역 변수

| 변수 | 타입 | 설명 |
|------|------|------|
| `mcp_tools` | `dict[str, Tool]` | `{tool.name: tool}` 딕셔너리. 노드에서 `agents.mcp_tools["get_server_info"]`로 접근 |
| `intent_llm` | `Runnable` | `RouteDecision` 구조화 출력 LLM |
| `policy_llm` | `Runnable` | `RecoveryPolicy` 구조화 출력 LLM |
| `response_agent` | `CompiledGraph` | `create_react_agent` 기반 일반 응답 에이전트 |

### init_agents(tools: list)

`main.py`의 lifespan에서 MCP 툴 목록을 받아 1회 초기화한다.

```python
async def init_agents(tools: list):
    mcp_tools = {tool.name: tool for tool in tools}
    base_llm  = ChatOpenAI(model="qwen2.5:7b", base_url="http://10.0.2.2:11434/v1", ...)
    intent_llm  = base_llm.with_structured_output(RouteDecision, method="json_mode")
    policy_llm  = base_llm.with_structured_output(RecoveryPolicy, method="json_mode")
    response_agent = create_react_agent(model=ChatOpenAI(..., temperature=0.3), tools=tools, prompt=RESPONSE_SYSTEM)
```

### 시스템 프롬프트

| 상수 | 사용 노드 | 언어 | 목적 |
|------|-----------|------|------|
| `INTENT_SYSTEM` | `node_intent_router` | 영어 | intent 분류 + server_id 추출, JSON 출력 유도 |
| `POLICY_SYSTEM` | `node_generate_policy` | 영어 | RecoveryPolicy JSON 생성, 외부 키 래핑 방지 |
| `RESPONSE_SYSTEM` | `response_agent` | 영어 + "Always respond in Korean" | 일반 질문 응답 |

> 시스템 프롬프트를 영어로 작성하는 이유: qwen2.5:7b에서 JSON 구조화 출력의 안정성이 높아짐.

### answer_generator(agent, graph_input, thread_id)

`ws/chat.py`에서 호출하는 그래프 실행 래퍼.

```python
async def answer_generator(agent, graph_input, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return await agent.ainvoke(graph_input, config=config)
```

---

## nodes.py — 노드 구현

### 공통 패턴

- 노드는 `ChatState`를 받아 `dict`를 반환한다 (부분 상태 업데이트).
- 에러 발생 시 `{"error": "메시지"}` 반환 → 라우터가 `error_handler`로 분기.
- MCP 응답 파싱: `langchain-mcp-adapters`가 응답을 `[{'type': 'text', 'text': '...json...'}]`로 래핑하므로 list/str/dict 모두 처리.

```python
# MCP 응답 파싱 패턴
if isinstance(result, list):
    text = result[0].get("text", "") if result else ""
    info = json.loads(text)
elif isinstance(result, str):
    info = json.loads(result)
else:
    info = result
```

### _invoke_with_retry(llm, messages, max_retries=3)

`ValidationError`, `OutputParserException`, `ValueError` 발생 시 최대 3회 재시도.

---

### node_intent_router

**역할:** 사용자 메시지를 분석해 `intent`와 `server_id`를 추출한다.

**설계 포인트:** 전체 대화 이력 대신 마지막 `HumanMessage`만 `intent_llm`에 전달한다.
- 이유: 이전 ToolMessage/AIMessage가 포함되면 qwen이 function-calling JSON 포맷으로 오응답.

```python
messages = [SystemMessage(content=INTENT_SYSTEM), last_human]
decision = await _invoke_with_retry(intent_llm, messages)
return {"intent": decision.intent, "server_id": decision.server_id}
```

**반환:** `{"intent": str, "server_id": str | None}`

---

### node_get_server_info

**역할:** MCP `get_server_info` 툴을 호출해 서버 상세 정보를 수집한다.

```python
result = await agents.mcp_tools["get_server_info"].ainvoke({"server_id": state["server_id"]})
```

**반환:** `{"server_info": dict, "messages": [AIMessage]}`  
**에러 시:** `{"error": str}`

---

### node_generate_policy

**역할:** `server_info`와 선택적 `reject_reason`을 기반으로 `RecoveryPolicy`를 생성한다.

- `retry_count`를 +1 증가시켜 반환.
- `reject_reason`이 있으면 프롬프트에 포함 → LLM이 다른 flavor/image 선택 유도.
- 완료 후 `reject_reason`을 `None`으로 초기화.

**반환:** `{"recovery_policy": dict, "retry_count": int, "reject_reason": None, "messages": [AIMessage]}`

---

### node_review_policy (HITL)

**역할:** 생성된 정책을 사용자에게 보여주고 승인/거절을 기다린다.

`interrupt()`로 그래프를 일시 정지. `ws/chat.py`가 `type:"policy_review"` 메시지를 클라이언트에 전송하고, 사용자 응답을 `Command(resume={...})`로 그래프를 재개한다.

```python
decision = interrupt({
    "type": "policy_review",
    "policy": state["recovery_policy"],
    "server_info": state["server_info"],
})

if decision.get("approved"):
    return {"messages": [AIMessage(content="정책 승인됨, VM 생성 진행")]}
return {"reject_reason": decision.get("reason", "사용자 거절"), ...}
```

**승인 시 반환:** `{"messages": [AIMessage]}`  
**거절 시 반환:** `{"reject_reason": str, "messages": [AIMessage]}`

---

### node_execute_recovery

**역할:** 승인된 `recovery_policy`로 MCP `create_vm` 툴을 호출해 VM을 생성한다.

```python
result = await agents.mcp_tools["create_vm"].ainvoke({
    "name": policy["name"], "flavor": policy["flavor"],
    "image_id": policy["image_id"], "network_id": policy["network_id"],
})
```

**반환:** `{"vm_info": str, "messages": [AIMessage]}`  
**에러 시:** `{"error": str}`

---

### node_generate_report

**역할:** LLM/MCP 호출 없이 state 값으로 최종 복구 보고서 문자열을 조합한다.

```
# 복구 완료 보고서
- 일시: YYYY-MM-DD HH:MM:SS
- 대상 서버: {server_id}
- 정책: {recovery_policy JSON}
- 결과: {vm_info}
```

**반환:** `{"report": str, "messages": [AIMessage]}`

---

### node_response

**역할:** `direct_response` 플로우 — `response_agent`(create_react_agent)에 전체 대화 이력을 위임한다.

```python
result = await agents.response_agent.ainvoke({"messages": state["messages"]})
return {"messages": result["messages"]}
```

---

### node_error_handler

**역할:** 에러 또는 최대 재시도 초과 시 사용자에게 안내 메시지를 반환한다.

- `retry_count >= MAX_POLICY_RETRIES(3)` 이면 관리자 확인 요청 메시지.
- 그 외에는 `error` 내용을 그대로 전달.

---

## graph.py — StateGraph 조립

### 라우팅 함수 요약

| 함수 | 판단 기준 | 분기 |
|------|-----------|------|
| `route_by_intent` | `state["intent"]`, `state["server_id"]` | `get_server_info` \| `response` |
| `route_after_server_info` | `state["error"]` | `generate_policy` \| `error_handler` |
| `route_after_policy` | `state["error"]` | `review_policy` \| `error_handler` |
| `route_after_review` | `error`, `reject_reason`, `retry_count` | `execute_recovery` \| `generate_policy` \| `error_handler` |
| `route_after_recovery` | `state["error"]` | `generate_report` \| `error_handler` |
| `route_after_report` | `state["error"]` | `END` \| `error_handler` |

### build_graph(checkpointer)

`main.py`의 lifespan에서 `AsyncRedisSaver` 인스턴스를 받아 그래프를 컴파일한다.

```python
app.state.agent = build_graph(checkpointer)
```

`ws/chat.py`는 `app.state.agent`를 참조해 `answer_generator`에 전달한다.

---

## 데이터 흐름 예시 (복구 플로우)

```
사용자: "a1b2c3d4-0002 서버 복구해줘"
  │
  ▼ intent_router
  state: {intent="recover_server", server_id="a1b2c3d4-0002"}
  │
  ▼ get_server_info  [MCP: get_server_info]
  state: {server_info={name, flavor, image, networks, ...}}
  │
  ▼ generate_policy  [LLM: policy_llm]
  state: {recovery_policy={name, flavor, image_id, ...}, retry_count=1}
  │
  ▼ review_policy  [interrupt() → 클라이언트 policy_review 카드 표시]
  사용자: "거절 — flavor가 너무 작습니다"
  state: {reject_reason="flavor가 너무 작습니다"}
  │
  ▼ generate_policy (재시도)  [LLM: policy_llm + reject_reason 포함]
  state: {recovery_policy={...m1.medium...}, retry_count=2, reject_reason=None}
  │
  ▼ review_policy  [interrupt() → 클라이언트 policy_review 카드 표시]
  사용자: "승인"
  state: {reject_reason=None}
  │
  ▼ execute_recovery  [MCP: create_vm]
  state: {vm_info="{id, name, status, ...}"}
  │
  ▼ generate_report
  state: {report="# 복구 완료 보고서\n..."}
  │
  ▼ END
  클라이언트: 보고서 텍스트 수신
```

---

## 현재 상태 및 미구현 항목

| 항목 | 상태 | 비고 |
|------|------|------|
| StateGraph 플로우 전체 | ✅ 완료 | Mock MCP 기준 end-to-end 동작 확인 |
| MCP get_server_info | ⚠️ Mock | 실제 OpenStack SDK 연동 필요 |
| MCP create_vm | ⚠️ Mock | 실제 OpenStack SDK + userdata ZConverter 설치 필요 |
| MCP execute_recovery | ⚠️ Mock | ZConverter API 연동 필요 |
| MCP get_recovery_status | ⚠️ Mock | ZConverter API 연동 필요 |
| find_server 복수 결과 처리 | ❌ 미구현 | 복수 결과 시 interrupt()로 사용자 선택 |
| keystone_token 기반 SDK 인증 | ❌ 미구현 | Redis 세션에서 토큰 추출 후 openstack conn에 주입 |
