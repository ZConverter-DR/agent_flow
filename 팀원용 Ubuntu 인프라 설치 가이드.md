# 팀원용 Ubuntu 인프라 설치 가이드

** 김운강 정리 : 내용을 최대한 정리해보면 아래와 같습니다 !
1) github에서 해당 코드 pull
```
git pull origin feature/rag
```
2) notion에 올린 .env 코드 가져와서 루트에 파일 생성
```
미차님이 생성하진 notion에 .env 파일 값 넣어놨습니다.
```
3) 개발 환경에서 ollama LLM 런타임 플랫폼 설치
``` bash
# 0. ollama server를 설치할 수 있는 tool 설치
sudo apt-get install zstd

# 1. Ollama 설치
curl -fsSL https://ollama.com/install.sh | sh

# 3. Ollama 서버 실행 확인 또는 실행
# 0.0.0.0으로 띄우면 해당 network가 가진 모든 ip:11434를 
# 통해서 OLLAMA_HOST에 접근할 수 있다.
OLLAMA_HOST=0.0.0.0:11434 ollama serve

# 2. Ollama 설치 확인
ollama --version
```
4) 설치된 ollama LLM에 qwen2.5:7b 설치
``` bash
# `1 qwen2.5:7b 모델 다운로드
ollama pull qwen2.5:7b

# 2. 설치된 llm 목록 확인 가능
ollama list
```
5) ollama IP를 .env에 하드코딩 후 이를 agent.py의 13번째 줄에 변수로 사용
``` bash
# host IP를 확인한 다음 11434 port로 하드코등 하시면 됩니다.
hostname -I 
```
6) 이후 docker compose를 사용하여 fastAPI 및 redis container 실행
``` bash
# docker compose를 실행하는 코드에요
docker compose up --build -d 

# docker compose로 생성한 container 및 network를 제거해줘요
docker compose down

# fastAPI container의 로그를 실시간으로 터미널에 띄어줘요
# 해당 코드를 통해서 채팅이 fastAPI로 잘 전달되는지 확인할 수 있습니다.
sudo docker logs -f zconvertproject-agent_server-1
```
7) 채팅 페이지에 들어가서 세션 발급 받은 뒤 채팅 테스트
```
저는 ollama terminal이랑 container terminal 두 개 띄어놓고 테스트 했습니다.
```

<br></br>

이 문서는 **코드는 이미 받은 상태**에서, 팀원이 Ubuntu 개발 환경에 이 프로젝트를 실행하기 위해 필요한 인프라를 최대한 빠르게 설치할 수 있도록 정리한 문서다.

현재 전제는 아래와 같다.

1. GitHub에는 코드만 올라가 있다.
2. `.env`는 GitHub에 없으므로 별도 경로로 받아야 한다.
3. `secrets/` 아래의 JWT 키 파일도 GitHub에 없으므로 별도 경로로 받아야 한다.
4. Ollama는 각자 로컬 Ubuntu에 설치하고 `qwen2.5:7b` 모델을 직접 pull 해야 한다.
5. `docker compose` 실행 전에, 각자 머신의 Ollama IP를 확인해서 `docker-compose.yml`에 **하드코딩**해야 한다.

---

## 1. 팀원이 받아야 하는 것

코드만 받아서는 바로 실행되지 않는다. 아래 파일/정보를 추가로 받아야 한다.

### 필수

1. 프로젝트 코드
2. `.env`
3. `secrets/private_key.pem`
4. `secrets/public_key.pem`

### 권장 전달 방식

1. 코드는 GitHub
2. `.env`는 Notion, 1Password, 사내 문서, 메신저 파일 전송 등 별도 루트
3. `secrets/private_key.pem`, `secrets/public_key.pem`도 GitHub가 아닌 별도 루트

### 주의

`.env`와 `secrets/`는 민감 정보이므로 GitHub에 올리면 안 된다.

---

## 2. 팀원이 최종적으로 해야 하는 일

Ubuntu에서 아래 6단계를 끝내면 된다.

1. Docker 설치
2. Ollama 설치
3. `ollama pull qwen2.5:7b`
4. 프로젝트 코드 clone
5. `.env`와 `secrets/` 파일 복사
6. Ollama IP를 `docker-compose.yml`에 하드코딩한 뒤 `docker compose up -d --build`

---

## 3. 가장 빠른 설치 방법

아래 순서로 진행하면 된다.

### 3.1 1차 설치 스크립트

이 스크립트는 Ubuntu에 아래를 설치한다.

1. Docker Engine
2. Docker Compose Plugin
3. Ollama

주의:
- 팀 합의상 "Docker Desktop"을 쓰고 싶으면 따로 설치해도 된다.
- 하지만 **이 프로젝트를 실행하는 데 필요한 것은 사실상 Docker Engine + Compose Plugin** 이므로, Ubuntu에서는 아래 스크립트가 더 단순하고 안정적이다.

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] apt 패키지 업데이트"
sudo apt-get update

echo "[2/6] 기본 패키지 설치"
sudo apt-get install -y ca-certificates curl gnupg lsb-release

echo "[3/6] Docker 저장소 키 등록"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "[4/6] Docker 저장소 등록"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "[5/6] Docker 설치"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[6/6] Ollama 설치"
curl -fsSL https://ollama.com/install.sh | sh

echo
echo "설치 완료"
echo "다음 명령으로 docker 권한을 반영하세요:"
echo "  sudo usermod -aG docker \$USER"
echo "그 후 반드시 로그아웃 후 다시 로그인하세요."
```

