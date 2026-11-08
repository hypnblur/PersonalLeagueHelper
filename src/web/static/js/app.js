const POLL_MS = 2000;

let allChampions = [];
let selectedRole = "top";
let selectedBuildChamp = null;
let selectedBuildOption = null;
let selectedBuildOptions = [];
let selectedBuildData = null;
let isLive = false;
let lockedChamp = null;
let safeRuneImport = true;

document.addEventListener("DOMContentLoaded", () => {
  setupRoleButtons();
  setupChampInputs();
  fetchChampionList();
  refreshCompanion();
  poll();
  setInterval(poll, POLL_MS);
});

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
    input.addEventListener("blur", () => setTimeout(() => suggestions.classList.remove("open"), 150));
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

async function fetchChampionList() {
  try {
    const resp = await fetch("/api/champions");
    allChampions = await resp.json();
    const dl = document.getElementById("champion-datalist");
    if (dl) dl.innerHTML = allChampions.map(c => `<option value="${esc(c.name)}"></option>`).join("");
  } catch(e) { console.error("Failed to load champion list", e); }
}

async function poll() {
  try {
    const resp = await fetch("/api/state");
    const state = await resp.json();
    renderState(state);
  } catch(e) { /* server not ready */ }
}

function renderState(state) {
  safeRuneImport = !!state.safe_rune_import;
  const dot = document.getElementById("connection-dot");
  const connText = document.getElementById("connection-text");
  dot.className = "dot " + (state.lcu_connected ? "connected" : "disconnected");
  connText.textContent = state.lcu_connected ? "Connected" : "Disconnected";

  const si = document.getElementById("summoner-info");
  si.textContent = state.summoner ? (state.summoner.name + (state.summoner.tag ? "#" + state.summoner.tag : "")) : "";
  document.getElementById("patch-badge").textContent = state.patch || "";
  checkRecap(state);

  const pb = document.getElementById("phase-badge");
  pb.className = "badge phase-" + (state.phase || "None");
  const phaseLabels = { None: "LOBBY", Lobby: "LOBBY", Matchmaking: "QUEUE", ReadyCheck: "READY", ChampSelect: "CHAMP SELECT", InProgress: "IN GAME", EndOfGame: "POST GAME", Reconnect: "RECONNECT" };
  pb.textContent = phaseLabels[state.phase] || state.phase || "LOBBY";

  if (state.champ_select) {
    isLive = true;
    fillFromChampSelect(state.champ_select);
    if (state.recommendations && state.recommendations.length) renderRecommendations(state.recommendations);
  } else {
    if (isLive) { isLive = false; if (lockedChamp) unlockChampion(); }
  }
  renderPlayerIntel(state.player_intel || [], state.phase);
}

function fillFromChampSelect(cs) {
  if (cs.my_position) {
    document.querySelectorAll(".role-btn").forEach(b => b.classList.toggle("active", b.dataset.role === cs.my_position));
    selectedRole = cs.my_position;
  }
  const me = (cs.my_team || []).find(m => m.is_me);
  if (me && me.champion && me.champion !== lockedChamp) lockChampion(me.champion, cs.my_position);
  else if (me && !me.champion && lockedChamp) unlockChampion();

  const allyInputs = document.querySelectorAll(".ally-input");
  const allies = (cs.my_team || []).filter(m => !m.is_me && m.champion);
  allies.forEach((member, i) => {
    if (allyInputs[i]) { allyInputs[i].value = member.champion; allyInputs[i].classList.toggle("filled", !!member.champion); }
  });
  const enemyInputs = document.querySelectorAll(".enemy-input");
  (cs.enemy_team || []).forEach((member, i) => {
    if (enemyInputs[i]) { enemyInputs[i].value = member.champion || ""; enemyInputs[i].classList.toggle("filled", !!member.champion); }
  });
}

async function fetchRecommendations() {
  const allies = getInputValues(".ally-input");
  const enemies = getInputValues(".enemy-input");
  const params = new URLSearchParams();
  params.set("role", selectedRole);
  allies.forEach(a => params.append("allies", a));
  enemies.forEach(e => params.append("enemies", e));
  try {
    const resp = await fetch("/api/recommend?" + params.toString());
    renderRecommendations(await resp.json());
  } catch(e) { console.error(e); }
}
function getInputValues(selector) { return Array.from(document.querySelectorAll(selector)).map(inp => inp.value.trim()).filter(v => v); }

