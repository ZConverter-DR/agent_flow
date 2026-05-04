import openstack
import json

SERVER_ID = "d496c2d1-6df3-4147-825d-6f8fcf80ecb1"
OUTPUT_FILE = "server_info.txt"
OUTPUT_FILE2 = "image_info.txt"
OUTPUT_FILE3 = "network_info.txt"

conn = openstack.connect(cloud="devstack-admin")
server = conn.compute.get_server(SERVER_ID)
image = conn.image.get_image(server.image.id)
network = conn.network.ports(device_id=SERVER_ID)

with open(OUTPUT_FILE, "w") as f:
    f.write(json.dumps(dict(server), indent=2, default=str))
    
with open(OUTPUT_FILE2, "w") as f:
    f.write(json.dumps(dict(image), indent=2, default=str))

with open(OUTPUT_FILE2, "w") as f:
    f.write(json.dumps(dict(network), indent=2, default=str))

print(f"서버 정보가 {OUTPUT_FILE}에 저장되었습니다.")
