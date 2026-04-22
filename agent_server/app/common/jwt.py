from jose import jwt, JWTError
from app.common.config import settings
from fastapi import HTTPException

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(
            toekn,
            settings.ai_jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")