예시 파일명:

```bash
setup_ubuntu_infra.sh
```

실행:

```bash
chmod +x setup_ubuntu_infra.sh
./setup_ubuntu_infra.sh
```

---

## 4. Docker Desktop을 꼭 써야 하는 경우

Ubuntu에서도 Docker Desktop을 쓸 수는 있지만, 이 프로젝트는 `docker compose`만 있으면 되므로 필수는 아니다.

그래도 팀 규칙상 Docker Desktop을 맞추고 싶다면 다음 원칙만 지키면 된다.

1. Docker Desktop 설치
2. `docker compose version`이 정상 출력되는지 확인
3. 이후 절차는 이 문서의 나머지와 동일

즉, 이 프로젝트 관점에서는 **Desktop이냐 Engine이냐보다 `docker compose`가 정상 동작하는지가 중요하다.**

---

## 5. Ollama 설치 후 반드시 할 일

### 5.1 Ollama 서비스 확인

```bash
ollama serve
```

보통 이미 서비스로 떠 있으면 따로 유지할 필요는 없다. 새 터미널에서 아래로 확인하면 된다.

```bash
curl http://127.0.0.1:11434/api/tags
```

### 5.2 모델 pull

```bash
ollama pull qwen2.5:7b
```

확인:

```bash
ollama list
```

여기서 `qwen2.5:7b`가 보여야 한다.

---

## 6. 프로젝트 실행 전에 받아야 하는 파일

프로젝트 루트 기준으로 아래 구조가 준비되어 있어야 한다.

```text
ZconvertProject/
├─ .env
├─ docker-compose.yml
├─ secrets/
│  ├─ private_key.pem
│  └─ public_key.pem
└─ agent_server/
```

### `.env`

이 파일은 GitHub에 없으므로 별도 전달해야 한다.

현재 코드 기준으로 최소한 아래 계열 값이 들어 있다.

1. `PUBLIC_KEY_PATH`
2. `REDIS_HOST`
3. `REDIS_PORT`
4. `JWT_ALGORITHM`
5. `DEV_CHAT_ENABLED`
6. Slack / Notion 관련 값들

주의:
- 현재 `docker-compose.yml`에서 `OLLAMA_BASE_URL`은 별도 environment로 덮어쓰고 있으므로, `.env`의 `OLLAMA_BASE_URL`만 믿으면 안 된다.
- 실제 컨테이너는 `docker-compose.yml`의 `environment.OLLAMA_BASE_URL`을 사용한다.

