const API_BASE = window.location.origin;
const WS_BASE  = API_BASE.replace(/^http/, "ws");

let ws           = null;
let audioContext = null;
let audioQueue   = [];        // Queue of ArrayBuffers waiting to play
let isPlaying    = false;     // Serialise playback so chunks don't overlap

// ── UI refs ───────────────────────────────────────────────────────────────────

const btnJoin      = document.getElementById("btn-join");
const btnLeave     = document.getElementById("btn-leave");
const inpCode      = document.getElementById("inp-code");
const selLang      = document.getElementById("sel-lang");
const stepJoin     = document.getElementById("step-join");
const stepLive     = document.getElementById("step-live");
const statusDot    = document.getElementById("status-dot");
const statusText   = document.getElementById("status-text");
const subtitleBox  = document.getElementById("subtitle-box");
const chkAudio     = document.getElementById("chk-audio");
const volSlider    = document.getElementById("vol-slider");

// ── Populate language dropdown ────────────────────────────────────────────────

async function loadLanguages() {
  try {
    const res   = await fetch(`${API_BASE}/languages`);
    const langs = await res.json();            // {"hi": {"name": "Hindi"}, ...}
    selLang.innerHTML = "";
    for (const [code, info] of Object.entries(langs)) {
      const opt   = document.createElement("option");
      opt.value   = code;
      opt.textContent = info.name;
      selLang.appendChild(opt);
    }
  } catch (_) {
    // Keep the hardcoded English fallback in HTML
  }
}

loadLanguages();

// ── Join room ─────────────────────────────────────────────────────────────────

btnJoin.addEventListener("click", async () => {
  const roomId = inpCode.value.trim().toUpperCase();
  const lang   = selLang.value;

  if (!roomId) { alert("Enter a room code."); return; }

  // Verify room exists before opening WebSocket
  try {
    const res = await fetch(`${API_BASE}/room/${roomId}/exists`);
    if (!res.ok) { alert("Room not found. Check the code and try again."); return; }
  } catch {
    alert("Cannot reach server."); return;
  }

  connectWebSocket(roomId, lang);
});

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWebSocket(roomId, lang) {
  ws = new WebSocket(`${WS_BASE}/ws/listener/${roomId}?lang=${lang}`);

  ws.onopen = () => {
    stepJoin.classList.add("hidden");
    stepLive.classList.remove("hidden");
    setStatus("connected");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (_) {}
  };

  ws.onerror = () => setStatus("error");

  ws.onclose = () => {
    setStatus("disconnected");
    stepLive.classList.add("hidden");
    stepJoin.classList.remove("hidden");
  };

  // Heartbeat: respond to server pings
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 20000);
}

// ── Message handler ───────────────────────────────────────────────────────────

function handleMessage(msg) {
  switch (msg.type) {
    case "joined":
      console.log("Joined as", msg.listener_id, "language:", msg.language_name);
      break;

    case "subtitle":
      showSubtitle(msg.text);
      break;

    case "audio":
      if (chkAudio.checked) {
        const binary = atob(msg.data);
        const bytes  = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        enqueueAudio(bytes.buffer);
      }
      break;

    case "ping":
      ws.send(JSON.stringify({ type: "ping" }));
      break;
  }
}

// ── Subtitle display ──────────────────────────────────────────────────────────

let subtitleTimeout = null;

function showSubtitle(text) {
  subtitleBox.innerHTML = `<p class="subtitle-text">${escapeHtml(text)}</p>`;

  // Fade out subtitle after 6 seconds of inactivity
  clearTimeout(subtitleTimeout);
  subtitleTimeout = setTimeout(() => {
    subtitleBox.innerHTML = `<p class="subtitle-placeholder">Waiting for speaker…</p>`;
  }, 6000);
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ── Audio queue (sequential playback) ────────────────────────────────────────

function enqueueAudio(arrayBuffer) {
  audioQueue.push(arrayBuffer);
  if (!isPlaying) playNext();
}

async function playNext() {
  if (audioQueue.length === 0) { isPlaying = false; return; }

  isPlaying = true;
  const buffer = audioQueue.shift();

  try {
    if (!audioContext) audioContext = new AudioContext();
    if (audioContext.state === "suspended") await audioContext.resume();

    const decoded = await audioContext.decodeAudioData(buffer);
    const source  = audioContext.createBufferSource();
    const gainNode = audioContext.createGain();
    gainNode.gain.value = parseFloat(volSlider.value);

    source.buffer = decoded;
    source.connect(gainNode);
    gainNode.connect(audioContext.destination);

    source.onended = () => playNext();       // Chain: play next chunk when done
    source.start();
  } catch (err) {
    console.warn("Audio decode/play error:", err);
    playNext();                               // Skip bad chunk, continue queue
  }
}

// ── Leave room ────────────────────────────────────────────────────────────────

btnLeave.addEventListener("click", () => {
  if (ws) ws.close();
  audioQueue = [];
  isPlaying  = false;
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function setStatus(state) {
  const states = {
    connected:    { text: "Connected",    cls: "connected"  },
    disconnected: { text: "Disconnected", cls: ""           },
    error:        { text: "Error",        cls: "error"      },
  };
  const s = states[state] || states.disconnected;
  statusText.textContent = s.text;
  statusDot.className    = `dot ${s.cls}`;
}
