# 현재까지 완성한 프로젝트가 실제로 어떻게 동작하는지

현재 이 프로젝트는 문서에 적힌 전체 DR 자동화가 모두 완성된 상태는 아니다.
실제로는 **“Horizon에서 발급한 JWT를 들고 WebSocket으로 접속하면, FastAPI 기반 AI 서버가 요청을 받아 MCP 도구를 호출할 수 있는 채팅 시스템”** 까지가 핵심 동작이다.

---

## 1. 현재 구현 기준 전체 동작 흐름

현재 완성된 흐름을 순서대로 보면 다음과 같다.

1. 클라이언트가 Horizon/Django 쪽에서 JWT를 발급받는다.
2. 그 JWT를 `ws://.../ws/chat?token=...` 형태로 FastAPI WebSocket 서버에 붙인다.
3. FastAPI는 JWT의 서명, issuer, audience, 만료시간, 중복 사용 여부, Redis 세션 존재 여부를 검사한다.
4. 검증이 통과하면 WebSocket 연결을 유지한 채 사용자의 채팅 메시지를 받는다.
5. 메시지를 받으면 FastAPI 내부의 AI supervisor가 요청 내용을 해석한다.
6. supervisor는 요청 성격에 따라 Slack, Filesystem, OpenStack 중 적절한 MCP 도구를 쓰도록 하위 agent에 위임한다.
7. 도구 실행 결과를 바탕으로 최종 응답을 생성해 WebSocket으로 다시 클라이언트에 보낸다.

즉, 현재 동작의 본질은:

- **인증된 운영자 채팅**
- **AI supervisor 기반 요청 분기**
- **MCP tool calling**
- **응답 반환**

이다.

---

## 2. 현재 서버별 역할

### Horizon/Django 쪽 역할

문서와 README 기준으로 Horizon 쪽은 인증의 시작점이다.

- 로그인된 사용자 기준으로 JWT 발급
- JWT 안에 `user_id`, `username`, `project_id`, `roles`, `session_id` 등을 넣음
- Redis에 세션 관련 키를 저장

즉, FastAPI가 독립적으로 로그인 처리하는 구조가 아니라,
**기존 운영 포털(Horizon)의 인증 결과를 받아서 AI 서버가 신뢰하는 구조**다.

### FastAPI `agent_server` 역할

현재 실제 실행 중심은 `agent_server`다.

이 서버는:

- WebSocket 엔드포인트 제공
- JWT 검증
- Redis 조회
- LLM + LangGraph supervisor 실행
- MCP 서버 연결
- 최종 응답 반환

을 담당한다.

---

## 3. 현재 채팅이 실제로 처리되는 방식

현재 채팅 처리는 [agent_server/app/ws/chat.py](/home/woonkim/ZconvertProject/agent_server/app/ws/chat.py:1) 와 [agent_server/app/agent/agent.py](/home/woonkim/ZconvertProject/agent_server/app/agent/agent.py:1) 기준으로 이해하면 된다.

동작은 단순하다.

1. WebSocket 연결 수립
2. `token` 쿼리 파라미터 검증
3. 인증 성공 시 메시지 루프 진입
4. 사용자가 텍스트 메시지 전송
5. `answer_generator(supervisor, message)` 호출
6. supervisor가 agent/tool 사용 후 응답 생성
7. 생성된 결과를 문자열로 다시 전송

중요한 점은 현재 코드상:

- 대화 이력 저장이 사실상 비활성화 상태
- message history 기반 맥락 유지가 없음
- 매 메시지를 거의 단발성 요청처럼 처리

라는 것이다.

즉, “채팅 UI”는 있지만 아직 완성도 높은 멀티턴 대화 시스템은 아니다.

---

## 4. 현재 붙어 있는 도구들

현재 supervisor는 세 종류의 도구 계열을 다룬다.

### 4-1. Slack 도구

- Slack 관련 요청을 처리하기 위한 MCP 서버

