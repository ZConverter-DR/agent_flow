import asyncio
import uuid

# Mock job store: 실제로는 DB나 Redis
_job_store: dict[str, dict] = {}


async def handle_execute_recovery(
    server_id: str,
    recovery_type: str,
    reason: str,
) -> dict:
    # Mock: 실제로는 VM 내 ZConverter AI Agent API 호출
    # e.g. httpx.post(f"http://{vm_ip}:8080/recovery", ...)
    await asyncio.sleep(0.2)

    # 존재하지 않는 서버 체크
    if server_id not in ["a1b2c3d4-0001", "a1b2c3d4-0002"]:
        return {"error": f"Server {server_id} not found"}

    job_id = str(uuid.uuid4())

    _job_store[job_id] = {
        "job_id": job_id,
        "server_id": server_id,
        "recovery_type": recovery_type,
        "reason": reason,
        "status": "PENDING",
        "progress": 0,
        "logs": [f"Recovery job created: {recovery_type} on {server_id}"],
    }

    return {
        "job_id": job_id,
        "status": "PENDING",
    }


async def handle_get_recovery_status(job_id: str) -> dict:
    # Mock: 실제로는 ZConverter AI Agent에 job 상태 polling
    # e.g. httpx.get(f"http://{vm_ip}:8080/recovery/{job_id}")
    await asyncio.sleep(0.1)

    job = _job_store.get(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}

    # Mock 진행 시뮬레이션: 호출할 때마다 progress 증가
    if job["status"] == "PENDING":
        job["status"] = "RUNNING"
        job["progress"] = 30
        job["logs"].append("Agent received recovery request")

    elif job["status"] == "RUNNING" and job["progress"] < 100:
        job["progress"] = min(job["progress"] + 40, 100)
        job["logs"].append(f"Progress: {job['progress']}%")

        if job["progress"] >= 100:
            job["status"] = "SUCCESS"
            job["logs"].append("Recovery completed successfully")

    return {
        "job_id": job["job_id"],
        "server_id": job["server_id"],
        "recovery_type": job["recovery_type"],
        "status": job["status"],
        "progress": job["progress"],
        "logs": job["logs"],
    }