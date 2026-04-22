from dataclasses import dataclass
from fastapi import WebSocket
from redis.asyncio import Redis

@dataclass
class DRDeps:
    websocket: WebSocket
    redis: Redis
    session_id: str
    mcp_url: str