function renderRecommendations(recs) {
  if (lockedChamp) return;
  const container = document.getElementById("recommendations");
  if (!recs || !recs.length) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Pick a role and add locked-in enemies to see recommendations (owned + good vs enemy comp + high WR)</div>';
    return;
  }
  container.innerHTML = recs.map((r, i) => {
    const b = r.build || {};
    const owned = r.owned === true ? '<span class="badge owned-badge">OWNED</span> ' : '';
    const personal = r.personal && r.personal.games ? ` · You ${r.personal.wr}% (${r.personal.games}g)` : '';
    const buildLine = [b.keystone ? `<span class="rec-keystone">${esc(b.keystone)}</span>` : '', b.core ? b.core.map(item => `<span class="rec-core-item">${esc(item)}</span>`).join('') : '', b.boots ? `<span class="rec-boots">${esc(b.boots)}</span>` : ''].filter(Boolean).join('');
    const metaLine = [b.spells ? b.spells.join(' + ') : '', b.skills || '', b.wr ? `${b.wr}% WR` : ''].filter(Boolean).join(' · ');
    return `<div class="rec-item" data-champ="${esc(r.champion)}" onclick="lockChampion('${escAttr(r.champion)}')"><div class="rec-rank ${i < 3 ? 'top3' : ''}">${i + 1}</div><div class="rec-info"><div class="rec-name">${owned}${esc(r.champion)} <span class="tier-badge tier-${esc(r.tier)}">${esc(r.tier)}</span></div><div class="rec-reasons">${esc((r.reasons||[]).join(' · '))}${esc(personal)}</div><div class="rec-build-preview">${buildLine}</div><div class="rec-build-meta">${esc(metaLine)}</div></div><div class="rec-score">${Math.round(r.score)}</div></div>`;
  }).join("");
}

async function lockChampion(champion, role) {
  lockedChamp = champion;
  role = role || selectedRole;
  const container = document.getElementById("recommendations");
  const recHeader = container.closest('.panel').querySelector('h2');
  recHeader.textContent = 'YOUR BUILD — 3 OPTIONS (highest WR)';
  document.getElementById("build-panel").classList.add("hidden");
  try {
    const enemies = getInputValues(".enemy-input");
    const params = new URLSearchParams(); enemies.forEach(e => params.append("enemies", e));
    const resp = await fetch(`/api/build/${encodeURIComponent(champion)}/${encodeURIComponent(role)}?${params.toString()}`);
    const data = await resp.json();
    if (data.error) { unlockChampion(); return; }
    selectedBuildData = data;
    selectedBuildOptions = data.build_options || (data.build ? [data.build] : []);
    selectedBuildOption = 0;
    renderLockedBuild(data);
  } catch(e) { console.error(e); unlockChampion(); }
}

function renderBuildOptionBody(build) {
  const runes = build.runes || [];
  const trees = build.rune_trees || [];
  let runesHtml = "";
  if (trees[0]) runesHtml += `<div class="rune-tree-label">${esc(trees[0])}</div>`;
  if (runes[0]) runesHtml += `<div class="rune-row rune-keystone">◆ ${esc(runes[0])}</div>`;
  for (let i = 1; i <= 3 && i < runes.length; i++) runesHtml += `<div class="rune-row rune-primary">▸ ${esc(runes[i])}</div>`;
  if (trees[1]) runesHtml += `<div class="rune-tree-label" style="margin-top:10px">${esc(trees[1])}</div>`;
  for (let i = 4; i < runes.length; i++) runesHtml += `<div class="rune-row rune-secondary">▹ ${esc(runes[i])}</div>`;
  if (build.shards) runesHtml += `<div class="rune-shards">Shards: ${esc(build.shards.join(" / "))}</div>`;
  let itemsHtml = "";
  if (build.start?.length) itemsHtml += `<div class="item-group"><div class="item-group-label">START</div><div class="item-list">${build.start.map(i => `<span class="item-tag">${esc(i)}</span>`).join("")}</div></div>`;
  if (build.core?.length) itemsHtml += `<div class="item-group"><div class="item-group-label">CORE</div><div class="item-list">${build.core.map(i => `<span class="item-tag core">${esc(i)}</span>`).join("")}</div></div>`;
  if (build.boots) itemsHtml += `<div class="item-group"><div class="item-group-label">BOOTS</div><div class="item-list"><span class="item-tag boots">${esc(build.boots)}</span></div></div>`;
  if (build.situational?.length) itemsHtml += `<div class="item-group"><div class="item-group-label">SITUATIONAL</div><div class="item-list">${build.situational.map(i => `<span class="item-tag">${esc(i)}</span>`).join("")}</div></div>`;
  return { runesHtml, itemsHtml };
}