### `secrets/`

반드시 있어야 한다.

1. `secrets/private_key.pem`
2. `secrets/public_key.pem`

이 프로젝트의 dev JWT 발급/검증이 이 키 파일에 의존한다.

---

## 7. Ollama IP를 하드코딩해야 하는 이유

현재 `docker-compose.yml`의 `agent_server`는 아래처럼 `OLLAMA_BASE_URL`을 직접 넣는 구조다.

```yaml
environment:
  OLLAMA_BASE_URL: "http://172.25.231.96:11434/v1"
```

문제는 이 IP가 **각 팀원 Ubuntu 머신마다 다를 수 있다**는 점이다.

즉, 각자 자신의 머신에서 Ollama가 접근 가능한 IP를 확인한 뒤 그 값을 직접 바꿔야 한다.

---

## 8. Ubuntu에서 Ollama IP 확인 방법

### 가장 단순한 방법

```bash
hostname -I
```

예시:

```bash
172.25.231.96
```

혹은 좀 더 자세히 보려면:

```bash
ip -4 addr show
```

보통 `eth0` 또는 메인 네트워크 인터페이스의 IPv4 주소를 사용하면 된다.

---

## 9. `docker-compose.yml`에 Ollama IP 하드코딩하기

프로젝트 루트에서 아래처럼 수정한다.

```yaml
agent_server:
  build: ./agent_server
  depends_on:
    - redis
  env_file:
    - ".env"
  environment:
    OLLAMA_BASE_URL: "http://내_머신_IP:11434/v1"
```

예시:

```yaml
environment:
  OLLAMA_BASE_URL: "http://172.25.231.96:11434/v1"
```

---

## 10. 최대한 딸깍으로 처리하는 프로젝트 설정 스크립트

아래 스크립트는 팀원이 아래 작업을 한 번에 할 수 있게 도와준다.

1. 현재 Ubuntu IP 확인
2. `docker-compose.yml`의 `OLLAMA_BASE_URL` 자동 치환
3. `.env` 존재 여부 확인
4. `secrets/private_key.pem`, `secrets/public_key.pem` 존재 여부 확인
5. `docker compose up -d --build` 실행

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$PWD}"
cd "$PROJECT_ROOT"

if [[ ! -f "docker-compose.yml" ]]; then
  echo "docker-compose.yml이 없습니다. 프로젝트 루트에서 실행하세요."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo ".env가 없습니다. 별도 전달받은 .env를 프로젝트 루트에 넣어주세요."
  exit 1
fi

if [[ ! -f "secrets/private_key.pem" ]]; then
  echo "secrets/private_key.pem이 없습니다."
  exit 1
fi

if [[ ! -f "secrets/public_key.pem" ]]; then
  echo "secrets/public_key.pem이 없습니다."
  exit 1
fi

HOST_IP="$(hostname -I | awk '{print $1}')"

if [[ -z "$HOST_IP" ]]; then
  echo "호스트 IP를 자동으로 찾지 못했습니다."
  exit 1
fi

OLLAMA_URL="http://${HOST_IP}:11434/v1"

echo "감지된 Ubuntu IP: ${HOST_IP}"
echo "적용할 OLLAMA_BASE_URL: ${OLLAMA_URL}"

sed -i "s|OLLAMA_BASE_URL: \".*\"|OLLAMA_BASE_URL: \"${OLLAMA_URL}\"|g" docker-compose.yml

echo "docker-compose.yml 수정 완료"
echo "Ollama 응답 확인 중..."
curl -fsS "http://${HOST_IP}:11434/api/tags" > /dev/null

echo "docker compose 실행"
docker compose up -d --build

