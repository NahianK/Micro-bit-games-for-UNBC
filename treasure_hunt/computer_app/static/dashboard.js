/* dashboard.js - Treasure Hunt FULL version
 * Socket.IO client for the Treasure Hunt dashboard.
 * REUSE: identical to treasure_hunt_test\computer_app\static\dashboard.js.
 */

'use strict';

const socket = io();

// ── Helpers ──────────────────────────────────────────────────────────────────

function rssiToPercent(rssi) {
  const floor = -80;
  const hot   = window.RSSI_HOT || -50;
  const pct   = Math.max(0, Math.min(100, ((rssi - floor) / (hot - floor)) * 100));
  return pct;
}

function rssiLabel(rssi) {
  if (rssi === null || rssi === undefined) return 'NO SIGNAL';
  if (rssi >= (window.RSSI_HOT  || -50)) return 'HOT 🔥';
  if (rssi >= (window.RSSI_WARM || -65)) return 'WARM ♨';
  return 'COLD ❄';
}

function rssiLabelClass(rssi) {
  if (rssi === null || rssi === undefined) return 'label-cold';
  if (rssi >= (window.RSSI_HOT  || -50)) return 'label-hot';
  if (rssi >= (window.RSSI_WARM || -65)) return 'label-warm';
  return 'label-cold';
}

function rssiBarColor(rssi) {
  if (rssi >= (window.RSSI_HOT  || -50)) return '#3fb950';
  if (rssi >= (window.RSSI_WARM || -65)) return '#e3912a';
  return '#58a6ff';
}

function ensureHunterCard(hunterId) {
  let card = document.getElementById('hunter-' + hunterId);
  if (!card) {
    card = document.createElement('div');
    card.className = 'hunter-card';
    card.id = 'hunter-' + hunterId;
    card.innerHTML = `
      <div class="hunter-header">
        <span class="hunter-name">${hunterId}</span>
        <span class="hunter-label label-cold" id="hlabel-${hunterId}">NO SIGNAL</span>
      </div>
      <div class="prox-bar-wrap">
        <div class="prox-bar" id="hbar-${hunterId}" style="width:0%;background:#58a6ff"></div>
      </div>
      <div class="hunter-meta">
        <span id="hmeta-target-${hunterId}">Nearest: —</span>
        <span id="hmeta-rssi-${hunterId}">— dBm</span>
      </div>`;
    document.getElementById('hunters-grid').appendChild(card);
  }
  return card;
}

function ensureTreasureCard(treasureId) {
  let card = document.getElementById('treasure-' + treasureId);
  if (!card) {
    card = document.createElement('div');
    card.className = 'treasure-card';
    card.id = 'treasure-' + treasureId;
    card.innerHTML = `
      <div class="treasure-header">
        <span class="treasure-name">💎 ${treasureId}</span>
        <span id="tfound-badge-${treasureId}" style="display:none" class="found-badge">FOUND!</span>
      </div>
      <div class="treasure-info" id="tinfo-${treasureId}">Waiting for signal…</div>
      <div class="signal-bar-wrap">
        <div class="signal-bar" id="tsigbar-${treasureId}" style="width:0%"></div>
      </div>`;
    document.getElementById('treasures-grid').appendChild(card);
  }
  return card;
}

function updateHunterCard(hunterId, data) {
  const card  = ensureHunterCard(hunterId);
  const rssi  = data.rssi_to_nearest;
  const pct   = rssi !== null ? rssiToPercent(rssi) : 0;
  const lbl   = rssiLabel(rssi);
  const lblCls = rssiLabelClass(rssi);
  const color = rssiBarColor(rssi);

  document.getElementById('hbar-' + hunterId).style.width      = pct + '%';
  document.getElementById('hbar-' + hunterId).style.background = color;
  document.getElementById('hlabel-' + hunterId).textContent    = lbl;
  document.getElementById('hlabel-' + hunterId).className      = 'hunter-label ' + lblCls;
  document.getElementById('hmeta-target-' + hunterId).textContent =
      'Nearest: ' + (data.nearest_treasure || '—');
  document.getElementById('hmeta-rssi-' + hunterId).textContent =
      rssi !== null ? rssi.toFixed(1) + ' dBm' : '— dBm';

  if (data.claimed) {
    card.classList.add('found');
    card.classList.remove('claiming');
  }
}

