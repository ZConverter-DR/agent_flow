🟢 Django 측 구현 목록 (Horizon)
장고는 주로 인증/권한의 단일 진실 공급원(SSOT) 역할과 사후 처리(로깅/승인 검증) 역할을 담당합니다.

1. JWT 발급 엔드포인트 (GET /ai/session/issue)
[ ] API 작성: 현재 로그인된 Horizon 사용자의 정보를 조회하여 60초 만료되는 단기 JWT 생성 후 반환.
[ ] Payload 구성: sub(사용자 ID), roles(오픈스택 권한), session_id(Redis 키용), jti(랜덤 uuid) 포함.
[ ] 서명 로직: 사전에 공유된 비밀키(HS256)를 사용해 서명.
2. 세션 메타데이터 Redis 적재 (세션 훅)
[ ] 로그인/갱신 훅 연동: 사용자가 Horizon에 로그인하거나 활성 상태일 때, Redis에 chat:session:{session_id} JSON 데이터를 저장.
[ ] 토큰 공유: JSON 안에 사용자의 keystone_token(평문)을 포함시켜 FastAPI가 나중에 이를 열어볼 수 있도록 환경 구성. (TTL: 1시간 수준)
3. 파괴적 작업 승인 API (POST /ai/confirm)
[ ] API 작성: UI(채팅창 모달)에서 승인 이벤트가 들어오면, POST 요청을 받아 처리하는 뷰 작성.
[ ] 보안 검증: Django의 @csrf_protect 및 로그인 세션 검증을 태워 올바른 권한자가 승인했는지 확인.
[ ] Redis 연동: 검증 통과 시 chat:confirm:{confirm_id} 의 값을 "approved" 로 변경하고, PUBLISH chat:confirm:events 로 FastAPI에 방송(알림) 발송.
4. 비동기 감사 로그 파이프라인 (Celery / Admin)
[ ] 모델 생성: audit_log.md에 명시된 AuditLog 장고 DB 모델 생성 및 마이그레이션 적용.
[ ] Celery Task 작성: 10초마다 RPOP chat:audit:queue 를 수행해 모아둔 로그 데이터를 파싱하여 DB에 Bulk Insert 하는 Task 작성.
[ ] 장고 어드민 등록: 관리자가 볼 수 있도록 admin.py 에 등록하고 필터링 로직 추가.


🔵 FastAPI 측 구현 목록 (AI Gateway)
FastAPI는 LLM을 이용해 사용자의 자연어를 해석하고, MCP를 실행하는 핵심 스트리밍 엔진 역할을 담당합니다.

1. 보안/인증 미들웨어 구축
[ ] JWT 검증: 모든 요청(Authorization: Bearer <token>)의 서명과 만료 시각(60초)을 검사하는 Dependency 작성.
[ ] Replay 방지: Redis의 chat:jti:{jti} 키 유무를 검사해 재사용된 토큰인지 차단하는 로직.
2. 핵심 채팅 엔드포인트 (POST /v1/chat/completions)
[ ] SSE 스트리밍: PydanticAI 또는 LangGraph를 연결하여 LLM의 생성 텍스트를 실시간 청크 전송.
[ ] History 관리 구조: Redis의 chat:session:{session_id}:history 에 LRANGE / RPUSH를 사용하여 채팅 컨텍스트 유지.
3. 고도화된 MCP 도구 (Tools) 메타데이터 제어기, MCP client로 다양한 MCP Server 호출
[ ] 메타데이터 파서: destructive, requires_confirmation, required_roles 등의 옵션을 읽어들이는 기능.
[ ] 실행 보류 로직 (Hold & Pub/Sub):
위험한 작업 감지 시 실행을 멈추고 UI에 confirm_required 이벤트 발행.
Redis Pub/Sub을 Subscribe 한 뒤, asyncio.sleep이나 await 상태로 장고의 승낙/거절 결정을 기다리는 비동기 로직 구현.
[ ] 장시간 작업 대처 (Timeout 우회):
1~2분이 넘어가는 무거운 스크립트는 백그라운드 태스크로 던진 후, UI에 job_started (job_id) 이벤트를 넘겨주고 종료하는 폴링 우회 처리. (GET /v1/jobs/{id} 전용 엔드포인트 포함)
4. 사후 감사 로깅 시스템
[ ] 변수 마스킹 로직: 도구 실행 직후, 인자 값 중에 password, key 같은 민감 정보가 있으면 "***MASKED***"로 치환.
[ ] Audit Push: 작업 성공/실패 여부를 JSON으로 파싱해 Redis chat:audit:queue에 LPUSH로 던지고 잊어버리는(Fire and Forget) 로직 구축.