from typing import Literal
from pydantic import BaseModel, Field

class RouteDecision(BaseModel):
    """intent 분류 결과"""
    intent: Literal[
        "recover_server",   # 복구 플로우 진행
        "direct_response",  #단순 응답/조회
    ]
    server_id: str | None = Field(
        default=None, description="복구 대상 서버 ID. 요청에 명시된 경우만 추출."
    )
    
class RecoveryPolicy(BaseModel):
    """복구 VM 생성 정책"""
    name: str = Field(description="새 VM 이름")
    flavor: Literal[
        "m1.tiny", "m1.small", "m1.medium", "m1.large", "m1.xlarge"
    ] = Field(description="VM 사양")
    image_id: str = Field(description="부팅 이미지 ID")
    network_id: str = Field(description="네트워크 ID")
    recovery_type: Literal[
        "snapshot_restore", "fresh_install", "config_replicate"
    ] = Field(description="복구 방식")
    reason: str = Field(description="해당 정책을 선택한 이유")