function renderLockedBuild(data) {
  const options = selectedBuildOptions.length ? selectedBuildOptions : [data.build || {}];
  const idx = Math.min(selectedBuildOption || 0, options.length - 1);
  const build = options[idx] || {};
  const body = renderBuildOptionBody(build);
  const optBtns = options.map((o, i) => {
    const wr = o.wr != null ? `${o.wr}% WR` : 'WR n/a';
    const label = o.name || (i === 0 ? 'Highest WR' : `Option ${i+1}`);
    return `<button class="build-opt-btn ${i===idx?'active':''}" onclick="selectBuildOption(${i})"><span class="opt-name">${esc(label)}</span><span class="opt-wr">${esc(wr)}</span></button>`;
  }).join('');
  const note = build.note ? `<div class="muted small" style="margin:8px 0">${esc(build.note)}</div>` : '';
  const container = document.getElementById("recommendations");
  container.innerHTML = `<div class="locked-build"><div class="locked-header"><div class="locked-champ-name">${esc(data.champion)}</div><div class="locked-meta">${esc(capitalize(data.role))} · ${esc(data.tier)}-Tier · ${options.length} build options${build.wr != null ? ` · selected ${build.wr}% WR` : ''}</div><div class="locked-actions"><button class="btn-gold" onclick="importSelectedRunes('${escAttr(data.champion)}', '${escAttr(data.role)}')" id="import-runes-btn">Import Selected Runes</button><button class="btn-unlock" onclick="unlockChampion()">Back to Picks</button></div></div><div class="build-options">${optBtns}</div>${note}<div class="locked-body"><div class="locked-section"><h3>RUNES</h3>${body.runesHtml}</div><div class="locked-section"><h3>ITEMS</h3>${body.itemsHtml}</div></div><div class="locked-footer"><div><strong>Spells:</strong> ${esc((build.spells || []).join(" + "))}</div><div><strong>Skills:</strong> ${esc(build.skills || "")}</div></div></div>`;
}

function selectBuildOption(i) { selectedBuildOption = i; renderLockedBuild(selectedBuildData || { champion: lockedChamp, role: selectedRole, tier: '?', build_options: selectedBuildOptions }); }

function unlockChampion() {
  lockedChamp = null; selectedBuildOptions = []; selectedBuildOption = 0; selectedBuildData = null;
  const recHeader = document.querySelector('.rec-panel h2');
  if (recHeader) recHeader.textContent = 'BEST PICKS';
  document.getElementById("build-panel").classList.add("hidden");
  fetchRecommendations();
}

async function showBuild(champion, role) { return lockChampion(champion, role); }

function importSelectedRunes(champion, role) {
  const build = selectedBuildOptions[selectedBuildOption || 0];
  return importRunes(champion, role, false, build, build?.name);
}

