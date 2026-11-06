const POLL_MS = 2000;

let allChampions = [];
let selectedRole = "top";
let selectedBuildChamp = null;
let isLive = false;
let lockedChamp = null; // when set, center column shows build instead of picks

/* ── Bootstrap ─────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  setupRoleButtons();
  setupChampInputs();
  fetchChampionList();
  poll();
  setInterval(poll, POLL_MS);
});

/* ── Role buttons ──────────────────────────────────────── */

function setupRoleButtons() {
  document.querySelectorAll(".role-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".role-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      selectedRole = btn.dataset.role;
      if (!isLive) fetchRecommendations();
    });
  });
}

/* ── Champion autocomplete inputs ──────────────────────── */

function setupChampInputs() {
  document.querySelectorAll(".champ-input").forEach(input => {
    const slot = input.closest(".champ-slot");
    const suggestions = slot.querySelector(".suggestions");

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (q.length < 1) { suggestions.classList.remove("open"); return; }
      const matches = allChampions.filter(c => c.name.toLowerCase().includes(q)).slice(0, 8);
      renderSuggestions(suggestions, matches, input);
    });

    input.addEventListener("focus", () => {
      if (input.value.trim().length >= 1) input.dispatchEvent(new Event("input"));
    });

    input.addEventListener("blur", () => {
      setTimeout(() => suggestions.classList.remove("open"), 150);
    });

    input.addEventListener("keydown", e => {
      const items = suggestions.querySelectorAll(".suggestion-item");
      const current = suggestions.querySelector(".highlighted");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!current && items.length) items[0].classList.add("highlighted");
        else if (current && current.nextElementSibling) { current.classList.remove("highlighted"); current.nextElementSibling.classList.add("highlighted"); }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (current && current.previousElementSibling) { current.classList.remove("highlighted"); current.previousElementSibling.classList.add("highlighted"); }
      } else if (e.key === "Enter") {
        e.preventDefault();
        const hl = suggestions.querySelector(".highlighted");
        if (hl) hl.click();
        else if (items.length === 1) items[0].click();
      }
    });
  });
}

function renderSuggestions(container, matches, input) {
  container.innerHTML = "";
  if (!matches.length) { container.classList.remove("open"); return; }
  matches.forEach(champ => {
    const div = document.createElement("div");
    div.className = "suggestion-item";
    div.textContent = champ.name;
    div.addEventListener("mousedown", e => {
      e.preventDefault();
      input.value = champ.name;
      input.classList.add("filled");
      container.classList.remove("open");
      fetchRecommendations();
    });
    container.appendChild(div);
  });
  container.classList.add("open");
}

/* ── Fetch champion list ───────────────────────────────── */

async function fetchChampionList() {
  try {
    const resp = await fetch("/api/champions");
    allChampions = await resp.json();
  } catch(e) { console.error("Failed to load champion list", e); }
}

/* ── Polling ───────────────────────────────────────────── */

async function poll() {
  try {
    const resp = await fetch("/api/state");
    const state = await resp.json();
    renderState(state);
  } catch(e) { /* server not ready yet */ }
}

function renderState(state) {
  // Connection
  const dot = document.getElementById("connection-dot");
  const connText = document.getElementById("connection-text");
  dot.className = "dot " + (state.lcu_connected ? "connected" : "disconnected");
  connText.textContent = state.lcu_connected ? "Connected" : "Disconnected";

  // Summoner
  const si = document.getElementById("summoner-info");
  if (state.summoner) {
    si.textContent = state.summoner.name + (state.summoner.tag ? "#" + state.summoner.tag : "");
  } else {
    si.textContent = "";
  }

  // Patch
  document.getElementById("patch-badge").textContent = state.patch || "";

  // Recap check
  checkRecap(state);

  // Phase
  const pb = document.getElementById("phase-badge");
  pb.className = "badge phase-" + (state.phase || "None");
  const phaseLabels = { None: "LOBBY", Lobby: "LOBBY", Matchmaking: "QUEUE", ReadyCheck: "READY", ChampSelect: "CHAMP SELECT", InProgress: "IN GAME", EndOfGame: "POST GAME" };
  pb.textContent = phaseLabels[state.phase] || state.phase || "LOBBY";

  // Champ select auto-fill
  if (state.champ_select) {
    isLive = true;
    fillFromChampSelect(state.champ_select);
    if (state.recommendations && state.recommendations.length) {
      renderRecommendations(state.recommendations);
    }
  } else {
    if (isLive) {
      isLive = false;
      if (lockedChamp) unlockChampion();
    }
  }
}

