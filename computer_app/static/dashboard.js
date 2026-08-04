// dashboard.js — Live SocketIO client for the Pass the Ball dashboard
//
// Receives events from app.py and updates the DOM in real time.
// No page refreshes needed — all updates are pushed via WebSocket.

(function () {
  "use strict";

  // ── constants ──────────────────────────────────────────────────────────────
  // RSSI_HOT and RSSI_WARM are injected by index.html from Flask config
  const RSSI_MIN = -100;   // weakest detectable signal (0 % on meter)
  const RSSI_MAX = -40;    // strongest realistic signal (100 % on meter)

  // ── socket ─────────────────────────────────────────────────────────────────
  const socket = io();

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const playersEl    = document.getElementById("players");
  const emptyEl      = document.getElementById("empty-state");
  const serialDot    = document.getElementById("serial-dot");
  const serialLabel  = document.getElementById("serial-label");
  const resetBtn     = document.getElementById("reset-btn");

  // ── local state ────────────────────────────────────────────────────────────
  const players = {};   // { player_id: { card, fillEl, labelEl, timeEl, countEl } }

  // ── helpers ────────────────────────────────────────────────────────────────
  function rssiPercent(rssi) {
    const clamped = Math.max(RSSI_MIN, Math.min(RSSI_MAX, rssi));
    return Math.round(((clamped - RSSI_MIN) / (RSSI_MAX - RSSI_MIN)) * 100);
  }

  function thresholdPercent() {
    return rssiPercent(window.RSSI_HOT);
  }

  function proximityClass(rssi) {
    if (rssi > window.RSSI_HOT)  return "hot";
    if (rssi > window.RSSI_WARM) return "warm";
    return "cold";
  }

  function proximityLabel(rssi) {
    if (rssi > window.RSSI_HOT)  return "🔴 Very Close — HOT";
    if (rssi > window.RSSI_WARM) return "🟠 In Range — WARM";
    return "🔵 Far Away — COLD";
  }

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = (seconds % 60).toFixed(1);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  function playerColor(pid) {
    // Stable color per player ID so P1 is always one color, P2 another, etc.
    const palette = ["#60a5fa", "#34d399", "#f472b6", "#fb923c", "#a78bfa"];
    const idx = parseInt(pid.replace(/\D/g, ""), 10) - 1;
    return palette[idx % palette.length] || "#94a3b8";
  }

  // ── card creation ──────────────────────────────────────────────────────────
  function createCard(pid) {
    const color  = playerColor(pid);
    const pct    = thresholdPercent();

    const card = document.createElement("div");
    card.className  = "player-card";
    card.dataset.id = pid;
    card.innerHTML  = `
      <div class="card-header">
        <span class="player-name" style="color:${color}">${pid}</span>
        <span class="holding-badge">HOLDING</span>
      </div>

      <div>
        <div class="meter-label">
          <span>Signal (RSSI)</span>
          <span class="rssi-value">— dBm</span>
        </div>
        <div class="meter-track">
          <div class="meter-fill" style="width:0%"></div>
          <div class="meter-threshold" style="left:${pct}%"></div>
        </div>
      </div>

      <div class="proximity-label cold">— dBm</div>

      <div class="stats">
        <div class="stat">
          <div class="stat-value time-value">0.0s</div>
          <div class="stat-label">Time with Ball</div>
        </div>
        <div class="stat">
          <div class="stat-value count-value">0</div>
          <div class="stat-label">Possessions</div>
        </div>
      </div>
    `;

    return {
      card,
      fillEl:    card.querySelector(".meter-fill"),
      rssiValue: card.querySelector(".rssi-value"),
      labelEl:   card.querySelector(".proximity-label"),
      timeEl:    card.querySelector(".time-value"),
      countEl:   card.querySelector(".count-value"),
    };
  }

  function ensureCard(pid) {
    if (!players[pid]) {
      const refs = createCard(pid);
      players[pid] = refs;
      emptyEl.style.display = "none";
      playersEl.appendChild(refs.card);
    }
    return players[pid];
  }

  // ── update card ────────────────────────────────────────────────────────────
  function updateCard(pid, data) {
    const refs   = ensureCard(pid);
    const { card, fillEl, rssiValue, labelEl, timeEl, countEl } = refs;
    const rssi   = data.ball_rssi;
    const pct    = rssiPercent(rssi);
    const prox   = proximityClass(rssi);
    const color  = playerColor(pid);

    // Meter fill — color transitions with proximity
    const fillColor = prox === "hot" ? "#f87171" : prox === "warm" ? "#fb923c" : "#334155";
    fillEl.style.width      = pct + "%";
    fillEl.style.background = fillColor;

    // RSSI value text
    rssiValue.textContent = rssi + " dBm";

    // Proximity label
    labelEl.className   = "proximity-label " + prox;
    labelEl.textContent = proximityLabel(rssi);

    // Stats
    timeEl.textContent  = formatTime(data.total_s ?? data.total_seconds ?? 0);
    countEl.textContent = data.possession ?? data.possession_count ?? 0;

    // Holding glow
    card.classList.toggle("holding", !!data.holding);

    // Online/offline dimming
    card.classList.toggle("offline", data.online === false);
  }

  // ── socket events ──────────────────────────────────────────────────────────
  socket.on("connect", () => {
    // Server will push state_snapshot on connect
  });

  socket.on("serial_status", (data) => {
    const ok = data.connected;
    serialDot.classList.toggle("connected", ok);
    serialLabel.textContent = ok
      ? `Connected — ${data.port}`
      : `Disconnected — ${data.error || "retrying…"}`;
  });

  socket.on("state_snapshot", (snapshot) => {
    // Full state from server — render all known players
    for (const [pid, data] of Object.entries(snapshot)) {
      updateCard(pid, data);
    }
    if (Object.keys(snapshot).length === 0) {
      emptyEl.style.display = "";
    }
  });

  socket.on("rssi_update", (data) => {
    // Incremental update for a single player
    updateCard(data.player_id, data);
  });

  // ── reset button ───────────────────────────────────────────────────────────
  resetBtn.addEventListener("click", () => {
    // Clear local cards
    for (const pid of Object.keys(players)) {
      players[pid].card.remove();
    }
    Object.keys(players).forEach((k) => delete players[k]);
    emptyEl.style.display = "";

    // Tell server to reset tallies
    socket.emit("reset_session");
  });
})();
