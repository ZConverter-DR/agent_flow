# app/schemas/auth.py
from pydantic import BaseModel

class TokenPayload(BaseModel):
    iss:        str
    aud:        str
    sub:        str          # Keystone user_id
    project_id: str
    username:   str
    roles:      list[str]
    scope:      str
    session_id: str
    jti:        str
    iat:        int
    exp:        int