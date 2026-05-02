# from = 어디에서 가져올지 지정 / import = 무엇을 가져올지 지정한다.
# from 뒤엔 파일 경로가 위치한다.
# import 뒤엔 보통 객체, 함수, 경로의 leaf 모듈이 위치한다.
import redis.asyncio
from app.common.config import settings

redis_client = redis.asyncio.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True
)

# -> redis.asyncio.Redis:는 함수의 반환 타입을 나타낸다.
async def get_redis() -> redis.asyncio.Redis:
    return redis_client