function fillFromChampSelect(cs) {
  // Set role
  if (cs.my_position) {
    document.querySelectorAll(".role-btn").forEach(b => {
      b.classList.toggle("active", b.dataset.role === cs.my_position);
    });
    selectedRole = cs.my_position;
  }

  // Auto-lock: if my champion is picked, lock it
  const me = (cs.my_team || []).find(m => m.is_me);
  if (me && me.champion && me.champion !== lockedChamp) {
    lockChampion(me.champion, cs.my_position);
  } else if (me && !me.champion && lockedChamp) {
    unlockChampion();
  }

  // Fill ally slots
  const allyInputs = document.querySelectorAll(".ally-input");
  const allies = (cs.my_team || []).filter(m => !m.is_me && m.champion);
  allies.forEach((member, i) => {
    if (allyInputs[i]) {
      allyInputs[i].value = member.champion;
      allyInputs[i].classList.toggle("filled", !!member.champion);
    }
  });

  // Fill enemy slots
  const enemyInputs = document.querySelectorAll(".enemy-input");
  (cs.enemy_team || []).forEach((member, i) => {
    if (enemyInputs[i]) {
      enemyInputs[i].value = member.champion || "";
      enemyInputs[i].classList.toggle("filled", !!member.champion);
    }
  });
}

/* ── Recommendations ───────────────────────────────────── */

async function fetchRecommendations() {
  const allies = getInputValues(".ally-input");
  const enemies = getInputValues(".enemy-input");
  const params = new URLSearchParams();
  params.set("role", selectedRole);
  allies.forEach(a => params.append("allies", a));
  enemies.forEach(e => params.append("enemies", e));

  try {
    const resp = await fetch("/api/recommend?" + params.toString());
    const recs = await resp.json();
    renderRecommendations(recs);
  } catch(e) { console.error(e); }
}

function getInputValues(selector) {
  return Array.from(document.querySelectorAll(selector))
    .map(inp => inp.value.trim())
    .filter(v => v.length > 0);
}

function renderRecommendations(recs) {
  if (lockedChamp) return;

  const container = document.getElementById("recommendations");
  if (!recs || !recs.length) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Pick a role and add enemies to see recommendations</div>';
    return;
  }

  container.innerHTML = recs.map((r, i) => {
    const b = r.build || {};
    const buildLine = [
      b.keystone ? `<span class="rec-keystone">${b.keystone}</span>` : '',
      b.core ? b.core.map(item => `<span class="rec-core-item">${item}</span>`).join('') : '',
      b.boots ? `<span class="rec-boots">${b.boots}</span>` : '',
    ].filter(Boolean).join('');

    const metaLine = [
      b.spells ? b.spells.join(' + ') : '',
      b.skills || '',
      b.wr ? `${b.wr}% WR` : '',
    ].filter(Boolean).join(' · ');

    return `
    <div class="rec-item" data-champ="${r.champion}" onclick="lockChampion('${r.champion}')">
      <div class="rec-rank ${i < 3 ? 'top3' : ''}">${i + 1}</div>
      <div class="rec-info">
        <div class="rec-name">${r.champion} <span class="tier-badge tier-${r.tier}">${r.tier}</span></div>
        <div class="rec-reasons">${r.reasons.join(' · ')}</div>
        <div class="rec-build-preview">${buildLine}</div>
        <div class="rec-build-meta">${metaLine}</div>
      </div>
      <div class="rec-score">${Math.round(r.score)}</div>
    </div>`;
  }).join("");
}