function updateTreasureCard(treasureId, data) {
  ensureTreasureCard(treasureId);
  const info  = document.getElementById('tinfo-' + treasureId);
  const badge = document.getElementById('tfound-badge-' + treasureId);
  const bar   = document.getElementById('tsigbar-' + treasureId);
  const card  = document.getElementById('treasure-' + treasureId);

  if (data.found_by) {
    badge.style.display = 'inline-block';
    card.classList.add('found');
    info.innerHTML = `Found by <span style="color:#f0c040;font-weight:700">${data.found_by}</span>`;
  } else {
    const sig = data.signal_at_relay;
    const pct = sig !== null && sig !== undefined ? rssiToPercent(sig) : 0;
    bar.style.width = pct + '%';
    info.textContent = sig !== null && sig !== undefined
        ? 'Relay signal: ' + sig + ' dBm'
        : 'Waiting for signal…';
  }
}

// ── Render full snapshot ──────────────────────────────────────────────────────

function renderSnapshot(snap) {
  const hunters   = snap.active_hunters   || window.ACTIVE_HUNTERS   || [];
  const treasures = snap.active_treasures || window.ACTIVE_TREASURES || [];

  const hGrid = document.getElementById('hunters-grid');
  const tGrid = document.getElementById('treasures-grid');

  if (hunters.length === 0 && treasures.length === 0) {
    hGrid.innerHTML = '';
    tGrid.innerHTML = `<div class="empty">No game configured. <a href="/setup">Set up a game</a>.</div>`;
    return;
  }

  hunters.forEach(hid => ensureHunterCard(hid));
  treasures.forEach(tid => ensureTreasureCard(tid));

  hunters.forEach(hid => {
    const data = snap.hunters ? snap.hunters[hid] : null;
    if (data) updateHunterCard(hid, data);
  });
  treasures.forEach(tid => {
    const data = snap.treasures ? snap.treasures[tid] : null;
    if (data) updateTreasureCard(tid, data);
  });

  if (snap.game_over && snap.leaderboard) {
    showGameOver({ leaderboard: snap.leaderboard, total_treasures: treasures.length });
  }
}

// ── Socket.IO events ──────────────────────────────────────────────────────────

socket.on('connect', () => {
  console.log('[socket] connected');
});

socket.on('serial_status', (data) => {
  const badge = document.getElementById('serial-badge');
  if (data.connected) {
    badge.textContent = '● Connected (' + data.port + ')';
    badge.className   = 'badge badge-ok';
  } else {
    badge.textContent = '● Disconnected' + (data.error ? ': ' + data.error : '');
    badge.className   = 'badge badge-err';
  }
});

socket.on('reachy_status', (data) => {
  const badge = document.getElementById('reachy-badge');
  if (!badge) return;
  if (!data.enabled) {
    badge.style.display = 'none';
    return;
  }
  if (data.available && data.robot_ready) {
    badge.textContent = '🤖 Reachy ●';
    badge.style.background = '#1a4731';
    badge.style.color      = '#3fb950';
    badge.style.border     = '1px solid #3fb950';
  } else if (data.available) {
    badge.textContent = '🤖 Reachy ◌';
    badge.style.background = '#1a2740';
    badge.style.color      = '#58a6ff';
    badge.style.border     = '1px solid #58a6ff';
  } else {
    badge.textContent = '🤖 Reachy ✕';
    badge.style.background = '#4c1616';
    badge.style.color      = '#f85149';
    badge.style.border     = '1px solid #f85149';
  }
});

socket.on('state_snapshot', (snap) => {
  renderSnapshot(snap);
});