async function importRunes(champion, role, confirm=false, build=null, optionName=null) {
  const btn = document.getElementById("import-runes-btn");
  if (btn) { btn.textContent = "Importing..."; btn.disabled = true; }
  try {
    const payload = { champion, role, confirm };
    if (build) payload.build = build;
    if (optionName) payload.option_name = optionName;
    const resp = await fetch("/api/import-runes", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
    const data = await resp.json();
    if (data.needs_confirmation && !confirm) {
      const p = data.preview || {};
      const target = p.target ? `\nWill replace app page: ${p.target.name} (#${p.target.id})` : "\nWill create a new app rune page.";
      const opt = optionName ? `\nBuild option: ${optionName}` : '';
      if (window.confirm(`Import rune page for ${champion} (${role})?${opt}${target}\n\nSafe mode only manages pages with the app prefix.`)) {
        return importRunes(champion, role, true, build, optionName);
      }
      if (btn) { btn.textContent = "Import Selected Runes"; btn.disabled = false; }
      return;
    }
    if (data.success) {
      if (btn) { btn.textContent = "Imported!"; setTimeout(() => { btn.textContent = "Import Selected Runes"; btn.disabled = false; }, 1800); }
      else alert(data.message || "Imported");
    } else {
      if (btn) { btn.textContent = data.error || "Failed"; setTimeout(() => { btn.textContent = "Import Selected Runes"; btn.disabled = false; }, 2200); }
      else alert(data.error || "Failed");
    }
  } catch(e) {
    if (btn) { btn.textContent = "Error"; setTimeout(() => { btn.textContent = "Import Selected Runes"; btn.disabled = false; }, 2200); }
  }
}

/* Post-game recap */
let recapShown = false, recapPolling = false, recapPollTimer = null;
function checkRecap(state) {
  if (state.recap_analyzing && !recapPolling) { recapPolling = true; pollRecap(1000); }
  if (state.recap_available && !recapShown) fetchRecap();
}
async function fetchRecap() {
  try {
    const data = await (await fetch("/api/recap")).json();
    if (data.status === "done" || data.status === "no_ai") { renderRecap(data); recapShown = true; recapPolling = false; }
    else if (data.status === "analyzing") renderRecapProgress(data);
    else if (data.status === "error") showRecapError(data.message);
  } catch(e) { console.error(e); }
}
function pollRecap(ms=1500) {
  if (recapPollTimer) clearInterval(recapPollTimer);
  recapPollTimer = setInterval(async () => {
    try {
      const data = await (await fetch("/api/recap")).json();
      if (data.status === "done" || data.status === "no_ai") { clearInterval(recapPollTimer); recapPollTimer=null; recapPolling = false; renderRecap(data); recapShown = true; refreshCompanion(); }
      else if (data.status === "analyzing") { renderRecapProgress(data); }
      else if (data.status === "error") { clearInterval(recapPollTimer); recapPollTimer=null; recapPolling = false; showRecapError(data.message); refreshCompanion(); }
    } catch(e) {}
  }, ms);
}
function renderRecapProgress(data) {
  const panel = document.getElementById("recap-panel"); panel.classList.remove("hidden");
  document.getElementById("recap-meta").textContent = `${data.champion || ''} · Analyzing...`;
  if (data.kda) renderRecapStats(data);
  const text = data.analysis || '';
  document.getElementById("recap-analysis").textContent = text ? text + '\n▍' : 'AI is reviewing your game...';
}
function renderRecapStats(data) {
  const resultClass = data.result === "Victory" ? "victory" : "defeat";
  document.getElementById("recap-stats").innerHTML = `
    <div class="stat-card ${resultClass}"><div class="stat-value">${data.result === "Victory" ? "W" : "L"}</div><div class="stat-label">RESULT</div></div>
    <div class="stat-card"><div class="stat-value">${esc(data.kda || '')}</div><div class="stat-label">KDA</div></div>
    <div class="stat-card"><div class="stat-value">${esc(String(data.cs ?? ""))}</div><div class="stat-label">CS (${esc(String(data.cs_per_min ?? ""))}/min)</div></div>
    <div class="stat-card"><div class="stat-value">${data.damage != null ? (data.damage/1000).toFixed(1)+'k':''}</div><div class="stat-label">DAMAGE</div></div>
    <div class="stat-card"><div class="stat-value">${esc(String(data.vision ?? ""))}</div><div class="stat-label">VISION</div></div>
    <div class="stat-card"><div class="stat-value">${data.gold != null ? (data.gold/1000).toFixed(1)+'k':''}</div><div class="stat-label">GOLD</div></div>`;
}
function renderRecap(data) {
  const panel = document.getElementById("recap-panel");
  panel.classList.remove("hidden");
  document.getElementById("recap-meta").textContent = `${data.champion || ""} · ${data.result || ""}`;
  if (data.kda) renderRecapStats(data);
  document.getElementById("recap-analysis").textContent = data.analysis || data.message || "";
}
function showRecapLoading() { renderRecapProgress({status:'analyzing'}); }
function showRecapError(msg) {
  const panel = document.getElementById("recap-panel"); panel.classList.remove("hidden");
  document.getElementById("recap-meta").textContent = "Error";
  document.getElementById("recap-stats").innerHTML = "";
  document.getElementById("recap-analysis").textContent = msg || "Analysis failed";
}
async function reanalyze() {
  const btn = document.getElementById("reanalyze-btn"); btn.textContent = "Analyzing..."; btn.disabled = true; recapShown = false;
  try { await fetch("/api/recap/reanalyze", { method: "POST" }); showRecapLoading(); recapPolling = true; pollRecap(1000); } catch(e) {}
  setTimeout(() => { btn.textContent = "Re-analyze"; btn.disabled = false; }, 3000);
}

/* Companion */
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(el => el.classList.toggle('hidden', el.id !== `tab-${name}`));
  if (name === 'insights' || name === 'matches') loadInsights();
  if (name === 'matches') loadMatches();
  if (name === 'pool') loadPool();
  if (name === 'notes') loadNotes();
  if (name === 'settings') loadSettings();
}
function refreshCompanion() { loadInsights(); loadPool(); loadNotes(); }
function openSettings() { switchTab('settings'); document.querySelector('.companion-panel')?.scrollIntoView({behavior:'smooth'}); }

