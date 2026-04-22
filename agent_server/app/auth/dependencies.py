# app/dependencies/auth.py
from fastapi import Depends, Header, HTTPException
from redis.asyncio import Redis
from app.common.redis import get_redis
from app.auth.jwt_verift import verify_jwt
from app.auth.schema import TokenPayload

async def get_current_user(
    authorization: str = Header(...),           # "Bearer <token>"
    redis: Redis = Depends(get_redis),
) -> TokenPayload:

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer 토큰 필요")

    token = authorization.removeprefix("Bearer ")
    return await verify_jwt(token, redis)


def require_roles(*required: str):
    """
    특정 역할이 필요한 엔드포인트에 사용
    예: Depends(require_roles("ai_user", "admin"))
    """
    async def role_checker(
        user: TokenPayload = Depends(get_current_user)
    ) -> TokenPayload:
        if not any(r in user.roles for r in required):
            raise HTTPException(
                403,
                f"필요한 역할: {list(required)}, 보유 역할: {user.roles}"
            )
        return user
    return role_checker