socket.on('rssi_update', (data) => {
  const card = ensureHunterCard(data.hunter_id);
  const rssi = data.hunter_rssi;
  const pct  = rssiToPercent(rssi);

  document.getElementById('hbar-' + data.hunter_id).style.width      = pct + '%';
  document.getElementById('hbar-' + data.hunter_id).style.background = rssiBarColor(rssi);
  document.getElementById('hlabel-' + data.hunter_id).textContent    = rssiLabel(rssi);
  document.getElementById('hlabel-' + data.hunter_id).className      = 'hunter-label ' + rssiLabelClass(rssi);
  document.getElementById('hmeta-target-' + data.hunter_id).textContent =
      'Nearest: ' + data.treasure_id;
  document.getElementById('hmeta-rssi-' + data.hunter_id).textContent =
      rssi.toFixed(1) + ' dBm';
});

socket.on('claim', (data) => {
  const card = ensureHunterCard(data.hunter_id);
  card.classList.add('claiming');
  const lbl = document.getElementById('hlabel-' + data.hunter_id);
  const prev = lbl.textContent;
  lbl.textContent = 'CLAIMING…';
  lbl.className   = 'hunter-label label-warm';
  setTimeout(() => {
    card.classList.remove('claiming');
    lbl.textContent = prev;
  }, 3000);
});

socket.on('found', (data) => {
  const tCard = ensureTreasureCard(data.treasure_id);
  tCard.classList.add('found');
  document.getElementById('tfound-badge-' + data.treasure_id).style.display = 'inline-block';
  document.getElementById('tinfo-' + data.treasure_id).innerHTML =
      `Found by <span style="color:#f0c040;font-weight:700">${data.hunter_id}</span>`;

  const hCard = document.getElementById('hunter-' + data.hunter_id);
  if (hCard) {
    hCard.classList.add('found');
    hCard.classList.remove('claiming');
    const lbl = document.getElementById('hlabel-' + data.hunter_id);
    if (lbl) { lbl.textContent = 'FOUND! 🏴'; lbl.className = 'hunter-label label-found'; }
  }
});

socket.on('treasure_signal', (data) => {
  const bar = document.getElementById('tsigbar-' + data.treasure_id);
  if (bar) {
    bar.style.width = rssiToPercent(data.relay_rssi) + '%';
  }
  const info = document.getElementById('tinfo-' + data.treasure_id);
  if (info && !document.getElementById('treasure-' + data.treasure_id).classList.contains('found')) {
    info.textContent = 'Bridge signal: ' + data.relay_rssi + ' dBm';
  }
});

socket.on('redirect', (data) => {
  window.location.href = data.url;
});

// ── Game-over overlay ─────────────────────────────────────────────────────────

function showGameOver(data) {
  const leaderboard = data.leaderboard || [];
  const total = data.total_treasures || 0;

  // Winner = first entry (already sorted desc by finds)
  const winner = leaderboard.length > 0 ? leaderboard[0] : null;
  document.getElementById('go-winner').textContent =
      winner && winner.finds > 0 ? winner.hunter_id : '—';
  document.getElementById('go-subtitle').textContent =
      total + (total === 1 ? ' treasure' : ' treasures') + ' discovered!';

  const ol = document.getElementById('go-leaderboard');
  ol.innerHTML = '';
  leaderboard.forEach((entry, i) => {
    const li = document.createElement('li');
    li.innerHTML =
        `<span class="go-rank">${i + 1}.</span>` +
        `<span class="go-hunter">${entry.hunter_id}</span>` +
        `<span class="go-finds"><span>${entry.finds}</span> found</span>`;
    ol.appendChild(li);
  });

  const overlay = document.getElementById('game-over-overlay');
  overlay.classList.add('visible');
}

socket.on('game_over', showGameOver);

document.getElementById('go-reset-btn').addEventListener('click', () => {
  if (confirm('Reset session and play again?')) {
    socket.emit('reset_session');
  }
});
document.getElementById('reset-btn').addEventListener('click', () => {
  if (confirm('Reset session and return to setup?')) {
    socket.emit('reset_session');
  }
});