async function loadInsights() {
  try {
    const d = await (await fetch('/api/insights?limit=30')).json();
    const s = document.getElementById('insights-summary');
    if (!d.count) { s.innerHTML = '<div class="muted">No saved matches yet. Play a game (or run with LCU connected) to build your history.</div>'; document.getElementById('insights-recent').innerHTML=''; document.getElementById('insights-champs').innerHTML=''; return; }
    s.innerHTML = [
      stat('Games', d.count), stat('Winrate', `${d.winrate}%`), stat('Avg KDA', d.avg_kda), stat('Avg Deaths', d.avg_deaths),
      stat('CS/min', d.avg_cs_per_min), stat('Vision', d.avg_vision), stat('Dmg Share', d.avg_damage_share != null ? `${d.avg_damage_share}%` : '—'), stat('Avg Kills', d.avg_kills)
    ].join('');
    document.getElementById('insights-recent').innerHTML = `<table class="mini-table"><thead><tr><th>Result</th><th>Champ</th><th>KDA</th><th>CS/m</th><th>Vis</th></tr></thead><tbody>${(d.recent||[]).map(m=>`<tr><td class="${m.result==='Victory'?'w':'l'}">${m.result==='Victory'?'W':'L'}</td><td>${esc(m.champion||'')}</td><td>${esc(m.kda||'')}</td><td>${esc(String(m.cs_per_min??''))}</td><td>${esc(String(m.vision??''))}</td></tr>`).join('')}</tbody></table>`;
    document.getElementById('insights-champs').innerHTML = `<table class="mini-table"><thead><tr><th>Champion</th><th>Games</th><th>WR</th></tr></thead><tbody>${(d.by_champion||[]).map(c=>`<tr><td>${esc(c.champion)}</td><td>${c.games}</td><td>${c.wr}%</td></tr>`).join('')}</tbody></table>`;
  } catch(e) {}
}
function stat(label, value) { return `<div class="insight-stat"><div class="insight-val">${esc(String(value ?? '—'))}</div><div class="insight-lbl">${esc(label)}</div></div>`; }

