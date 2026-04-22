"""
OpenStack MCP Server Mock
1차 구현에서 실제 MCP Server 대신 사용.
2차에서 실제 OpenStack MCP Server로 교체 예정.
"""


def get_server_info(server_name: str) -> dict:
    """서버 정보 Mock 응답"""
    return {
        "server_name": server_name,
        "exists":      True,
        "vcpus":       4,
        "ram_mb":      8192,
        "disk_gb":     100,
        "status":      "ERROR",
        "image_id":    "img-mock-001",
        "network_id":  "net-mock-001",
    }


def search_runbook(query: str) -> str:
    """런북 RAG Mock 응답"""
    return """
[런북 #1] VM 장애 복구 절차
1. 백업 이미지 존재 여부 확인 (Glance)
2. 신규 VM 생성 (Nova) — 동일 스펙 기준
3. Userdata로 ZConverter Agent 자동 설치
4. 복구 작업 진행 확인
5. 네트워크 연결 검증 후 완료 처리

[런북 #2] 복구 실패 시 대응
- 이미지 손상: 이전 백업 이미지로 재시도
- 리소스 부족: Flavor 다운그레이드 후 재시도
- Agent 설치 실패: 수동 개입 요청
""".strip()


def create_vm(spec: dict) -> dict:
    """VM 생성 Mock 응답"""
    return {
        "success":   True,
        "server_id": "vm-mock-001",
        "status":    "ACTIVE",
        "message":   f"VM {spec.get('server_name', 'unknown')} 생성 완료",
    }


def execute_recovery(policy: dict) -> dict:
    """복구 실행 Mock 응답"""
    return {
        "success":   True,
        "server_id": policy.get("server_name", "unknown"),
        "message":   "복구 작업 완료",
        "elapsed":   120,
    }


def get_recovery_status(session_id: str) -> dict:
    """복구 상태 조회 Mock 응답"""
    return {
        "session_id": session_id,
        "status":     "executing",
        "progress":   80,
        "message":    "ZConverter Agent 복구 진행 중",
    }