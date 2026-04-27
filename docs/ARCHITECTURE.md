# 아키텍처: ZIASTACK DR 복구 자동화

## 컴포넌트 구조

```
┌─────────────────────────────────────────────────────────┐
│  운영자 (Browser)                                         │
└────────────────┬────────────────────────────────────────┘
                 │ WebSocket / REST
┌────────────────▼────────────────────────────────────────┐
│  Django · Horizon  [Plan / Confirm UI]                   │
│  - 복구 요청 접수 (서버 이름 입력)                          │
│  - AI 정책 표시 + 승인/거절 (거절 사유 필수)                │
│  - 실시간 상태 스트리밍 (WebSocket)                         │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  AI Agent  [Claude API + Tool Calling]                   │
│  - Plan: 리소스 수집 → RAG 검색 → 복구 정책 생성            │
│  - Execute: MCP Tool 호출로 VM 생성 및 복구 실행            │
│  - Report: 결과 리포트 자동 생성                            │
│  - Failure: 로그 분석 → 원인 추정 → 재시도                  │
├─────────────────────────┬───────────────────────────────┤
│  Chroma (Vector DB)      │  도구 목록 (MCP Tools)         │
│  - 런북 / 매뉴얼 (TBD)   │  - vm_query(name)             │
│  - 복구 성공 이력        │  - vm_create(spec)            │
│  - 장애 대응 지식        │  - recovery_execute(policy)   │
└─────────────────────────┴──────────┬────────────────────┘
                                     │ Streamable HTTP
┌────────────────────────────────────▼────────────────────┐
│  MCP Server  [Tool Gateway]                              │
│  - AI Agent → OpenStack 사이의 유일한 진입점               │
│  - Tool 인터페이스 정의 및 라우팅                           │
└────────────────────────────────────┬────────────────────┘
                                     │ HTTP + Pre-shared Key
┌────────────────────────────────────▼────────────────────┐
│  FastAPI  [Internal Adapter]                             │
│  - Pre-shared Key 헤더 인증 (Guard Clause)                │
│  - MCP 요청 → OpenStack SDK 호출 변환                      │
│  - Redis에 작업 상태 저장 / Lock 관리                       │
│  - Kafka에 Execute 이벤트 발행                             │
│  - Slack MCP / Jira MCP 알림 트리거                        │
└──────────────┬──────────────────┬──────────────────┬────┘
               │ SDK              │                  │
┌──────────────▼───┐  ┌───────────▼──┐  ┌────────────▼──┐
│  OpenStack        │  │  Redis        │  │  Kafka        │
│  Nova (VM)        │  │  State · Lock │  │  Execute      │
│  Neutron (Net)    │  │  TTL          │  │  Events       │
│  Cinder (Volume)  │  └──────────────┘  └───────────────┘
│  Glance (Image)   │
└──────────────┬───┘
               │ Userdata
┌──────────────▼────────────────────────────────────────┐
│  ZConverter Cloud AI 에이전트 (VM 내부)                  │
│  - VM 내부 설치 후 복구 작업 자동 진행                      │
│  - 세부 동작 TBD                                         │
└───────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  DB (PostgreSQL)          Slack MCP       Jira MCP     │
│  - 복구 이력 영구 저장      - 완료/실패 알림  - 티켓 자동 생성 │
└────────────────────────────────────────────────────────┘
```

## 디렉토리 구조 (예정)

```
ziastack-dr/
├── ui/                        # Django · Horizon
│   ├── views/                 # 복구 요청, 정책 확인, 상태 모니터링
│   ├── consumers/             # WebSocket consumers
│   └── templates/
├── agent/                     # AI Agent (Claude API)
│   ├── planner.py             # Plan 단계 — 정책 생성
│   ├── executor.py            # Execute 단계 — Tool Calling
│   ├── reporter.py            # Report 단계 — 리포트 생성
│   └── tools.py               # MCP Tool 정의
├── mcp/                       # MCP Server
│   └── server.py              # Streamable HTTP 서버
├── adapter/                   # FastAPI Internal Adapter
│   ├── main.py
│   ├── auth.py                # Pre-shared Key 인증
│   ├── openstack/             # OpenStack SDK 래퍼
│   │   ├── nova.py
│   │   ├── neutron.py
│   │   ├── cinder.py
│   │   └── glance.py
│   ├── state.py               # Redis 상태 관리
│   └── events.py              # Kafka 이벤트 발행
├── rag/                       # Chroma RAG
│   ├── ingest.py              # 런북 인제스트 (TBD)
│   └── retriever.py           # 복구 정책 검색
└── db/                        # PostgreSQL 모델
    └── models.py              # 복구 이력 스키마
```

## 데이터 흐름

### Plan Phase
```
운영자 입력(서버 이름)
  → Django → AI Agent
  → Nova API: 서버 이름으로 VM 조회 (타겟 존재 여부 판단)
  → Nova API: 소스 서버 리소스 수집 (CPU/Memory/Disk/Network)
  → Chroma RAG: 관련 런북 검색
  → Claude API: 복구 정책 생성
  → Django UI에 정책 표시
```

### Confirm Phase
```
운영자 승인 → Execute Phase로 진행
운영자 거절 (사유 필수) → AI Agent 정책 재생성 (최대 3회)
3회 초과 → blocked 상태 전환
```

### Execute Phase
```
승인된 정책
  → AI Agent → MCP Server → FastAPI (Pre-shared Key 인증)
  → Redis Lock 획득 (중복 실행 방지)
  → [타겟 없는 경우] Nova API: VM 생성
  → [타겟 없는 경우] Userdata: ZConverter AI 에이전트 설치
  → 복구 실행 (ZConverter AI 에이전트가 VM 내 처리)
  → Kafka: Execute 이벤트 발행
  → WebSocket: 실시간 상태 스트리밍
```

### Report Phase
```
복구 완료/실패
  → Claude API: 리포트 자동 생성
  → DB: 이력 저장
  → Chroma: 정책/장애 지식 누적
  → Slack MCP / Jira MCP: 알림 발송
```

## 상태 관리

- **작업 상태** (Redis): `pending → planning → confirming → executing → completed / failed / blocked / cancelled`
- **분산 Lock** (Redis): 동일 작업 ID 중복 실행 방지, TTL 설정
- **이벤트** (Kafka): Execute Phase 진행 이벤트 — UI WebSocket 스트리밍용
