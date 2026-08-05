(function () {
  "use strict";

  // ── REUSE NOTE ─────────────────────────────────────────────────────────────
  // This file is IDENTICAL in hide_and_seek/ and hide_and_seek_test/.
  // rssiPercent() formula is identical to pass_the_ball dashboard.js.
  // Changed: card structure tracks hider found state instead of possession.
  // ──────────────────────────────────────────────────────────────────────────

  const RSSI_MIN = -100;
  const RSSI_MAX = -40;

  const socket      = io();
  const hidersEl    = document.getElementById("hiders");
  const emptyEl     = document.getElementById("empty-state");
  const serialDot   = document.getElementById("serial-dot");
  const serialLabel = document.getElementById("serial-label");
  const resetBtn    = document.getElementById("reset-btn");

  // { hider_id: { card, fillEl, rssiValue, labelEl, timeEl, relayEl, hide_start } }
  const hiders = {};

  // ── helpers ────────────────────────────────────────────────────────────────

  function rssiPercent(rssi) {
    // REUSE: identical formula to pass_the_ball dashboard.js
    const c = Math.max(RSSI_MIN, Math.min(RSSI_MAX, rssi));
    return Math.round(((c - RSSI_MIN) / (RSSI_MAX - RSSI_MIN)) * 100);
  }

  function proximityClass(rssi) {
    if (rssi > window.RSSI_HOT)  return "hot";
    if (rssi > window.RSSI_WARM) return "warm";
    return "cold";
  }

  function proximityLabel(rssi) {
    if (rssi > window.RSSI_HOT)  return "Very Close — HOT 🔥";
    if (rssi > window.RSSI_WARM) return "Getting Warmer — WARM";
    return "Far Away — COLD";
  }

  function hiderColor(hid) {
    const palette = ["#a78bfa", "#34d399", "#f472b6", "#fb923c", "#60a5fa"];
    const idx = parseInt(hid.replace(/\D/g, ""), 10) - 1;
    return palette[idx % palette.length] || "#94a3b8";
  }

  function formatTime(seconds) {
    const s = Math.floor(seconds);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  }

  // ── card factory ───────────────────────────────────────────────────────────

  function createCard(hid) {
    const color = hiderColor(hid);
    const pct   = rssiPercent(window.RSSI_HOT);
    const card  = document.createElement("div");
    card.className  = "hider-card";
    card.dataset.id = hid;
    card.innerHTML  = `
      <div class="card-header">
        <span class="hider-name" style="color:${color}">${hid}</span>
        <span class="found-badge">FOUND</span>
      </div>
      <div>
        <div class="meter-label">
          <span>Seeker Proximity</span>
          <span class="rssi-value">— dBm</span>
        </div>
        <div class="meter-track">
          <div class="meter-fill" style="width:0%"></div>
          <div class="meter-threshold" style="left:${pct}%"></div>
        </div>
      </div>
      <div class="proximity-label cold">—</div>
      <div class="card-footer">
        <div class="stat">
          <div class="stat-value time-value">0s</div>
          <div class="stat-label">Time Hiding</div>
        </div>
      </div>
      <div class="relay-rssi">Bridge signal: <span class="relay-value">—</span> dBm</div>`;
    return {
      card,
      fillEl:    card.querySelector(".meter-fill"),
      rssiValue: card.querySelector(".rssi-value"),
      labelEl:   card.querySelector(".proximity-label"),
      timeEl:    card.querySelector(".time-value"),
      relayEl:   card.querySelector(".relay-value"),
      hide_start: Date.now(),
      found:      false,
      found_at:   null,
    };
  }

  function ensureCard(hid) {
    if (!hiders[hid]) {
      const refs = createCard(hid);
      hiders[hid] = refs;
      emptyEl.style.display = "none";
      hidersEl.appendChild(refs.card);
    }
    return hiders[hid];
  }

  // ── update functions ───────────────────────────────────────────────────────

  function updateSeekerProximity(hid, seekerRssi) {
    const refs = ensureCard(hid);
    if (refs.found) return;   // card is frozen once found
    const pct   = rssiPercent(seekerRssi);
    const prox  = proximityClass(seekerRssi);
    const fill  = prox === "hot" ? "#f87171" : prox === "warm" ? "#fb923c" : "#334155";
    refs.fillEl.style.width      = pct + "%";
    refs.fillEl.style.background = fill;
    refs.rssiValue.textContent   = seekerRssi + " dBm";
    refs.labelEl.className       = "proximity-label " + prox;
    refs.labelEl.textContent     = proximityLabel(seekerRssi);
  }

  function updateRelaySignal(hid, rssi) {
    const refs = ensureCard(hid);
    refs.relayEl.textContent = rssi;
  }

  function markFound(hid) {
    const refs = ensureCard(hid);
    if (!refs.found) {
      refs.found    = true;
      refs.found_at = Date.now();
      refs.card.classList.add("found");
      refs.labelEl.className   = "proximity-label hot";
      refs.labelEl.textContent = "🎉 FOUND!";
    }
  }

  // ── time counter ───────────────────────────────────────────────────────────

  setInterval(function () {
    const now = Date.now();
    for (const [hid, refs] of Object.entries(hiders)) {
      const elapsed = refs.found
        ? (refs.found_at - refs.hide_start) / 1000
        : (now - refs.hide_start) / 1000;
      refs.timeEl.textContent = formatTime(elapsed);
    }
  }, 500);

  // ── full snapshot render ───────────────────────────────────────────────────

  function renderSnapshot(snap) {
    const h = snap.hiders || {};
    for (const [hid, data] of Object.entries(h)) {
      const refs = ensureCard(hid);
      if (snap.game_start && !refs._started) {
        refs.hide_start = snap.game_start * 1000;
        refs._started   = true;
      }
      if (data.seeker_rssi !== undefined && data.seeker_rssi > -100) {
        updateSeekerProximity(hid, data.seeker_rssi);
      }
      if (data.signal_at_relay !== undefined) {
        refs.relayEl.textContent = data.signal_at_relay;
      }
      if (data.found) {
        markFound(hid);
      }
    }
    if (Object.keys(h).length === 0) {
      emptyEl.style.display = "";
    }
  }

  // ── socket events ──────────────────────────────────────────────────────────

  socket.on("serial_status", (d) => {
    serialDot.classList.toggle("connected", d.connected);
    serialLabel.textContent = d.connected
      ? `Connected — ${d.port}`
      : `Disconnected — ${d.error || "retrying…"}`;
  });

  socket.on("state_snapshot", (snap) => {
    renderSnapshot(snap);
  });

  socket.on("rssi_update", (d) => {
    updateSeekerProximity(d.hider_id, d.seeker_rssi);
  });

  socket.on("hider_signal", (d) => {
    updateRelaySignal(d.hider_id, d.rssi);
  });

  socket.on("tagged", (d) => {
    markFound(d.hider_id);
  });

  // ── reset ──────────────────────────────────────────────────────────────────

  resetBtn.addEventListener("click", () => {
    for (const refs of Object.values(hiders)) refs.card.remove();
    Object.keys(hiders).forEach((k) => delete hiders[k]);
    emptyEl.style.display = "";
    socket.emit("reset_session");
  });

})();
