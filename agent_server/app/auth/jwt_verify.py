import jwt
from fastapi import HTTPException
from redis.asyncio import Redis
from app.common.config import settings
from app.auth.schema import TokenPayload

def load_public_key() -> str:
    with open(settings.public_key_path, "r") as f:
        return f.read()
    
PUBLIC_KEY = load_public_key()

async def verify_jwt(token: str, redis: Redis) -> TokenPayload:
    """
    1. `iss == "horizon-django"` 확인
    2. `aud == "ai-gateway"` 확인
    3. `exp > now` 만료 확인 (clock skew ±10초 허용)
    4. `jti` Redis에서 중복 확인 (replay 방지, `chat:jti:{jti}` 키 존재 시 거부)
    5. `session_id` Redis에서 세션 존재 확인 → 없으면 403
    6. `required_roles` 검증 (MCP 도구별) — `roles` 중 하나라도 포함 시 통과
    """
    try:
        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            leeway=settings.jwt_leeway,
            options={"require": ["exp", "iat", "jti", "sub"]}
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "토큰 만료")
    except jwt.InvalidAudienceError:
        raise HTTPException(401, "잘못된 audience")
    except jwt.InvalidSignatureError:
        raise HTTPException(401, "서명 검증 실패")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"유효하지 않은 토큰: {str(e)}")
    
    if payload.get("iss") != settings.jwt_issuer:
        raise HTTPException(401, "잘못된 issuer")
    
    session_id = payload.get("session_id")
    session_key = f"chat:session:{session_id}"
    if not await redis.exists(session_key):
        raise HTTPException(403, "세션 없음 또는 만료")
    
    jti = payload.get("jti")
    jti_key = f"chat:jti:{jti}"
    is_first = await redis.set(
        jti_key,
        "1",
        nx=True,    # 키가 없을 때만 쓰기
        ex=settings.jwt_jti_ttl
    )
    
    if not is_first:
        raise HTTPException(409, "이미 사용된 토큰(replay)")
    
    return TokenPayload(**payload)