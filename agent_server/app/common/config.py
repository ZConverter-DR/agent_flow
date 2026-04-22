from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    ollama_base_url: Optional[str] = None
    notion_api_key: Optional[str] = None
    slack_bot_token: Optional[str] = None
    slack_team_id: Optional[str] = None
    
    redis_host: str
    redis_port: int
    public_key_path: str   
    
    # JWT 검증
    jwt_issuer: str = "horizon-django"
    jwt_audience: str = "ai-gateway"
    jwt_leeway: int = 10  # clock skew 허용 시간
    jwt_jti_ttl: int = 120  # redis jti ttl
    jwt_algorithm: str

    model_config = SettingsConfigDict(
        env_file = ".env",
        extra="ignore"	# Docker용 변수 무시 (위에 정의해둔 변수말고는 무시)
    )

settings = Settings()