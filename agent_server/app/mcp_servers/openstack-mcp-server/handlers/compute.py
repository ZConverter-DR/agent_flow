import asyncio
import openstack
from openstack.exceptions import DuplicateResource

# token은 token_id를 명칭함
def _make_conn(auth_url: str, token: str, project_id: str):
    return openstack.connect(
        auth_url=auth_url,
        auth_type="token",
        token=token,
        project_id=project_id,
    )

async def handle_get_server_info(server_id: str, auth_url: str, token: str, project_id: str) -> dict:
    loop = asyncio.get_event_loop()
    with await loop.run_in_executor(None, lambda: _make_conn(auth_url, token, project_id)) as conn:
        try:
            result = await loop.run_in_executor(
                # find_server() 처럼 find_ 로직 함수들은 id, name으로 둘다 서칭 가능
                None, lambda: conn.compute.find_server(server_id)
            )
        except DuplicateResource:
            servers = await loop.run_in_executor(
                None, lambda: list(conn.compute.servers(name=server_id))
            )
            return {
                "action": "select_required",
                "message": f"'{server_id}' 이름의 서버가 {len(servers)}개 있습니다.",
                "candidates": [
                    {
                        "index": i + 1,
                        "id": s.id,
                        "status": s.status,
                        "host": s.hypervisor_hostname,
                        "created_at": s.created_at,
                    }
                    for i, s in enumerate(servers)
                ],
            }

        if result is None:
            return {"error": f"서버를 찾을 수 없습니다: {server_id}"}
        return result.to_dict()


async def handle_create_vm(
    name: str,
    flavor_id: str,
    image_id: str,
    network_id: str,
    auth_url: str,
    token: str,
    project_id: str,
) -> dict:
    loop = asyncio.get_event_loop()
    with await loop.run_in_executor(None, lambda: _make_conn(auth_url, token, project_id)) as conn:
        try:
            image = await loop.run_in_executor(
                None, lambda: conn.compute.find_image(image_id)
            )
            if image is None:
                return {"error": f"이미지를 찾을 수 없습니다: {image_id}"}

            network = await loop.run_in_executor(
                None, lambda: conn.network.find_network(network_id)
            )
            if network is None:
                return {"error": f"네트워크를 찾을 수 없습니다: {network_id}"}

            flavor = await loop.run_in_executor(
                None, lambda: conn.compute.find_flavor(flavor_id)
            )
            if flavor is None:
                return {"error": f"Flavor를 찾을 수 없습니다: {flavor_id}"}

            result = await loop.run_in_executor(
                None,
                lambda: conn.compute.create_server(
                    name=name,
                    flavor_id=1,
                    image_id=image.id,
                    networks=[{"uuid": network_id}],
                ),
            )
        except Exception as e:
            return {"error": f"VM 생성 중 오류가 발생했습니다: {str(e)}"}

    return result.to_dict()