echo
echo "완료"
echo "채팅 페이지: http://localhost:8000/dev/chat"
```

예시 파일명:

```bash
bootstrap_project.sh
```

실행:

```bash
chmod +x bootstrap_project.sh
./bootstrap_project.sh /path/to/ZconvertProject
```

---

## 11. 팀원용 권장 최종 절차

아래 순서 그대로 하면 된다.

### 1단계

코드 clone

```bash
git clone <repo-url>
cd ZconvertProject
```

### 2단계

Ubuntu 인프라 설치

```bash
chmod +x setup_ubuntu_infra.sh
./setup_ubuntu_infra.sh
```

설치 후:

```bash
sudo usermod -aG docker $USER
```

그 다음 로그아웃/로그인

### 3단계

Ollama 모델 설치

```bash
ollama pull qwen2.5:7b
```

### 4단계

별도 전달받은 파일 배치

1. `.env`를 프로젝트 루트에 넣기
2. `secrets/private_key.pem` 넣기
3. `secrets/public_key.pem` 넣기

### 5단계

프로젝트 bootstrap 실행

```bash
chmod +x bootstrap_project.sh
./bootstrap_project.sh .
```

### 6단계

브라우저 접속

```text
http://localhost:8000/dev/chat
```

---

## 12. 동작 확인 체크리스트

아래가 모두 되면 정상이다.

1. `docker compose ps` 에서 `agent_server`, `redis`가 올라와 있다.
2. `curl http://localhost:8000/dev/chat` 이 HTML을 반환한다.
3. 브라우저에서 `http://localhost:8000/dev/chat` 접속이 된다.
4. username 입력 후 연결이 된다.
5. 메시지 전송 시 FastAPI 로그에 아래가 찍힌다.

```text
[DEV JWT] 발급 성공
[JWT] 검증 성공
[WS] 사용자 메시지 수신
```

---

## 13. 장애가 났을 때 먼저 볼 것

### `docker compose up`은 되는데 응답이 느리거나 안 오는 경우

아래를 확인한다.

1. `ollama list`에 `qwen2.5:7b`가 있는지
2. `curl http://127.0.0.1:11434/api/tags`가 되는지
3. `docker-compose.yml`의 `OLLAMA_BASE_URL` IP가 현재 머신 IP와 맞는지

### `/dev/chat`은 열리는데 연결이 안 되는 경우

아래를 확인한다.

1. `.env`가 프로젝트 루트에 있는지
2. `secrets/private_key.pem`, `secrets/public_key.pem`이 있는지
3. `DEV_CHAT_ENABLED=true`인지

### JWT 관련 오류가 나는 경우

대부분 아래 둘 중 하나다.

1. `secrets/` 키 파일이 잘못되었거나 누락됨
2. `.env`가 누락되었거나 값이 다름

---

## 14. 팀원에게 실제로 전달하면 좋은 것

팀원 경험을 가장 좋게 하려면 아래 4개를 같이 전달하는 것이 좋다.

1. GitHub 저장소 URL
2. `.env` 파일
3. `secrets/private_key.pem`, `secrets/public_key.pem`
4. 이 문서

그리고 가능하면 아래 두 스크립트를 실제 파일로도 같이 주는 것이 가장 좋다.

1. `setup_ubuntu_infra.sh`
2. `bootstrap_project.sh`

지금 문서에는 스크립트 본문까지 포함했으므로, 팀원은 그대로 복사해서 파일로 만들면 된다.

---

## 15. 추천 운영 방식

가장 현실적인 방식은 아래다.

1. 코드는 GitHub로 공유
2. `.env`와 `secrets/`는 Notion 또는 비공개 문서/메신저로 공유
3. 팀원은 이 문서 순서대로 설치
4. 팀원이 자신의 Ubuntu IP를 자동 감지해서 `docker-compose.yml`에 반영
5. `docker compose up -d --build` 실행

이 방식이면 팀원 입장에서는 사실상 아래 두 번만 제대로 하면 된다.

1. 인프라 설치 스크립트 실행
2. 프로젝트 bootstrap 스크립트 실행

그 뒤 브라우저에서 `http://localhost:8000/dev/chat`로 들어가면 된다.