### 4-2. Filesystem 도구

- 파일 읽기/쓰기/디렉터리 조회용 MCP 서버

### 4-3. OpenStack 도구

- 서버 정보 조회
- VM 생성
- 복구 실행
- 복구 상태 조회

즉, 사용자가 채팅으로 어떤 요청을 하느냐에 따라
AI가 “어떤 도구를 써야 하는지” 판단하고 호출하는 구조다.

---

## 5. OpenStack 쪽은 현재 어디까지 진짜인가

이 부분이 중요하다.

현재 저장소의 OpenStack MCP 서버는 [agent_server/app/mcp_servers/openstack-mcp-server/main.py](/home/woonkim/ZconvertProject/agent_server/app/mcp_servers/openstack-mcp-server/main.py:1) 기준으로 붙어 있지만,
실제 핸들러 구현은 아직 mock 성격이 강하다.

예를 들면:

- 서버 조회는 하드코딩된 mock 서버 목록 반환
- VM 생성은 가짜 UUID를 만들어 반환
- 복구 실행도 메모리 내 job store에 상태를 넣는 수준
- 복구 상태 조회도 호출할 때마다 progress가 증가하는 시뮬레이션

즉, 현재는
**“OpenStack DR 자동화 시스템의 실제 운영 구현”이라기보다**
**“OpenStack용 tool calling 구조를 먼저 실험하고 있는 프로토타입”**
으로 보는 것이 맞다.

---

## 6. RAG는 현재 어떻게 동작하나

사실상 아직 동작하지 않는다고 보는 편이 정확하다.

이유:

- `app/knowledge/runbooks/` 디렉터리는 비어 있음
- Chroma 연동 코드 없음
- 문서에는 RAG가 핵심으로 적혀 있지만 실제 retrieval 파이프라인이 없음

즉, 현재 프로젝트는
**“RAG 기반으로 잘 동작하는 상태”는 아니다.**

당신이 알고 있던 설명 중 `RAG로 처리한다`는 부분은
**기획상 목표는 맞지만, 현재 구현 상태 설명으로는 과장**이다.

---

## 7. 리포트 생성/저장은 현재 어떻게 동작하나

이 부분도 문서상 목표에 비해 현재 구현은 부족하다.

문서에는:

- 복구 결과 리포트 생성
- DB 저장
- Slack/Jira 알림
- Chroma 지식 축적

이 포함되어 있다.

하지만 현재 코드 기준으로는:

- 리포트 전용 로직이 명확히 구현되어 있지 않고
- 영구 저장 DB 구조도 없다
- Slack/Jira 후처리 자동화도 완성되지 않았다

즉, “리포트 생성 및 저장” 역시 현재는 완성 기능이라기보다 향후 목표다.

---

## 8. 지금 시점에서 가장 정확한 한 문장 설명

현재까지 완성된 프로젝트는:

**“Horizon 인증 기반으로 WebSocket 채팅을 열고, FastAPI의 AI supervisor가 MCP 도구(Slack/파일시스템/OpenStack mock)를 호출해 응답하는 운영용 AI 게이트웨이 프로토타입”**

이라고 설명하는 것이 가장 정확하다.

---

## 9. 결론

지금 이 프로젝트는 “채팅 UI에 프롬프트를 입력하면 AI가 도구를 호출해 응답하는 구조”까지는 맞다.
하지만 다음 항목들은 아직 완성됐다고 보기 어렵다.

- RAG 기반 지식 검색
- 실제 OpenStack 복구 자동화
- 복구 승인/거절 워크플로우
- 리포트 영구 저장
- 실패 재시도/이력 축적

따라서 현재 프로젝트를 이해할 때는
**“완성된 DR 자동화 제품”으로 보기보다**
**“운영 포털 연동형 AI 채팅 + MCP tool calling 프로토타입”**
으로 받아들이는 것이 정확하다.
