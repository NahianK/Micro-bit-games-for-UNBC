// initialize.js — Registration ceremony page logic.
// Connects to SocketIO and renders live hunter identification progress.

(function () {
  'use strict';

  var socket = io({ transports: ['websocket', 'polling'] });
  var chips  = {};   // hid → DOM element

  // ── DOM references ──────────────────────────────────────────────────────
  var gridEl       = document.getElementById('hunters-grid');
  var phaseLabel   = document.getElementById('phase-label');
  var phaseTitle   = document.getElementById('phase-title');
  var phaseDesc    = document.getElementById('phase-desc');
  var promptBox    = document.getElementById('prompt-box');
  var promptHunter = document.getElementById('prompt-hunter');
  var promptCode   = document.getElementById('prompt-code');
  var progressBar  = document.getElementById('progress-bar');
  var progressLbl  = document.getElementById('progress-label');
  var readyN       = document.getElementById('ready-n');
  var alertBox     = document.getElementById('alert-box');
  var startBtn     = document.getElementById('start-btn');

  // ── Initialise chips from server-rendered SESSION ───────────────────────
  function init() {
    if (!SESSION || !SESSION.hunters) return;
    var hids = Object.keys(SESSION.hunters).sort();
    hids.forEach(function (hid) {
      var chip = makeChip(hid, SESSION.hunters[hid]);
      chips[hid] = chip;
      gridEl.appendChild(chip);
    });
    applySnapshot(SESSION);
  }

  function makeChip(hid, data) {
    var el = document.createElement('div');
    el.className = 'hunter-chip state-waiting';
    el.id = 'chip-' + hid;
    el.innerHTML =
      '<div class="hunter-chip-id">' + hid + '</div>' +
      '<div class="hunter-chip-code" id="code-' + hid + '">· · ·</div>' +
      '<div class="hunter-chip-status" id="status-' + hid + '">waiting</div>';
    return el;
  }

  // ── Snapshot renderer ───────────────────────────────────────────────────
  function applySnapshot(snap) {
    var hunters = snap.hunters || {};
    var ackedCount = 0;
    var currentPrompt = snap.current_prompt;

    Object.keys(hunters).forEach(function (hid) {
      var d  = hunters[hid];
      var el = chips[hid];
      if (!el) return;
      var codeEl   = el.querySelector('#code-' + hid);
      var statusEl = el.querySelector('#status-' + hid);

      el.className = 'hunter-chip state-' + chipState(d);
      if (codeEl) {
        codeEl.textContent = d.code
          ? d.code.split('').join(' ')
          : '· · ·';
      }
      if (statusEl) {
        statusEl.textContent = statusText(d, hid === currentPrompt);
      }
      if (d.acked) ackedCount++;
    });

    // Progress bar
    var pct = N_HUNTERS > 0 ? (ackedCount / N_HUNTERS) * 100 : 0;
    progressBar.style.width = pct + '%';
    progressLbl.textContent = ackedCount + ' / ' + N_HUNTERS;

    // Ready count
    if (readyN) readyN.textContent = snap.fresh_unassigned || 0;

    // Prompt spotlight
    if (currentPrompt && hunters[currentPrompt] && !hunters[currentPrompt].acked) {
      var h   = hunters[currentPrompt];
      promptHunter.textContent = currentPrompt;
      promptCode.textContent   = h.code ? h.code.split('').join(' ') : '— — —';
      promptBox.classList.add('visible');
    } else {
      promptBox.classList.remove('visible');
    }

    // Phase header
    if (snap.state === 'collecting') {
      phaseLabel.textContent = 'WAITING FOR HUNTERS';
      phaseTitle.textContent = 'Touch your gold logo pad once';
      phaseDesc.textContent  = 'Each hunter should touch the gold logo pad once. ' +
        'You can let go after the diamond appears — once everyone is ready, Reachy will assign each hunter a secret button code.';
    } else if (snap.state === 'prompting') {
      phaseLabel.textContent = 'IDENTIFICATION IN PROGRESS';
      phaseTitle.textContent = currentPrompt
        ? currentPrompt + ' — enter your code'
        : 'Assigning codes…';
      phaseDesc.textContent  = 'When you hear your name, press the three buttons shown above ' +
        'on your micro:bit (A and B). Your display stays on the diamond while you enter the code.';
    } else if (snap.state === 'complete') {
      phaseLabel.textContent = 'ALL IDENTIFIED';
      phaseTitle.textContent = '✓ All hunters ready!';
      phaseDesc.textContent  = 'Everyone has been confirmed. Press Start Hunt to begin.';
      promptBox.classList.remove('visible');
      startBtn.classList.add('visible');
    }

    // Error state
    if (snap.state === 'cancelled') {
      showAlert('Session cancelled or timed out. Returning to dashboard…');
      setTimeout(function () { window.location = '/'; }, 2500);
    }
  }

  function chipState(d) {
    if (d.acked)                     return 'acked';
    if (d.nonce && !d.acked)         return 'prompted';
    if (!d.nonce)                    return 'waiting';
    return 'ready';
  }

  function statusText(d, isCurrent) {
    if (d.acked)     return '✓ confirmed';
    if (isCurrent)   return 'entering code…';
    if (d.nonce)     return 'assigned';
    return 'waiting';
  }

  function showAlert(msg) {
    alertBox.textContent = msg;
    alertBox.classList.add('visible');
  }

  // ── SocketIO events ─────────────────────────────────────────────────────
  socket.on('connect', function () {
    // Ask for a fresh snapshot
    socket.emit('connect');
  });

  socket.on('reg_snapshot', function (snap) {
    applySnapshot(snap);
  });

  socket.on('redirect', function (data) {
    if (data && data.url) window.location = data.url;
  });

  // ── Start game (all ACKs received) ──────────────────────────────────────
  window.startGame = function () {
    startBtn.disabled = true;
    socket.emit('reg_complete');
  };

  // ── Boot ────────────────────────────────────────────────────────────────
  init();
}());
