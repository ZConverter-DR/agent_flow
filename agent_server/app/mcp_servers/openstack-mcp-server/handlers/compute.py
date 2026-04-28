import asyncio
import uuid
from datetime import datetime


async def handle_get_server_info(server_id: str) -> dict:
    # Mock: 실제로는 openstacksdk conn.compute.get_server(server_id)
    await asyncio.sleep(0.1)

    mock_servers = {
        "a1b2c3d4-0001": {
            "id": "a1b2c3d4-0001",
            "name": "web-server-01",
            "status": "ACTIVE",
            "flavor": "m1.small",
            "ip_addresses": {"default": [{"addr": "192.168.1.10"}]},
            "created": "2025-04-01T09:00:00Z",
        },
        "a1b2c3d4-0002": {
            "id": "a1b2c3d4-0002",
            "name": "db-server-01",
            "status": "ERROR",
            "flavor": "m1.large",
            "ip_addresses": {"default": [{"addr": "192.168.1.11"}]},
            "created": "2025-03-15T12:00:00Z",
        },
    }

    server = mock_servers.get(server_id)
    if not server:
        return {"error": f"Server {server_id} not found"}

    return server


async def handle_create_vm(
    name: str,
    flavor: str,
    image_id: str,
    network_id: str,
) -> dict:
    # Mock: 실제로는 conn.compute.create_server(..., user_data=userdata)
    await asyncio.sleep(0.3)

    new_id = str(uuid.uuid4())

    return {
        "id": new_id,
        "name": name,
        "status": "BUILD",
        "flavor": flavor,
        "image_id": image_id,
        "network_id": network_id,
        "created": datetime.utcnow().isoformat() + "Z",
        "note": "ZConverter AI Agent will be installed via cloud-init on first boot",
    }