async function lockChampion(champion, role) {
  lockedChamp = champion;
  role = role || selectedRole;

  const container = document.getElementById("recommendations");
  const recHeader = container.closest('.panel').querySelector('h2');
  recHeader.textContent = 'YOUR BUILD';

  // Hide the bottom build panel since we're showing it in the center
  document.getElementById("build-panel").classList.add("hidden");

  try {
    const resp = await fetch(`/api/build/${encodeURIComponent(champion)}/${role}`);
    const data = await resp.json();
    if (data.error) { unlockChampion(); return; }

    const build = data.build;
    const runes = build.runes || [];
    const trees = build.rune_trees || [];

    let runesHtml = "";
    if (trees[0]) runesHtml += `<div class="rune-tree-label">${trees[0]}</div>`;
    if (runes[0]) runesHtml += `<div class="rune-row rune-keystone">◆ ${runes[0]}</div>`;
    for (let i = 1; i <= 3 && i < runes.length; i++) {
      runesHtml += `<div class="rune-row rune-primary">▸ ${runes[i]}</div>`;
    }
    if (trees[1]) runesHtml += `<div class="rune-tree-label" style="margin-top:10px">${trees[1]}</div>`;
    for (let i = 4; i < runes.length; i++) {
      runesHtml += `<div class="rune-row rune-secondary">▹ ${runes[i]}</div>`;
    }
    if (build.shards) {
      runesHtml += `<div class="rune-shards">Shards: ${build.shards.join(" / ")}</div>`;
    }

    let itemsHtml = "";
    if (build.start && build.start.length) {
      itemsHtml += `<div class="item-group"><div class="item-group-label">START</div><div class="item-list">${build.start.map(i => `<span class="item-tag">${i}</span>`).join("")}</div></div>`;
    }
    if (build.core && build.core.length) {
      itemsHtml += `<div class="item-group"><div class="item-group-label">CORE</div><div class="item-list">${build.core.map(i => `<span class="item-tag core">${i}</span>`).join("")}</div></div>`;
    }
    if (build.boots) {
      itemsHtml += `<div class="item-group"><div class="item-group-label">BOOTS</div><div class="item-list"><span class="item-tag boots">${build.boots}</span></div></div>`;
    }
    if (build.situational && build.situational.length) {
      itemsHtml += `<div class="item-group"><div class="item-group-label">SITUATIONAL</div><div class="item-list">${build.situational.map(i => `<span class="item-tag">${i}</span>`).join("")}</div></div>`;
    }

    container.innerHTML = `
      <div class="locked-build">
        <div class="locked-header">
          <div class="locked-champ-name">${data.champion}</div>
          <div class="locked-meta">${capitalize(data.role)} · ${data.tier}-Tier${build.wr ? ` · ${build.wr}% WR` : ''}${build.pr ? ` · ${build.pr}% Pick` : ''}</div>
          <div class="locked-actions">
            <button class="btn-gold" onclick="importRunes('${data.champion}', '${data.role}')" id="import-runes-btn">Import Runes</button>
            <button class="btn-unlock" onclick="unlockChampion()">Back to Picks</button>
          </div>
        </div>
        <div class="locked-body">
          <div class="locked-section">
            <h3>RUNES</h3>
            ${runesHtml}
          </div>
          <div class="locked-section">
            <h3>ITEMS</h3>
            ${itemsHtml}
          </div>
        </div>
        <div class="locked-footer">
          <div><strong>Spells:</strong> ${(build.spells || []).join(" + ")}</div>
          <div><strong>Skills:</strong> ${build.skills || ""}</div>
        </div>
      </div>`;
  } catch(e) { console.error(e); unlockChampion(); }
}