async function loadMatches() {
  try {
    const rows = await (await fetch('/api/matches?limit=25')).json();
    const el = document.getElementById('matches-list');
    if (!rows.length) { el.innerHTML = '<div class="muted">No matches saved.</div>'; return; }
    el.innerHTML = `<table class="mini-table"><thead><tr><th>Time</th><th>Result</th><th>Champion</th><th>KDA</th><th>CS/m</th><th>Vision</th><th>Dmg Share</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${new Date(r.created_at*1000).toLocaleString()}</td><td class="${r.result==='Victory'?'w':'l'}">${esc(r.result||'')}</td><td>${esc(r.champion||'')}</td><td>${r.kills}/${r.deaths}/${r.assists}</td><td>${esc(String(r.cs_per_min??''))}</td><td>${esc(String(r.vision??''))}</td><td>${r.damage_share!=null?esc(String(r.damage_share))+'%':''}</td></tr>`).join('')}</tbody></table>`;
  } catch(e) {}
}

async function loadPool() {
  try {
    const rows = await (await fetch('/api/pool')).json();
    document.getElementById('pool-list').innerHTML = rows.length ? `<table class="mini-table"><thead><tr><th>Champion</th><th>Role</th><th>Notes</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.champion)}</td><td>${esc(r.role||'')}</td><td>${esc(r.notes||'')}</td><td><button class="btn-small" onclick="removePool('${escAttr(r.champion)}')">Remove</button></td></tr>`).join('')}</tbody></table>` : '<div class="muted">No champion pool yet. Add your comfort picks.</div>';
  } catch(e) {}
}
async function savePool() {
  const champion = document.getElementById('pool-champ').value.trim(); if (!champion) return;
  await fetch('/api/pool', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({champion, role: document.getElementById('pool-role').value.trim(), notes: document.getElementById('pool-notes').value.trim()})});
  document.getElementById('pool-champ').value=''; document.getElementById('pool-role').value=''; document.getElementById('pool-notes').value=''; loadPool();
}
async function removePool(champion) { await fetch('/api/pool?champion='+encodeURIComponent(champion), {method:'DELETE'}); loadPool(); }

async function loadNotes() {
  try {
    const rows = await (await fetch('/api/notes')).json();
    document.getElementById('notes-list').innerHTML = rows.length ? rows.map(n=>`<div class="note-item"><div class="note-meta">${esc(n.category)}${n.champion?` · ${esc(n.champion)}`:''} · ${new Date(n.created_at*1000).toLocaleString()} <button class="btn-small" onclick="deleteNote(${n.id})">Delete</button></div><div>${esc(n.content)}</div></div>`).join('') : '<div class="muted">No notes yet. Track goals, matchup learnings, and reminders.</div>';
  } catch(e) {}
}
async function saveNote() {
  const content = document.getElementById('note-content').value.trim(); if (!content) return;
  await fetch('/api/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content, category: document.getElementById('note-category').value, champion: document.getElementById('note-champ').value.trim()})});
  document.getElementById('note-content').value=''; document.getElementById('note-champ').value=''; loadNotes();
}
async function deleteNote(id) { await fetch('/api/notes?id='+encodeURIComponent(id), {method:'DELETE'}); loadNotes(); }

async function loadSettings() {
  try {
    const d = await (await fetch('/api/settings')).json();
    const r = d.runtime || {};
    document.getElementById('settings-view').innerHTML = `
      <div class="settings-grid">
        <div class="setting"><strong>AI provider</strong><div>${esc(r.ai_provider||'gemini')} ${r.ai_configured ? '· configured' : '· not configured'}</div></div>
        <div class="setting"><strong>AI model</strong><div>${esc(r.ai_model||r.recap_model||'')}</div></div>
        <div class="setting"><strong>Safe rune import</strong><div>${r.safe_rune_import ? 'Enabled' : 'Disabled'} (prefix: ${esc(r.rune_page_prefix||'LA:')})</div></div>
        <div class="setting"><strong>Data Dragon patch</strong><div>${esc(document.getElementById('patch-badge').textContent||'')}</div></div>
      </div>
      <p class="muted small">Configure in <code>.env</code>: <code>AI_PROVIDER</code> (gemini/openai/openrouter/ollama), <code>AI_API_KEY</code> (or <code>GEMINI_API_KEY</code>), <code>AI_MODEL</code>, <code>AI_BASE_URL</code> (for OpenAI-compatible/Ollama), <code>AI_TIMEOUT</code>. Legacy <code>GEMINI_API_KEY</code>/<code>RECAP_MODEL</code> still work.</p>`;
  } catch(e) {}
}

function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s) { return String(s ?? '').replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }
function renderPlayerIntel(rows, phase) {
  const panel = document.getElementById('intel-panel');
  const el = document.getElementById('player-intel');
  if (!panel || !el) return;
  const showPhases = new Set(['ChampSelect', 'GameStart', 'InProgress', 'Reconnect']);
  const useful = (rows || []).filter(r => r && (r.name || r.champion || r.summoner_id || r.puuid));
  if (!useful.length || !showPhases.has(phase)) { panel.classList.add('hidden'); return; }
  panel.classList.remove('hidden');
  const teams = { ally: [], enemy: [] };
  useful.forEach(r => { (teams[r.team === 'enemy' ? 'enemy' : 'ally'] || teams.ally).push(r); });
  const renderCard = (r) => {
    const intel = r.intel || {};
    const rank = intel.rank;
    const mastery = intel.mastery;
    const rankText = rank ? (rank.text || rank.tier || 'Unranked') : (intel.status === 'pending' ? 'Loading…' : intel.status === 'disconnected' ? 'Client disconnected' : 'Unavailable');
    const wr = rank && rank.winrate != null ? `${rank.winrate}% WR (${rank.wins}W/${rank.losses}L)` : (rank && rank.tier && rank.tier !== 'UNRANKED' ? 'WR n/a' : '');
    const mast = mastery ? `M${mastery.level || '?'} · ${fmtPoints(mastery.points)} on ${esc(r.champion || 'pick')}` : (r.champion ? `Mastery loading/unavailable` : '');
    const name = r.name || (r.is_me ? 'You' : (r.team === 'enemy' ? 'Enemy' : 'Ally'));
    return `<div class="intel-card ${r.team === 'enemy' ? 'enemy' : 'ally'}${r.is_me ? ' me' : ''}">
      <div class="intel-name">${esc(name)}${r.is_me ? ' <span class="muted">(You)</span>' : ''}</div>
      <div class="intel-champ">${esc(r.champion || 'No pick yet')}</div>
      <div class="intel-rank">${esc(rankText)}</div>
      <div class="intel-sub">${esc(wr)}</div>
      <div class="intel-sub">${mast ? esc(mast) : ''}</div>
      <div class="intel-status muted small">${intel.status && intel.status !== 'ok' ? esc(intel.status) : ''}</div>
    </div>`;
  };
  el.innerHTML = `
    <div><h3>ALLIES</h3><div class="intel-cards">${teams.ally.map(renderCard).join('') || '<div class="muted small">No data</div>'}</div></div>
    <div><h3>ENEMIES</h3><div class="intel-cards">${teams.enemy.map(renderCard).join('') || '<div class="muted small">Hidden/unavailable</div>'}</div></div>`;
}
function fmtPoints(n){ if(n==null) return ''; if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return Math.round(n/1e3)+'k'; return String(n); }


