from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# class Settings(BaseSettings): <- 이 문법은 파이썬에선 
# Settings 클래스가 BaseSettings 클래스를 상속한다는 뜻이다.
# java에선 class Settings extends BaseSettings {~}게 표현한다.

# BaseSettings는 pydantic이 제공하는 설정 클래스이다.
# Settings 객체 생성 시 클래스에 선언된 필드 값을 OS 환경변수 또는 
# .env 파일에서 읽어온다.
# 기본값이 없는 필드는 필수 설정값으로 환경변수/.env에 없으면 
# 검증 에러가 발생한다.
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