function unlockChampion() {
  lockedChamp = null;
  const recHeader = document.querySelector('.rec-panel h2');
  if (recHeader) recHeader.textContent = 'BEST PICKS';
  document.getElementById("build-panel").classList.add("hidden");
  fetchRecommendations();
}

/* ── Build panel ───────────────────────────────────────── */

async function showBuild(champion, role) {
  selectedBuildChamp = champion;
  role = role || selectedRole;
  const panel = document.getElementById("build-panel");

  try {
    const resp = await fetch(`/api/build/${encodeURIComponent(champion)}/${role}`);
    const data = await resp.json();
    if (data.error) { panel.classList.add("hidden"); return; }

    panel.classList.remove("hidden");
    document.getElementById("build-title").textContent = data.champion;
    document.getElementById("build-meta").textContent =
      `${capitalize(data.role)} · ${data.tier}-Tier` +
      (data.build.wr ? ` · ${data.build.wr}% WR` : '') +
      (data.build.pr ? ` · ${data.build.pr}% Pick` : '');

    renderRunes(data.build);
    renderItems(data.build);
    document.getElementById("build-spells").textContent = (data.build.spells || []).join(" + ");
    document.getElementById("build-skills").textContent = data.build.skills || "";

    const importBtn = document.getElementById("import-runes-btn");
    importBtn.classList.remove("hidden");
    importBtn.onclick = () => importRunes(data.champion, data.role);

    // Re-highlight in recommendations
    document.querySelectorAll(".rec-item").forEach(el => {
      el.classList.toggle("selected", el.dataset.champ === champion);
    });

  } catch(e) { console.error(e); }
}

function renderRunes(build) {
  const container = document.getElementById("build-runes");
  const runes = build.runes || [];
  const trees = build.rune_trees || [];

  let html = "";
  if (trees[0]) html += `<div class="rune-tree-label">${trees[0]}</div>`;
  if (runes[0]) html += `<div class="rune-row rune-keystone">◆ ${runes[0]}</div>`;
  for (let i = 1; i <= 3 && i < runes.length; i++) {
    html += `<div class="rune-row rune-primary">▸ ${runes[i]}</div>`;
  }
  if (trees[1]) html += `<div class="rune-tree-label" style="margin-top:10px">${trees[1]}</div>`;
  for (let i = 4; i < runes.length; i++) {
    html += `<div class="rune-row rune-secondary">▹ ${runes[i]}</div>`;
  }
  if (build.shards) {
    html += `<div class="rune-shards">Shards: ${build.shards.join(" / ")}</div>`;
  }
  container.innerHTML = html;
}

function renderItems(build) {
  const container = document.getElementById("build-items");
  let html = "";

  if (build.start && build.start.length) {
    html += `<div class="item-group"><div class="item-group-label">START</div><div class="item-list">${build.start.map(i => `<span class="item-tag">${i}</span>`).join("")}</div></div>`;
  }
  if (build.core && build.core.length) {
    html += `<div class="item-group"><div class="item-group-label">CORE</div><div class="item-list">${build.core.map(i => `<span class="item-tag core">${i}</span>`).join("")}</div></div>`;
  }
  if (build.boots) {
    html += `<div class="item-group"><div class="item-group-label">BOOTS</div><div class="item-list"><span class="item-tag boots">${build.boots}</span></div></div>`;
  }
  if (build.situational && build.situational.length) {
    html += `<div class="item-group"><div class="item-group-label">SITUATIONAL</div><div class="item-list">${build.situational.map(i => `<span class="item-tag">${i}</span>`).join("")}</div></div>`;
  }
  container.innerHTML = html;
}

/* ── Post-Game Recap ──────────────────────────────────── */

let recapShown = false;
let recapPolling = false;

function checkRecap(state) {
  if (state.recap_analyzing && !recapPolling) {
    recapPolling = true;
    pollRecap();
  }
  if (state.recap_available && !recapShown) {
    fetchRecap();
  }
}