function draftParams() {
  const role = selectedRole;
  const allies = getInputValues('.ally-input');
  const enemies = getInputValues('.enemy-input');
  const p = new URLSearchParams(); p.set('role', role);
  allies.forEach(a => p.append('allies', a)); enemies.forEach(e => p.append('enemies', e));
  return { role, allies, enemies, qs: p.toString() };
}
function setDraftOutput(html) { const el = document.getElementById('draft-output'); if (el) el.innerHTML = html; }
async function runDraftAnalysis() {
  const { qs } = draftParams();
  setDraftOutput('Analyzing team comps...');
  try {
    const d = await (await fetch('/api/draft/analysis?' + qs)).json();
    const render = (c) => `<div><strong>${esc(c.label||'')}</strong>: ${esc((c.champs||[]).join(', ')||'none')}<br><span class="muted small">Damage (est): AD ${c.damage?.AD||0}, AP ${c.damage?.AP||0}, Mixed ${c.damage?.Mixed||0}, Utility ${c.damage?.Utility||0} · Frontline ${c.frontline||0} · Engage ${c.engage||0}</span>${(c.warnings||[]).map(w=>`<div class="warn">⚠ ${esc(w)}</div>`).join('')}${(c.notes||[]).map(n=>`<div class="note-ok">• ${esc(n)}</div>`).join('')}</div>`;
    setDraftOutput(`<div class="draft-grid">${render(d.enemy||{})}${render(d.ally||{})}</div>${(d.vs||[]).length?`<div style="margin-top:8px">${(d.vs||[]).map(n=>`<div class="note-ok">→ ${esc(n)}</div>`).join('')}</div>`:''}<div class="muted small" style="margin-top:6px">${esc(d.enemy?.disclaimer||'')}</div>`);
  } catch(e) { setDraftOutput('Failed to analyze team comp.'); }
}
async function runBanSuggestions() {
  const { qs } = draftParams();
  setDraftOutput('Loading ban suggestions...');
  try {
    const d = await (await fetch('/api/draft/bans?' + qs)).json();
    if (!d.length) { setDraftOutput('No ban suggestions (need role/pool context).'); return; }
    setDraftOutput(`<strong>Ban ideas</strong> (threats for your role/pool):<div class="draft-list">${d.map(b=>`<div class="draft-row"><strong>${esc(b.champion)}</strong> <span class="muted small">(${esc(b.tier||'?')})</span><div class="muted small">${esc((b.reasons||[]).join(' · '))}</div></div>`).join('')}</div>`);
  } catch(e) { setDraftOutput('Failed to load ban suggestions.'); }
}
async function runWhatShouldIPlay() {
  const { qs } = draftParams();
  setDraftOutput('Finding best owned picks vs locked enemies...');
  try {
    const d = await (await fetch('/api/draft/what-to-play?' + qs)).json();
    if (!d.length) { setDraftOutput('No picks found. Add enemies/role or connect client for ownership.'); return; }
    setDraftOutput(`<strong>What you should play</strong> (owned + good vs enemy comp + high WR):<div class="draft-list">${d.map((r,i)=>`<div class="draft-row clickable" onclick="lockChampion('${escAttr(r.champion)}')"><strong>${i+1}. ${esc(r.champion)}</strong> <span class="muted small">score ${Math.round(r.score||0)}</span><div class="muted small">${esc((r.reasons||[]).slice(0,4).join(' · '))}${r.note?` · ${esc(r.note)}`:''}</div></div>`).join('')}</div>`);
  } catch(e) { setDraftOutput('Failed to load picks.'); }
}
let draftAiPoll = null;
async function runDraftCoach() {
  const { role, allies, enemies } = draftParams();
  setDraftOutput('Starting AI draft coach...');
  try {
    await fetch('/api/draft/coach', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({role, allies, enemies})});
    pollDraftAi();
  } catch(e) { setDraftOutput('Failed to start AI draft coach.'); }
}
async function explainBuild() {
  const { role, allies, enemies } = draftParams();
  const build = selectedBuildOptions[selectedBuildOption || 0] || null;
  if (!lockedChamp || !build) { setDraftOutput('Lock a champion/build first, then click AI Build Explain.'); return; }
  setDraftOutput('Starting AI build explanation...');
  try {
    await fetch('/api/build-explain', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({champion: lockedChamp, role, allies, enemies, build})});
    pollDraftAi();
  } catch(e) { setDraftOutput('Failed to start build explanation.'); }
}
function pollDraftAi() {
  if (draftAiPoll) clearInterval(draftAiPoll);
  draftAiPoll = setInterval(async () => {
    try {
      const d = await (await fetch('/api/draft/ai')).json();
      if (d.status === 'analyzing') setDraftOutput(`<strong>AI</strong> <span class="muted small">${esc(d.model||'')}</span><div style="white-space:pre-wrap;margin-top:6px">${esc(d.text||'...')}${d.text?'▍':''}</div>`);
      else if (d.status === 'done') { clearInterval(draftAiPoll); draftAiPoll=null; setDraftOutput(`<strong>AI Draft/Build Advice</strong> <span class="muted small">${esc(d.model||'')}</span><div style="white-space:pre-wrap;margin-top:6px">${esc(d.text||'')}</div>`); }
      else if (d.status === 'error') { clearInterval(draftAiPoll); draftAiPoll=null; setDraftOutput(`<strong>AI error:</strong> ${esc(d.text||'Unknown error')}`); }
    } catch(e) {}
  }, 1000);
}

window.lockChampion = lockChampion; window.unlockChampion = unlockChampion; window.importRunes = importRunes; window.importSelectedRunes = importSelectedRunes; window.selectBuildOption = selectBuildOption; window.reanalyze = reanalyze; window.switchTab = switchTab; window.refreshCompanion = refreshCompanion; window.openSettings = openSettings; window.savePool = savePool; window.removePool = removePool; window.saveNote = saveNote; window.deleteNote = deleteNote; window.runDraftAnalysis=runDraftAnalysis; window.runBanSuggestions=runBanSuggestions; window.runWhatShouldIPlay=runWhatShouldIPlay; window.runDraftCoach=runDraftCoach; window.explainBuild=explainBuild;
