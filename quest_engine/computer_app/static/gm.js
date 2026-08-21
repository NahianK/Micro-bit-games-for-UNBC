// gm.js - gamemaster console client.
//
// The server pushes a whole snapshot several times a second and this file just
// renders it. No client-side state to drift out of sync with the engine, which
// matters when a session is live and you cannot stop to debug.

const socket = io();

const el = (id) => document.getElementById(id);

// Remember which selects the gamemaster is actively using, so a snapshot
// arriving mid-choice does not yank the dropdown out from under them.
let packTouched = false;
let lastPack = null;

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------
document.querySelectorAll('button[data-action]').forEach((button) => {
  button.addEventListener('click', () => {
    socket.emit('control', { action: button.dataset.action });
  });
});

el('sel-pack').addEventListener('change', (event) => {
  packTouched = true;
  socket.emit('control', { action: 'pack', value: event.target.value });
  setTimeout(() => { packTouched = false; }, 1000);
});

el('sel-diff').addEventListener('change', (event) => {
  socket.emit('control', { action: 'difficulty', value: event.target.value });
});

// Prefill a sensible arg when the verb changes, from the verb table.
el('m-verb').addEventListener('change', (event) => {
  const option = event.target.selectedOptions[0];
  el('m-arg').value = option ? option.dataset.default : '';
});

el('m-send').addEventListener('click', () => {
  socket.emit('control', {
    action: 'manual',
    verb: el('m-verb').value,
    arg: el('m-arg').value.trim(),
    win: el('m-win').value.trim(),
    who: el('m-who').value,
  });
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
socket.on('voices', (info) => {
  const banner = el('banner-voices');
  if (info.missing > 0) {
    banner.classList.add('show');
    banner.textContent =
      `${info.missing} narration line(s) have no audio yet, so they will be ` +
      `printed in the terminal instead of spoken. Read them aloud yourself, or ` +
      `run tools/build_voice.py. Missing: ${info.examples.join(', ')}...`;
  } else {
    banner.classList.remove('show');
  }
});

socket.on('state', (state) => {
  renderHeader(state);
  renderStep(state);
  renderWands(state);
  renderScores(state);
  renderSession(state);
  renderLog(state);
});

function renderHeader(state) {
  const link = el('pill-link');
  link.textContent = state.link.connected
    ? `bridge on ${state.link.target}`
    : `no bridge (${state.link.target})`;
  link.className = 'pill ' + (state.link.connected ? 'good' : 'bad');

  el('pill-audio').textContent = state.audio || 'audio ?';

  // The robot is optional, so its pill disappears entirely rather than sitting
  // in an already-busy header saying it is not there.
  const robot = el('pill-robot');
  const robotText = state.robot || '';
  const robotOff = !robotText || robotText.startsWith('robot off');
  robot.style.display = robotOff ? 'none' : '';
  robot.textContent = robotText;
  robot.className = 'pill ' + (robotText.startsWith('no robot') ? 'bad' : 'good');

  el('pill-status').textContent = state.status;
  el('pill-status').className =
    'pill ' + (state.status === 'running' ? 'good'
      : state.status === 'paused' ? 'bad' : '');
}

function renderStep(state) {
  const step = state.step;
  const round = state.round;

  if (state.step_total) {
    el('step-counter').textContent =
      `step ${Math.min(state.step_index + 1, state.step_total)} of ${state.step_total}`;
  }
  el('step-id').textContent = step ? `[${step.id}]` : '';

  if (step) {
    el('whiteboard').textContent = step.whiteboard || (step.verb || '\u2014');
    el('script').textContent = step.say || '';
  } else if (state.status === 'finished') {
    el('whiteboard').textContent = 'THE END';
    el('script').textContent = 'Scenario complete. Scores are on the right.';
  }

  if (round) {
    el('verbline').textContent = round.description;
    const left = round.remaining_s;
    el('countdown').textContent = left > 0 ? `${left.toFixed(1)}s` : '';
    el('countdown').style.color = left > 0 && left < 2 ? 'var(--bad)' : 'var(--ink)';
  } else {
    el('verbline').textContent = '';
    el('countdown').textContent = '';
  }
}

function renderWands(state) {
  const round = state.round;
  const fastest = round && round.winners.length ? round.winners[0] : null;
  const container = el('wands');
  container.innerHTML = '';

  Object.keys(state.roster).sort((a, b) => a - b).forEach((pid) => {
    const info = state.roster[pid];
    const answer = round && round.answers ? round.answers[pid] : null;
    const addressed = round && round.expected.includes(Number(pid));

    const classes = ['wand'];
    if (!info.online) classes.push('off');
    if (answer) classes.push(answer.result === 'OK' ? 'ok' : 'bad');

    let statusText;
    if (!info.online) {
      statusText = info.ago === null ? 'never seen' : `silent ${info.ago}s`;
    } else if (round && !addressed) {
      statusText = 'not their turn';
    } else if (answer) {
      statusText = answer.result === 'OK' ? 'done'
        : answer.result === 'NOCAL' ? 'no compass' : 'missed';
    } else if (round) {
      statusText = 'waiting...';
    } else {
      statusText = 'ready';
    }

    const reaction = answer && answer.result === 'OK'
      ? `${(answer.ms / 1000).toFixed(2)}s` : '';

    const tile = document.createElement('div');
    tile.className = classes.join(' ');
    tile.innerHTML =
      `<div class="who">P${pid}</div>` +
      `<div class="st">${statusText}</div>` +
      `<div class="ms">${reaction}</div>` +
      `<div class="fastest">${Number(pid) === fastest ? 'fastest' : ''}</div>`;
    container.appendChild(tile);
  });
}

function renderScores(state) {
  const body = el('scores');
  const ids = Object.keys(state.scores).sort((a, b) => a - b);
  if (!ids.length) {
    body.innerHTML =
      '<tr><td colspan="4" style="color:var(--dim)">nothing yet</td></tr>';
    return;
  }
  body.innerHTML = ids.map((pid) => {
    const row = state.scores[pid];
    const best = row.best_ms ? `${(row.best_ms / 1000).toFixed(2)}s` : '\u2014';
    return `<tr><td>P${pid}</td><td>${row.passed}</td>` +
           `<td>${row.failed}</td><td>${best}</td></tr>`;
  }).join('');
}

function renderSession(state) {
  const select = el('sel-pack');
  if (!packTouched && (state.pack !== lastPack || select.options.length !== state.packs.length)) {
    select.innerHTML = state.packs
      .map((name) => `<option value="${name}">${name}</option>`).join('');
    select.value = state.pack;
    lastPack = state.pack;
  }
  if (el('sel-diff').value !== state.difficulty) {
    el('sel-diff').value = state.difficulty;
  }
  el('pack-blurb').textContent = state.title || '';
}

function renderLog(state) {
  el('log').innerHTML = state.log
    .map((line) => `<div>${escapeHtml(line)}</div>`).join('');
}

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