async function fetchRecap() {
  try {
    const resp = await fetch("/api/recap");
    const data = await resp.json();
    if (data.status === "done") {
      renderRecap(data);
      recapShown = true;
      recapPolling = false;
    } else if (data.status === "analyzing") {
      showRecapLoading();
    } else if (data.status === "error") {
      showRecapError(data.message);
    }
  } catch(e) { console.error(e); }
}

function pollRecap() {
  const interval = setInterval(async () => {
    try {
      const resp = await fetch("/api/recap");
      const data = await resp.json();
      if (data.status === "done") {
        clearInterval(interval);
        recapPolling = false;
        renderRecap(data);
        recapShown = true;
      } else if (data.status === "error") {
        clearInterval(interval);
        recapPolling = false;
        showRecapError(data.message);
      }
    } catch(e) {}
  }, 2000);
}

function renderRecap(data) {
  const panel = document.getElementById("recap-panel");
  panel.classList.remove("hidden");

  const resultClass = data.result === "Victory" ? "victory" : "defeat";
  document.getElementById("recap-meta").textContent =
    `${data.champion} · ${data.result}`;

  document.getElementById("recap-stats").innerHTML = `
    <div class="stat-card ${resultClass}">
      <div class="stat-value">${data.result === "Victory" ? "W" : "L"}</div>
      <div class="stat-label">RESULT</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${data.kda}</div>
      <div class="stat-label">KDA</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${data.cs}</div>
      <div class="stat-label">CS (${data.cs_per_min}/min)</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${(data.damage / 1000).toFixed(1)}k</div>
      <div class="stat-label">DAMAGE</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${data.vision}</div>
      <div class="stat-label">VISION</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${(data.gold / 1000).toFixed(1)}k</div>
      <div class="stat-label">GOLD</div>
    </div>
  `;

  document.getElementById("recap-analysis").textContent = data.analysis;
}

function showRecapLoading() {
  const panel = document.getElementById("recap-panel");
  panel.classList.remove("hidden");
  document.getElementById("recap-meta").textContent = "Analyzing...";
  document.getElementById("recap-stats").innerHTML = "";
  document.getElementById("recap-analysis").innerHTML =
    '<div class="analysis-loading">AI is reviewing your game...</div>';
}

function showRecapError(msg) {
  const panel = document.getElementById("recap-panel");
  panel.classList.remove("hidden");
  document.getElementById("recap-meta").textContent = "Error";
  document.getElementById("recap-stats").innerHTML = "";
  document.getElementById("recap-analysis").textContent = msg || "Analysis failed";
}

async function reanalyze() {
  const btn = document.getElementById("reanalyze-btn");
  btn.textContent = "Analyzing...";
  btn.disabled = true;
  recapShown = false;

  try {
    await fetch("/api/recap/reanalyze", { method: "POST" });
    showRecapLoading();
    recapPolling = true;
    pollRecap();
  } catch(e) {}

  setTimeout(() => { btn.textContent = "Re-analyze"; btn.disabled = false; }, 3000);
}

/* ── Rune Import ──────────────────────────────────────── */

async function importRunes(champion, role) {
  const btn = document.getElementById("import-runes-btn");
  btn.textContent = "Importing...";
  btn.disabled = true;

  try {
    const resp = await fetch("/api/import-runes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ champion, role }),
    });
    const data = await resp.json();
    if (data.success) {
      btn.textContent = "Imported!";
      btn.style.background = "linear-gradient(135deg, #2e7d32, #4caf50)";
      setTimeout(() => {
        btn.textContent = "Import Runes";
        btn.style.background = "";
        btn.disabled = false;
      }, 2000);
    } else {
      btn.textContent = data.error || "Failed";
      setTimeout(() => { btn.textContent = "Import Runes"; btn.disabled = false; }, 2000);
    }
  } catch(e) {
    btn.textContent = "Error";
    setTimeout(() => { btn.textContent = "Import Runes"; btn.disabled = false; }, 2000);
  }
}

function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }
