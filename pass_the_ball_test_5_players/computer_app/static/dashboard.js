(function () {
  "use strict";

  const RSSI_MIN = -100;
  const RSSI_MAX = -40;

  const socket      = io();
  const playersEl   = document.getElementById("players");
  const emptyEl     = document.getElementById("empty-state");
  const serialDot   = document.getElementById("serial-dot");
  const serialLabel = document.getElementById("serial-label");
  const resetBtn    = document.getElementById("reset-btn");
  const ballFill    = document.getElementById("ball-fill");
  const ballRssiVal = document.getElementById("ball-rssi-value");
  const ballThresh  = document.getElementById("ball-threshold");

  const players = {};

  // Position threshold marker on ball banner
  ballThresh.style.left = rssiPercent(window.RSSI_HOT) + "%";

  function rssiPercent(rssi) {
    const c = Math.max(RSSI_MIN, Math.min(RSSI_MAX, rssi));
    return Math.round(((c - RSSI_MIN) / (RSSI_MAX - RSSI_MIN)) * 100);
  }

  function proximityClass(rssi) {
    if (rssi > window.RSSI_HOT)  return "hot";
    if (rssi > window.RSSI_WARM) return "warm";
    return "cold";
  }

  function proximityLabel(rssi) {
    if (rssi > window.RSSI_HOT)  return "Very Close — HOT";
    if (rssi > window.RSSI_WARM) return "In Range — WARM";
    return "Far Away — COLD";
  }

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = (s % 60).toFixed(1);
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  }

  function playerColor(pid) {
    const palette = ["#60a5fa","#34d399","#f472b6","#fb923c","#a78bfa"];
    const idx = parseInt(pid.replace(/\D/g, ""), 10) - 1;
    return palette[idx % palette.length] || "#94a3b8";
  }

  function createCard(pid) {
    const color = playerColor(pid);
    const pct   = rssiPercent(window.RSSI_HOT);
    const card  = document.createElement("div");
    card.className  = "player-card";
    card.dataset.id = pid;
    card.innerHTML  = `
      <div class="card-header">
        <span class="player-name" style="color:${color}">${pid}</span>
        <span class="holding-badge">HOLDING</span>
      </div>
      <div>
        <div class="meter-label"><span>Signal</span><span class="rssi-value">— dBm</span></div>
        <div class="meter-track">
          <div class="meter-fill" style="width:0%"></div>
          <div class="meter-threshold" style="left:${pct}%"></div>
        </div>
      </div>
      <div class="proximity-label cold">—</div>
      <div class="stats">
        <div class="stat"><div class="stat-value time-value">0.0s</div><div class="stat-label">Time with Ball</div></div>
        <div class="stat"><div class="stat-value count-value">0</div><div class="stat-label">Possessions</div></div>
      </div>`;
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

  function updateCard(pid, data) {
    const refs  = ensureCard(pid);
    const rssi  = data.ball_rssi;
    const pct   = rssiPercent(rssi);
    const prox  = proximityClass(rssi);
    const fill  = prox === "hot" ? "#f87171" : prox === "warm" ? "#fb923c" : "#334155";

    refs.fillEl.style.width      = pct + "%";
    refs.fillEl.style.background = fill;
    refs.rssiValue.textContent   = rssi + " dBm";
    refs.labelEl.className       = "proximity-label " + prox;
    refs.labelEl.textContent     = proximityLabel(rssi);
    refs.timeEl.textContent      = formatTime(data.total_s ?? data.total_seconds ?? 0);
    refs.countEl.textContent     = data.possession ?? data.possession_count ?? 0;
    refs.card.classList.toggle("holding", !!data.holding);
    refs.card.classList.toggle("offline", data.online === false);
  }

  function updateBallBanner(rssi) {
    const pct   = rssiPercent(rssi);
    const color = rssi > window.RSSI_HOT ? "#34d399" : rssi > window.RSSI_WARM ? "#fb923c" : "#334155";
    ballFill.style.width      = pct + "%";
    ballFill.style.background = color;
    ballRssiVal.textContent   = rssi + " dBm (bridge reference)";
  }

  // ── socket events ──────────────────────────────────────────────────────────
  socket.on("serial_status", (d) => {
    serialDot.classList.toggle("connected", d.connected);
    serialLabel.textContent = d.connected ? `Connected — ${d.port}` : `Disconnected — ${d.error || "retrying…"}`;
  });

  socket.on("state_snapshot", (snap) => {
    if (snap.ball_position !== undefined) updateBallBanner(snap.ball_position);
    const pl = snap.players || {};
    for (const [pid, data] of Object.entries(pl)) updateCard(pid, data);
    if (Object.keys(pl).length === 0) emptyEl.style.display = "";
  });

  socket.on("ball_position", (d) => updateBallBanner(d.rssi));

  socket.on("rssi_update", (d) => updateCard(d.player_id, d));

  resetBtn.addEventListener("click", () => {
    for (const pid of Object.keys(players)) players[pid].card.remove();
    Object.keys(players).forEach((k) => delete players[k]);
    emptyEl.style.display = "";
    socket.emit("reset_session");
  });
})();
