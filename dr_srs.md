# AI 기반 ZIASTACK DR 복구 자동화
## 소프트웨어 요구사항 명세서 (SRS)
*Software Requirements Specification*

---

| 항목 | 내용 |
|------|------|
| 문서 버전 | v1.0 |
| 작성일 | 2026-05-07 |
| 프로젝트 | ZIASTACK DR 자동화 |
| 분류 | 내부 기밀 |
| 상태 | 초안 (Draft) |

---

## 목차

1. [문서 개요](#1-문서-개요)
2. [시스템 아키텍처 개요](#2-시스템-아키텍처-개요)
3. [기능 요구사항](#3-기능-요구사항-functional-requirements)
4. [비기능 요구사항](#4-비기능-요구사항-non-functional-requirements)
5. [기술 스택](#5-기술-스택)
6. [개발 일정](#6-개발-일정-3개월--12주)
7. [인터페이스 요구사항](#7-인터페이스-요구사항)
8. [제약 사항 및 가정](#8-제약-사항-및-가정)
9. [문서 변경 이력](#9-문서-변경-이력)

---

## 1. 문서 개요

### 1.1 목적

본 문서는 AI 기반 ZIASTACK Disaster Recovery(DR) 복구 자동화 시스템의 소프트웨어 요구사항을 정의한다.
개발팀, 인프라팀, QA팀이 공통 기준으로 사용하며 설계, 구현, 검증의 근거가 된다.

### 1.2 범위

본 시스템은 ZIASTACK(OpenStack 기반 프라이빗 클라우드) 환경에서 백업 이미지를 기반으로 VM을 자동 복구하는 End-to-End 파이프라인을 구현한다.

- 백업 이미지 감지 → 포맷 변환 → Glance 등록 → Nova VM 생성까지 전 과정 자동화
- LLM 기반 복구 정책 추천 및 AI Agent 실행 오케스트레이션
- MCP Server를 통한 Tool Calling 기반 실행 제어
- 복구 이력 추적, 실시간 상태 모니터링, 자동 보고서 생성
- Slack / Jira 연동을 통한 운영 알림 및 티켓 자동화

### 1.3 정의 및 약어

| 용어/약어 | 설명 |
|-----------|------|
| DR | Disaster Recovery – 재해복구 |
| VM | Virtual Machine – 가상 머신 |
| SRS | Software Requirements Specification – 소프트웨어 요구사항 명세서 |
| MCP | Model Context Protocol – AI Agent 도구 호출 프로토콜 |
| RAG | Retrieval-Augmented Generation – 검색 증강 생성 |
| LLM | Large Language Model – 대규모 언어 모델 |
| OpenStack | Nova·Neutron·Cinder·Glance·Keystone 컴포넌트를 포함하는 IaaS 플랫폼 |
| Glance | OpenStack 이미지 서비스 |
| Nova | OpenStack 컴퓨트 서비스 |
| Neutron | OpenStack 네트워크 서비스 |
| Cinder | OpenStack 블록 스토리지 서비스 |
| Tool Calling | LLM이 외부 함수/API를 직접 호출하는 기법 |
| Redis Stream | 메시지 큐 역할을 수행하는 Redis 데이터 구조 |
| Kafka | 이벤트 스트리밍 플랫폼 (향후 확장) |
| Chroma | Vector DB – 복구 규칙 및 정책 저장소 |

---

## 2. 시스템 아키텍처 개요

### 2.1 전체 시스템 구성

```
운영자
  │ WebSocket
  ▼
Django · Horizon  ──────────────────────────────── [Plan]
  │ REST API
  ▼
AI Agent (LLM + Tool Calling) ──► Chroma (Vector DB · Rules)  ── [Confirm]
  │ Tool Call
  ▼
MCP Server (Streamable HTTP)
  │ HTTP + Auth
  ▼
FastAPI (Internal Adapter) ──► Redis  (State · Lock · TTL)      ── [Execute]
  │                       ──► Kafka  (Events · Queue)
  │                       ──► DB     (Recovery history)
  │ SDK 호출
  ▼
OpenStack (Nova · Neutron · Cinder · Glance) ──► Slack MCP     ── [Report]
                                              ──► Jira MCP
```

| 레이어 | 컴포넌트 | 역할 |
|--------|----------|------|
| Presentation | Django · Horizon | WebSocket 및 REST API 기반 운영자 UI. 복구 요청 접수 및 실시간 진행 현황 표시 |
| AI/Knowledge | AI Agent (LLM) | 복구 정책 자동 생성, Tool Calling 기반 실행 오케스트레이션, Chroma 규칙 검색 |
| AI/Knowledge | Chroma Vector DB | 과거 복구 케이스 및 정책 규칙 저장, RAG 기반 유사 사례 검색 |
| Connectivity | MCP Server | Streamable HTTP 기반 AI Agent 도구 호출 수신 및 FastAPI 위임 |
| Connectivity | FastAPI | OpenStack SDK 호출 Internal Adapter. Redis/Kafka 이벤트 발행, DB 저장 |
| State/Events | Redis | Task 상태 관리, 분산 락, TTL 기반 임시 데이터 저장 |
| State/Events | Kafka | 복구 이벤트 스트리밍 (Redis Stream에서 단계적 전환) |
| Persistence | DB (MariaDB) | 복구 이력, 태스크 로그, 보고서 데이터 영구 저장 |
| Infrastructure | OpenStack | Nova/Neutron/Cinder/Glance SDK 호출로 VM 실제 생성·관리 |
| Integration | Slack MCP | 복구 완료/실패 알림 자동 발송 |
| Integration | Jira MCP | 복구 태스크 기반 이슈 자동 생성 및 상태 업데이트 |

### 2.2 복구 실행 단계 (Phase)

| Phase | 단계명 | 주체 | 설명 |
|-------|--------|------|------|
| Plan | 복구 계획 수립 | Django + AI Agent | 운영자가 복구 대상 서버 선택, AI가 리소스 분석 및 복구 정책 초안 생성 |
| Confirm | 정책 확인 및 승인 | AI Agent + 운영자 | AI가 Chroma에서 유사 규칙 검색하여 정책 제안, 운영자 최종 승인 |
| Execute | 복구 자동 실행 | MCP → FastAPI → OpenStack | Tool Calling으로 이미지 변환·등록·VM 생성 파이프라인 자동 수행 |
| Report | 결과 보고 및 기록 | FastAPI + Slack/Jira | 복구 결과 DB 저장, Markdown 보고서 생성, Slack 알림, Jira 이슈 갱신 |

---

## 3. 기능 요구사항 (Functional Requirements)

> **우선순위 기준**
> - `필수` : MVP에 반드시 포함
> - `권장` : Phase 2 이후 구현 목표

### 3.1 운영자 UI / Frontend

#### 3.1.1 복구 대상 선택

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-UI-01 | ZIASTACK에 접속하여 복구 가능한 VM 목록을 조회할 수 있어야 한다. | 필수 | Phase 1 |
| FR-UI-02 | 복구 대상 VM을 선택하고 백업 이미지 목록(Full / ZDM / 증분)을 확인할 수 있어야 한다. | 필수 | Phase 1 |
| FR-UI-03 | WebSocket을 통해 복구 진행 상태를 실시간으로 수신하고 화면에 표시해야 한다. | 필수 | Phase 2 |
| FR-UI-04 | 복구 정책 AI 초안을 UI에서 수정·최종 승인할 수 있어야 한다. | 필수 | Phase 1 |
| FR-UI-05 | 복구 이력 목록 및 상세 보고서를 조회할 수 있어야 한다. | 필수 | Phase 2 |

---

### 3.2 AI Agent

#### 3.2.1 복구 정책 자동 생성

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-AI-01 | LLM은 소스 서버의 CPU/Memory/Disk 사양을 입력받아 복구 VM 사양 초안을 자동 생성해야 한다. | 필수 | Phase 1 |
| FR-AI-02 | Chroma Vector DB에서 유사 복구 사례 및 정책 규칙을 RAG 방식으로 검색하여 정책에 반영해야 한다. | 필수 | Phase 2 |
| FR-AI-03 | Full / ZDM / 증분 백업 유형을 자동 판별하여 적합한 복구 전략을 선택해야 한다. | 필수 | Phase 1 |
| FR-AI-04 | 복구 실패 시 원인을 분석하고 해결 방안 및 재시도 정책을 자동 제안해야 한다. | 권장 | Phase 2 |

#### 3.2.2 Tool Calling 기반 실행

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-AI-05 | AI Agent는 MCP Server를 통해 이미지 변환, Glance 등록, Nova VM 생성 도구를 순차 호출해야 한다. | 필수 | Phase 2 |
| FR-AI-06 | 각 Tool Call 결과를 다음 단계 판단에 활용하는 Multi-step Reasoning을 지원해야 한다. | 필수 | Phase 2 |
| FR-AI-07 | Engineer-in-the-Loop: 고위험 작업(VM 삭제, 네트워크 변경)은 인간 승인 후 실행해야 한다. | 필수 | Phase 1 |

---

### 3.3 MCP Server

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-MCP-01 | Streamable HTTP 방식으로 AI Agent의 Tool Call을 수신하고 FastAPI에 위임해야 한다. | 필수 | Phase 2 |
| FR-MCP-02 | Tool 목록을 동적으로 등록·해제할 수 있는 Tool Registry를 제공해야 한다. | 권장 | Phase 2 |
| FR-MCP-03 | 인증(Auth) 토큰 기반 요청 검증을 수행해야 한다. | 필수 | Phase 2 |
| FR-MCP-04 | Tool 호출 결과를 스트리밍 방식으로 AI Agent에 반환할 수 있어야 한다. | 권장 | Phase 2 |

---

### 3.4 FastAPI (Internal Adapter)

#### 3.4.1 이미지 처리

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-FA-01 | 백업 이미지 파일의 포맷(raw, qcow2, vmdk, vhd 등)을 자동 감지해야 한다. | 필수 | Phase 1 |
| FR-FA-02 | `qemu-img`를 이용해 이미지를 qcow2 포맷으로 비동기 변환해야 한다. | 필수 | Phase 1 |
| FR-FA-03 | 변환된 이미지를 Glance에 메타데이터 등록(`create_image`) 후 실제 데이터를 업로드(`upload_image`)해야 한다. | 필수 | Phase 1 |

#### 3.4.2 VM 생성 및 리소스 검증

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-FA-04 | Nova를 통해 복구 정책에 명시된 사양(flavor, network, security group)으로 VM을 생성해야 한다. | 필수 | Phase 1 |
| FR-FA-05 | VM 생성 전 하이퍼바이저 잔여 리소스(vCPU, RAM, Disk)를 검증하고 부족 시 실패 처리해야 한다. | 필수 | Phase 1 |
| FR-FA-06 | VM 생성 완료 후 ACTIVE 상태 전환을 폴링하여 결과를 확인해야 한다. | 필수 | Phase 1 |
| FR-FA-07 | Userdata를 통한 클라우드 초기화(ZConverter Agent 자동 설치 등)를 지원해야 한다. | 권장 | Phase 2 |

#### 3.4.3 이벤트 및 상태 관리

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-FA-08 | 복구 태스크를 Redis Stream에 발행하고 Worker가 비동기 처리할 수 있어야 한다. | 필수 | Phase 1 |
| FR-FA-09 | 태스크 진행 상태를 Redis에 저장하고 WebSocket을 통해 UI로 Push해야 한다. | 필수 | Phase 2 |
| FR-FA-10 | 복구 완료/실패 이벤트를 Kafka에 발행하여 외부 시스템과 연동할 수 있어야 한다. | 권장 | Phase 2 |
| FR-FA-11 | 모든 복구 이력(시작/종료 시간, 결과, 사용 이미지, 생성 VM ID)을 DB에 저장해야 한다. | 필수 | Phase 1 |

---

### 3.5 OpenStack 연동

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-OS-01 | Keystone 인증을 통해 OpenStack API 토큰을 획득하고 갱신해야 한다. | 필수 | Phase 1 |
| FR-OS-02 | `asyncio.to_thread`를 이용해 동기 OpenStack SDK 호출을 비동기로 래핑해야 한다. | 필수 | Phase 1 |
| FR-OS-03 | Neutron을 통해 복구 VM에 네트워크 포트 및 Floating IP를 할당해야 한다. | 필수 | Phase 1 |
| FR-OS-04 | Cinder를 통해 추가 블록 볼륨을 생성하고 VM에 연결할 수 있어야 한다. | 권장 | Phase 2 |

---

### 3.6 보고서 및 외부 연동

| ID | 요구사항 | 우선순위 | 출처 |
|----|----------|----------|------|
| FR-RP-01 | 복구 완료 후 Markdown/HTML 형식의 복구 보고서를 자동 생성해야 한다. | 필수 | Phase 2 |
| FR-RP-02 | 보고서에는 복구 시간, 사용 이미지, 생성 VM 사양, 성공/실패 원인이 포함되어야 한다. | 필수 | Phase 2 |
| FR-RP-03 | Slack MCP를 통해 지정 채널에 복구 결과 알림을 자동 발송해야 한다. | 필수 | Phase 2 |
| FR-RP-04 | Jira MCP를 통해 복구 태스크에 대한 이슈를 자동 생성하고 완료 시 상태를 갱신해야 한다. | 권장 | Phase 2 |
| FR-RP-05 | 복구 결과를 Chroma Vector DB에 저장하여 향후 RAG 검색에 활용해야 한다. | 권장 | Phase 2 |

---

## 4. 비기능 요구사항 (Non-Functional Requirements)

### 4.1 성능

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| NFR-P-01 | 단일 VM 복구 End-to-End 처리 시간(이미지 변환 제외)은 10분 이내이어야 한다. | 필수 |
| NFR-P-02 | 동시 복구 요청 5건을 병렬 처리할 수 있어야 한다. | 필수 |
| NFR-P-03 | FastAPI 복구 API 응답 시간(비동기 수신 확인)은 2초 이내이어야 한다. | 필수 |
| NFR-P-04 | 100GB 이미지 변환 작업이 메인 이벤트 루프를 차단하지 않아야 한다. | 필수 |

### 4.2 가용성 및 신뢰성

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| NFR-A-01 | Worker 프로세스 비정상 종료 시 Redis Stream Consumer Group의 Pending 태스크를 자동 재처리해야 한다. | 필수 |
| NFR-A-02 | OpenStack API 일시 오류 시 지수 백오프(exponential backoff) 재시도를 3회 수행해야 한다. | 필수 |
| NFR-A-03 | 이미지 변환 실패 시 중간 파일을 정리하고 명확한 오류 메시지를 반환해야 한다. | 필수 |
| NFR-A-04 | VM 생성 실패 시 생성된 Glance 이미지를 롤백(삭제)하는 보상 트랜잭션을 수행해야 한다. | 권장 |

### 4.3 보안

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| NFR-S-01 | OpenStack 자격증명(Keystone Token)은 환경변수 또는 Vault를 통해 관리하며 코드에 하드코딩하지 않는다. | 필수 |
| NFR-S-02 | MCP Server 요청은 JWT 토큰 기반 인증을 통해 검증해야 한다. | 필수 |
| NFR-S-03 | FastAPI 내부 API는 네트워크 정책을 통해 MCP Server에서만 접근 가능하도록 제한해야 한다. | 필수 |
| NFR-S-04 | 모든 API 통신은 TLS 1.2 이상을 사용해야 한다. | 필수 |

### 4.4 유지보수성

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| NFR-M-01 | 모든 컴포넌트는 Docker 컨테이너로 패키징되어야 하며 `docker-compose`로 로컬 환경을 구성할 수 있어야 한다. | 필수 |
| NFR-M-02 | 신규 Tool 추가 시 MCP Server 재배포 없이 동적 등록이 가능해야 한다. | 권장 |
| NFR-M-03 | 복구 정책 규칙(Chroma)의 추가/수정을 관리자 UI 없이 API를 통해 수행할 수 있어야 한다. | 권장 |
| NFR-M-04 | 전체 코드 커버리지 70% 이상의 단위 테스트를 작성해야 한다. | 권장 |

### 4.5 관찰 가능성 (Observability)

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| NFR-O-01 | 모든 복구 태스크에는 Trace ID를 부여하여 전 구간 로그 추적이 가능해야 한다. | 필수 |
| NFR-O-02 | 성공/실패/오류 로그는 구조화된 JSON 형식으로 출력해야 한다. | 필수 |
| NFR-O-03 | 태스크 처리 시간, 실패율 등 주요 메트릭을 수집할 수 있어야 한다. | 권장 |

---

## 5. 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| Frontend | Django + Horizon | WebSocket / REST API 기반 운영자 포털 |
| AI Agent | LLM API | 로컬 LLM 또는 외부 API (Tool Calling 지원 모델) |
| AI Agent | Chroma | Vector DB – 복구 정책 및 RAG 지식베이스 |
| Connectivity | MCP Server | Streamable HTTP – AI Agent Tool Calling 게이트웨이 |
| Backend | FastAPI | Python 3.11+, asyncio, Internal Adapter |
| Backend | asyncpg | PostgreSQL / MariaDB 비동기 드라이버 |
| Message Queue | Redis Streams | 태스크 큐, 분산 락, 실시간 상태 저장 |
| Message Queue | Kafka | 이벤트 스트리밍 (Phase 2 이후 전환) |
| Infrastructure | OpenStack SDK | Nova / Neutron / Cinder / Glance / Keystone |
| Infrastructure | qemu-img | VM 디스크 이미지 포맷 변환 |
| Infra as Code | Terraform | OpenStack 리소스 프로비저닝 템플릿 |
| Container | Docker / Compose | 개발·테스트 환경 컨테이너화 |
| Reporting | Jinja2 | Markdown/HTML 보고서 템플릿 |
| Integration | Slack MCP | 운영 알림 자동화 |
| Integration | Jira MCP | 복구 이슈 추적 자동화 |

---

## 6. 개발 일정 (3개월 / 12주)

| 주차 | 핵심 목표 | 주요 산출물 | Phase |
|------|-----------|-------------|-------|
| 1주 | 기존 수동 복구 프로세스 분석, 타깃 시나리오 정의 | 복구 시나리오 문서, 환경 구성 가이드 | Phase 1 |
| 2주 | AI 복구 프로세스 설계, 정책 추진/승인 구조 정의 | 아키텍처 설계서, 정책 흐름도 | Phase 1 |
| 3주 | 데이터 모델 및 정책 정의, 복구 단위 프로퍼티 정의 | DB 스키마, API 인터페이스 명세 | Phase 1 |
| 4주 | OpenStack 연결 기초 구현, SDK 검증 및 API 테스트 | OpenStack 연결 모듈, VM/Volume 조회 API | Phase 1 |
| 5주 | 정책 수립 로직 구현, AI 정책 추론 프로토타입 | 복구 정책 생성 API, 파라미터 검증 로직 | Phase 1 |
| 6주 | Tool Calling 템플릿 구성, SDK Wrapper 완성 | MCP Tool 목록, SDK Wrapper 코드 | Phase 1 |
| 7주 | Target VM 자동 생성 구현, Same-Spec VM 생성 | Nova VM 자동 생성 기능, 리소스 검증 로직 | Phase 2 |
| 8주 | 복구 상태 및 상세 수집, 실패 로그 저장 | 상태 수집 Worker, 실패 분석 보고 기능 | Phase 2 |
| 9주 | 리포트 자동화 구현, AI 경과/결과 정보 정리 | 자동 보고서 생성 기능, Summary 템플릿 | Phase 2 |
| 10주 | 장애 분석 RAG 구축, 과거 로그/케이스 벡터화 | Chroma 지식베이스, 유사 사례 검색 API | Phase 2 |
| 11주 | 벡터DB 지식 축적, 정책 지식베이스 자동 갱신 | 지식 자동 축적 파이프라인 | Phase 2 |
| 12주 | 통합 테스트 및 시연 준비, 최종 데이터 확정 | 최종 통합 테스트 결과, 시연 시나리오 | Phase 2 |

### 6.1 마일스톤

| 마일스톤 | 목표 주차 | 달성 기준 |
|----------|-----------|-----------|
| M1: OpenStack 연동 완료 | 4주 차 | Nova VM 조회 및 기본 생성 API 동작 확인 |
| M2: AI 기반 복구 정책 생성 | 5~6주 차 | LLM Tool Calling으로 복구 정책 초안 자동 생성 성공 |
| M3: End-to-End 복구 자동화 | 7주 차 | 백업 이미지 → Glance 등록 → Nova VM 생성 전 과정 자동 완료 |
| M4: 모니터링 + 보고서 | 9주 차 | 복구 결과 DB 저장 + Slack 알림 + HTML 보고서 자동 생성 |
| M5: 최종 통합 검증 | 12주 차 | 전체 시나리오 E2E 테스트 통과, 성능 요구사항 충족 |

---

## 7. 인터페이스 요구사항

### 7.1 주요 API 엔드포인트 (FastAPI)

| Method | Endpoint | 설명 | 우선순위 |
|--------|----------|------|----------|
| `POST` | `/api/v1/recovery/start` | 복구 태스크 시작 – 이미지 경로, 복구 정책, 대상 하이퍼바이저 수신 | 필수 |
| `GET` | `/api/v1/recovery/{task_id}/status` | 태스크 현재 상태 조회 (PENDING / RUNNING / SUCCESS / FAILED) | 필수 |
| `GET` | `/api/v1/recovery/history` | 복구 이력 목록 조회 (페이지네이션) | 필수 |
| `POST` | `/api/v1/image/convert` | 이미지 포맷 변환 요청 (비동기) | 필수 |
| `POST` | `/api/v1/image/register` | Glance에 이미지 등록 및 업로드 | 필수 |
| `POST` | `/api/v1/vm/create` | Nova VM 생성 요청 (복구 정책 기반) | 필수 |
| `GET` | `/api/v1/vm/{vm_id}` | 생성된 VM 상태 및 상세 정보 조회 | 필수 |
| `POST` | `/api/v1/policy/recommend` | AI Agent에 복구 정책 추천 요청 | 필수 |
| `POST` | `/api/v1/report/generate` | 복구 완료 보고서 생성 | 필수 |

### 7.2 WebSocket 이벤트 (Django → UI)

| 이벤트 | 페이로드 | 발생 시점 |
|--------|----------|-----------|
| `recovery.status_update` | `{ task_id, status, progress, message }` | 태스크 상태 변경 시마다 |
| `recovery.completed` | `{ task_id, vm_id, duration, report_url }` | 복구 성공 완료 시 |
| `recovery.failed` | `{ task_id, error_code, error_message, suggestion }` | 복구 실패 시 |
| `image.convert_progress` | `{ task_id, percent, elapsed }` | 이미지 변환 진행 중 |

---

## 8. 제약 사항 및 가정

### 8.1 제약 사항

- ZIASTACK(OpenStack) 환경에서만 동작하며 타 IaaS 플랫폼(AWS, Azure 등)은 현 범위에서 제외한다.
- 이미지 변환 도구(`qemu-img`)는 복구 실행 서버에 설치되어 있어야 한다.
- AI Agent가 사용하는 LLM은 Tool Calling 기능을 지원해야 한다.
- Redis 및 Kafka 클러스터는 외부 인프라에서 별도 운영된다고 가정한다.
- 초기 릴리스(Phase 1)에서는 Redis Stream을 사용하며, Kafka로의 전환은 Phase 2 이후 진행한다.

### 8.2 가정

- 운영자는 ZIASTACK 관리자 권한을 보유하고 있다.
- 백업 이미지 파일은 복구 실행 서버에서 직접 접근 가능한 경로에 위치한다.
- Slack 및 Jira 연동을 위한 API 키는 사전에 발급되어 있다.
- 복구 정책 규칙의 초기 데이터(Chroma Seed)는 인프라팀이 사전 입력한다.

---

## 9. 문서 변경 이력

| 버전 | 변경일 | 작성자 | 변경 내용 |
|------|--------|--------|-----------|
| v1.0 | 2026-05-07 | 팀장 | 최초 작성 – 전체 요구사항 초안 정의 |

---

*— 문서 끝 —*