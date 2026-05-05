def build_dev_chat_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dev Chat</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3efe6;
      --panel: rgba(255, 252, 247, 0.9);
      --line: #d6cbb8;
      --text: #1f1a17;
      --muted: #6a625a;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iosevka Aile", "Pretendard", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(180, 35, 24, 0.12), transparent 24%),
        linear-gradient(135deg, #efe7d8, var(--bg));
      min-height: 100vh;
      padding: 24px;
    }
    .shell {
      max-width: 1040px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 20px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 24px 60px rgba(31, 26, 23, 0.08);
      backdrop-filter: blur(10px);
    }
    .controls, .chat {
      padding: 20px;
    }
    h1, h2 {
      margin: 0 0 12px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .eyebrow {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 14px;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    input, textarea, button {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      font: inherit;
    }
    input, textarea {
      background: #fffdf8;
      color: var(--text);
      padding: 12px 14px;
    }
    textarea {
      min-height: 88px;
      resize: vertical;
    }
    button {
      padding: 12px 14px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      border: none;
      transition: transform 120ms ease, background 120ms ease;
    }
    button:hover { background: var(--accent-strong); transform: translateY(-1px); }
    button.secondary { background: #fff; color: var(--text); border: 1px solid var(--line); }
    button.reject { background: var(--danger); }
    .stack { display: grid; gap: 12px; }
    .status {
      padding: 12px 14px;
      border-radius: 12px;
      background: #fcfaf4;
      border: 1px solid var(--line);
      color: var(--muted);
      min-height: 48px;
    }
    .log {
      background: #fffdf8;
      border: 1px solid var(--line);
      border-radius: 14px;
      min-height: 420px;
      max-height: 62vh;
      overflow: auto;
      padding: 14px;
      display: grid;
      gap: 10px;
    }
    .msg {
      padding: 12px 14px;
      border-radius: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .msg.user { background: #d9f1ee; justify-self: end; max-width: 85%; }
    .msg.assistant { background: #f1ebdf; max-width: 90%; }
    .msg.system { background: #f8f4ea; color: var(--muted); }
    .confirm-box {
      display: grid;
      gap: 10px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff7ed;
    }
    .confirm-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    @media (max-width: 860px) {
      .shell { grid-template-columns: 1fr; }
      .log { min-height: 320px; max-height: 48vh; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel controls">
      <h1>Dev Chat</h1>
      <p class="eyebrow">개발용 JWT를 발급받아 기존 <code>/ws/chat</code> 경로로 연결합니다.</p>
      <div class="stack">
        <div>
          <label for="username">Username</label>
          <input id="username" placeholder="alice" autocomplete="off" />
        </div>
        <button id="connectBtn">토큰 발급 후 연결</button>
        <button id="disconnectBtn" class="secondary" type="button">연결 종료</button>
        <div id="status" class="status">연결 전</div>
      </div>
    </section>
    <section class="panel chat">
      <h2>Conversation</h2>
      <div id="log" class="log"></div>
      <div class="stack" style="margin-top: 14px;">
        <textarea id="message" placeholder="메시지를 입력하세요."></textarea>
        <button id="sendBtn" type="button">메시지 전송</button>
      </div>
    </section>
  </main>
  <script>
    const state = {
      socket: null,
      token: null,
      username: "",
      pendingConfirmId: null,
    };

    const usernameEl = document.getElementById("username");
    const statusEl = document.getElementById("status");
    const logEl = document.getElementById("log");
    const messageEl = document.getElementById("message");
    const connectBtn = document.getElementById("connectBtn");
    const disconnectBtn = document.getElementById("disconnectBtn");
    const sendBtn = document.getElementById("sendBtn");

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function appendMessage(kind, text) {
      const el = document.createElement("div");
      el.className = "msg " + kind;
      el.textContent = text;
      logEl.appendChild(el);
      logEl.scrollTop = logEl.scrollHeight;
    }

    function removeConfirmBox() {
      const existing = document.getElementById("confirmBox");
      if (existing) {
        existing.remove();
      }
      state.pendingConfirmId = null;
    }

    function renderConfirm(payload) {
      removeConfirmBox();
      state.pendingConfirmId = payload.confirm_id || null;

      const box = document.createElement("div");
      box.id = "confirmBox";
      box.className = "confirm-box";

      const title = document.createElement("div");
      title.textContent = payload.message || "작업 실행 여부를 확인하세요.";
      box.appendChild(title);

      const meta = document.createElement("pre");
      meta.textContent = JSON.stringify({
        tool: payload.tool || "",
        args: payload.args || {}
      }, null, 2);
      meta.style.margin = "0";
      meta.style.whiteSpace = "pre-wrap";
      box.appendChild(meta);

      const actions = document.createElement("div");
      actions.className = "confirm-actions";

      const approveBtn = document.createElement("button");
      approveBtn.textContent = "Approve";
      approveBtn.onclick = () => sendConfirm(true);

      const rejectBtn = document.createElement("button");
      rejectBtn.textContent = "Reject";
      rejectBtn.className = "reject";
      rejectBtn.onclick = () => sendConfirm(false);

      actions.appendChild(approveBtn);
      actions.appendChild(rejectBtn);
      box.appendChild(actions);

      logEl.appendChild(box);
      logEl.scrollTop = logEl.scrollHeight;
    }

    async function issueToken(username) {
      const response = await fetch("/dev/chat/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username })
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "token issuance failed");
      }

      return response.json();
    }

    function disconnect() {
      if (state.socket) {
        state.socket.close();
        state.socket = null;
      }
      removeConfirmBox();
      setStatus("연결 종료");
    }

    async function connect() {
      const username = usernameEl.value.trim();
      if (!username) {
        setStatus("username을 입력하세요.");
        return;
      }

      disconnect();
      setStatus("토큰 발급 중...");

      try {
        const tokenResponse = await issueToken(username);
        state.token = tokenResponse.token;
        state.username = tokenResponse.username;

        const scheme = location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(`${scheme}://${location.host}/ws/chat?token=${encodeURIComponent(state.token)}`);
        state.socket = socket;

        socket.onopen = () => {
          setStatus(`연결됨: ${state.username}`);
          appendMessage("system", `connected as ${state.username}`);
        };

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === "history") {
              payload.messages.forEach((item) => {
                appendMessage(item.role === "user" ? "user" : "assistant", item.content);
              });
              return;
            }
            if (payload.type === "confirm") {
              renderConfirm(payload);
              return;
            }
          } catch (_) {}

          appendMessage("assistant", event.data);
        };

        socket.onclose = (event) => {
          state.socket = null;
          removeConfirmBox();
          setStatus(`연결 종료 (code=${event.code})`);
        };

        socket.onerror = () => {
          setStatus("웹소켓 오류");
        };
      } catch (error) {
        setStatus(`연결 실패: ${error.message}`);
      }
    }

    function sendMessage() {
      if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
        setStatus("먼저 연결하세요.");
        return;
      }

      const content = messageEl.value.trim();
      if (!content) {
        return;
      }

      state.socket.send(JSON.stringify({ content }));
      appendMessage("user", content);
      messageEl.value = "";
    }

    function sendConfirm(approved) {
      if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
        setStatus("연결이 종료되었습니다.");
        return;
      }

      state.socket.send(JSON.stringify({
        type: "confirm_response",
        confirm_id: state.pendingConfirmId,
        approved
      }));
      appendMessage("system", approved ? "approve sent" : "reject sent");
      removeConfirmBox();
    }

    connectBtn.addEventListener("click", connect);
    disconnectBtn.addEventListener("click", disconnect);
    sendBtn.addEventListener("click", sendMessage);
    messageEl.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        sendMessage();
      }
    });
  </script>
</body>
</html>"""
