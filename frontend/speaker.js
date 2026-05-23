/**
 * speaker.js
 * Handles room creation, microphone capture via MediaRecorder,
 * and streaming binary audio chunks to the backend WebSocket.
 */

const API_BASE = window.location.origin;
const WS_BASE  = API_BASE.replace(/^http/, "ws");

let ws            = null;
let mediaRecorder = null;
let roomId        = null;
let listenerPoll  = null;

// ── UI refs ───────────────────────────────────────────────────────────────────

const btnCreate       = document.getElementById("btn-create");
const btnMic          = document.getElementById("btn-mic");
const btnStop         = document.getElementById("btn-stop");
const btnCopy         = document.getElementById("btn-copy");
const roomCodeEl      = document.getElementById("room-code");
const statusDot       = document.getElementById("status-dot");
const statusText      = document.getElementById("status-text");
const listenerCountEl = document.getElementById("listener-count");
const stepCreate      = document.getElementById("step-create");
const stepRoom        = document.getElementById("step-room");
const logEl           = document.getElementById("log");

// ── Room creation ─────────────────────────────────────────────────────────────

btnCreate.addEventListener("click", async () => {
  btnCreate.disabled = true;
  btnCreate.textContent = "Creating…";
  try {
    const res  = await fetch(`${API_BASE}/room/create`, { method: "POST" });
    const data = await res.json();
    roomId = data.room_id;

    roomCodeEl.textContent = roomId;
    stepCreate.classList.add("hidden");
    stepRoom.classList.remove("hidden");
    logEl.classList.remove("hidden");

    setStatus("idle");
    startListenerPoll();
    log(`Room created: ${roomId}`);
  } catch (err) {
    log(`Error creating room: ${err}`);
    btnCreate.disabled = false;
    btnCreate.textContent = "Create Room";
  }
});

// ── Copy room code ────────────────────────────────────────────────────────────

btnCopy.addEventListener("click", () => {
  navigator.clipboard.writeText(roomId).then(() => {
    btnCopy.textContent = "Copied!";
    setTimeout(() => (btnCopy.textContent = "Copy"), 1500);
  });
});

// ── Start microphone ──────────────────────────────────────────────────────────

btnMic.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    connectWebSocket(stream);
  } catch (err) {
    log(`Mic access denied: ${err}`);
  }
});

btnStop.addEventListener("click", stopAll);

// ── WebSocket + MediaRecorder ─────────────────────────────────────────────────

function connectWebSocket(stream) {
  ws = new WebSocket(`${WS_BASE}/ws/speaker/${roomId}`);

  ws.onopen = () => {
    log("WebSocket connected.");
    setStatus("connected");

    // MediaRecorder sends 1-second webm/opus chunks
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 64000,
    });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data);           // Send binary chunk directly
      }
    };

    mediaRecorder.start(1000);    // Fire ondataavailable every 1000 ms
    setStatus("recording");
    btnMic.classList.add("hidden");
    btnStop.classList.remove("hidden");
    log("Recording started.");
  };

  ws.onerror = (err) => {
    log(`WebSocket error: ${err}`);
    setStatus("error");
  };

  ws.onclose = () => {
    log("WebSocket closed.");
    setStatus("idle");
  };
}

// ── Stop everything ───────────────────────────────────────────────────────────

function stopAll() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
  }
  if (ws) ws.close();
  setStatus("idle");
  btnStop.classList.add("hidden");
  btnMic.classList.remove("hidden");
  log("Recording stopped.");
}

// ── Poll listener count ───────────────────────────────────────────────────────

function startListenerPoll() {
  listenerPoll = setInterval(async () => {
    try {
      const res  = await fetch(`${API_BASE}/room/${roomId}/exists`);
      const data = await res.json();
      listenerCountEl.textContent = data.listener_count ?? 0;
    } catch (_) {}
  }, 3000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setStatus(state) {
  const states = {
    idle:       { text: "Idle",       cls: ""           },
    connected:  { text: "Connected",  cls: "connected"  },
    recording:  { text: "Recording…", cls: "recording"  },
    error:      { text: "Error",      cls: "error"      },
  };
  const s = states[state] || states.idle;
  statusText.textContent = s.text;
  statusDot.className    = `dot ${s.cls}`;
}

function log(msg) {
  const ts   = new Date().toLocaleTimeString();
  const line = document.createElement("div");
  line.textContent = `[${ts}] ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
