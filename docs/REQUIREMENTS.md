# 요구사항 명세서: ZIASTACK DR 복구 자동화

## 기능 요구사항 (FR)

### Plan Phase

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | 운영자가 UI에서 복구 대상 소스 서버를 선택할 수 있다 | Must |
| FR-02 | 시스템이 OpenStack API로 소스 서버의 CPU/Memory/Disk/Network 상태를 자동 수집한다 | Must |
| FR-03 | 운영자가 입력한 서버 이름을 기준으로 OpenStack Nova API에서 VM을 조회한다. 해당 이름의 VM이 없으면 타겟 서버 없음으로 판단한다 | Must |
| FR-04 | 타겟 서버가 없는 경우, 소스 서버 스펙 기반으로 신규 VM 파라미터를 자동 산출한다 | Must |
| FR-05 | AI 에이전트가 Chroma에서 관련 런북/복구 이력을 RAG로 검색한다 | Must |
| FR-06 | AI 에이전트(Claude API)가 수집 데이터 + RAG 결과를 기반으로 복구 정책을 생성한다 | Must |
| FR-07 | 복구 정책에는 백업 시점, 복구 유형(Full/증분), 실행 순서, 예상 소요 시간이 포함된다 | Must |

### Confirm Phase

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-08 | 생성된 복구 정책이 UI에 가독성 있게 표시된다 | Must |
| FR-09 | 엔지니어가 승인 또는 거절을 선택할 수 있다 | Must |
| FR-10 | 거절 시 사유 입력이 필수이며, 사유를 반영하여 AI가 정책을 재생성한다 | Must |
| FR-11 | 거절 후 재생성을 3회 초과하면 작업이 blocked 상태로 중단된다 | Must |

### Execute Phase

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-12 | 승인 후 MCP Server → FastAPI → OpenStack SDK 경로로 복구 작업이 자동 실행된다 | Must |
| FR-13 | 타겟 서버가 없는 경우 Nova API로 VM을 자동 생성한다 | Must |
| FR-14 | VM 생성 시 Userdata 스크립트로 ZConverter Cloud AI 에이전트가 VM 내부에 자동 설치된다 | Must |
| FR-14a | 설치된 ZConverter AI 에이전트가 VM 내부에서 이후 복구 작업을 자동으로 진행한다 | Must |
| FR-14b | ZConverter AI 에이전트의 등록 완료 후 세부 동작 방식은 추후 확정 (TBD) | TBD |
| FR-15 | 복구 작업 상태가 Redis에 저장되어 중복 실행이 방지된다 (분산 Lock) | Must |
| FR-16 | Execute Phase의 복구 진행 이벤트가 Kafka에 발행되어 실시간 모니터링에 사용된다. Plan/Confirm 단계 이벤트는 Kafka 미사용 | Must |
| FR-17 | 복구 상태가 WebSocket으로 UI에 실시간 스트리밍된다 | Must |
| FR-18 | 복구 작업은 멱등성을 보장한다 (동일 요청 재실행 시 중복 처리 없음) | Must |

### Report Phase

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-19 | 복구 성공 시 AI가 결과 리포트를 자동 생성한다 (소요 시간, 서버 정보, 전체 작업 내역) | Must |
| FR-20 | 복구 완료/실패 알림이 Slack으로 자동 발송된다 | Must |
| FR-21 | 복구 완료/실패 시 Jira 티켓이 자동 생성된다 | Should |
| FR-22 | 복구 이력이 DB에 영구 저장된다 | Must |
| FR-23 | 복구 성공 정책이 Chroma에 누적되어 RAG 지식베이스가 갱신된다 | Must |

### Failure Handling

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-24 | 복구 실패 시 AI가 로그를 자동 수집·분석하여 원인을 추정한다 | Must |
| FR-25 | AI가 해결 방안을 제시하고 엔지니어에게 최종 조치를 요청한다 | Must |
| FR-26 | 실패 원인과 해결 과정이 Chroma에 누적된다 (장애 대응 지식) | Should |
| FR-27 | 실패 시 최대 3회 자동 재시도하며, 이전 에러를 다음 시도 프롬프트에 포함한다 | Must |

---

## 비기능 요구사항 (NFR)

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-01 | **보안** MCP Server → FastAPI 통신은 Pre-shared Key 헤더 인증 | 내부망 전용, 외부 노출 금지 |
| NFR-02 | **멱등성** 동일 복구 작업 ID의 중복 실행 방지 | Redis Lock으로 보장 |
| NFR-03 | **성능** 복구 정책 생성(Plan) 30초 이내 완료 | Claude API 응답 포함 |
| NFR-04 | **신뢰성** 실패 시 자동 재시도 최대 3회 | 이전 에러 컨텍스트 포함 |
| NFR-05 | **감사 추적** 모든 복구 작업의 입력/결과/타임스탬프 DB 로깅 | 삭제 불가 |
| NFR-06 | **확장성** MCP Tool은 인터페이스 변경 없이 신규 OpenStack 오퍼레이션 추가 가능 | |

---

## 제약사항

- OpenStack(ZIASTACK 플랫폼) 전용. 멀티 클라우드 미지원.
- Claude API 의존. 로컬 LLM 대체 불가 (MVP 기준).
- ZConverter Cloud AI 에이전트 설치는 Userdata 방식만 지원. SSH 수동 설치 미지원.
- 런북/매뉴얼 데이터 형식 미확정 (TBD). RAG 인제스트 파이프라인은 형식 확정 후 구현.
- Kafka는 Execute Phase 이벤트 전용. Plan/Confirm 단계에서는 미사용.
- 복구 정책 파라미터 직접 편집 UI 없음. 승인/거절만 가능.
