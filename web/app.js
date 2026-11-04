// MARÉE — Observatoire web (données réelles uniquement, via WebSocket).
// Le client est un consommateur : tout ce qui est à l'écran découle de l'instantané
// affiché. L'interpolation et les effets ne nourrissent aucun chiffre.

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const EXIT_PALETTE = {
  A: { fill: "#56b4e9", ink: "#0b5f91", shape: "circle", symbol: "●" },
  B: { fill: "#e69f00", ink: "#8a5300", shape: "square", symbol: "■" },
  C: { fill: "#cc79a7", ink: "#9a3d72", shape: "triangle", symbol: "▲" },
  none: { fill: "#a1a1aa", ink: "#52525b", shape: "diamond", symbol: "◆" },
};

const INTENTION_LABELS = {
  stay: "Reste sur place",
  go_exit: "Se dirige vers la sortie",
  go_zone: "Rejoint la zone",
  search: "Cherche un repère ou un proche",
  guide: "Guide les personnes autour vers la sortie",
  follow: "Suit",
};

const TRIGGER_LABELS = {
  premiere_decision: "première observation en arrivant sur place",
  periodique: "point régulier sur la situation",
  fumee_visible: "vient d'apercevoir la fumée",
  annonce: "vient d'entendre l'annonce officielle",
  sortie_fermee: "vient de constater qu'une sortie est fermée",
  proche_disparu: "ne voit plus son proche",
  message_recu: "vient d'être prévenu par quelqu'un",
};

const PERCEIVED_LABELS = {
  smoke: "Voit la fumée",
  announcement: "A entendu l'annonce",
  missing_kin: "Proche hors de vue",
};

const INDICATORS_META = [
  {
    key: "I1_consensus",
    code: "I1",
    name: "Accord sur la sortie",
    explain: "Part des personnes présentes qui visent la même sortie que la majorité.",
    format: (v) => (v == null ? "—" : `${Math.round(v * 100)} %`),
    formula: "max(A, B, C) / personnes présentes",
    window: "Tick courant",
    unit: "Proportion (0 à 1)",
    source: "Croyances des agents",
  },
  {
    key: "I2_entropy",
    name: "Hésitation moyenne",
    code: "I2",
    explain: "Mesure à quel point les personnes doutent entre plusieurs sorties (0 = certaines, 1 = très partagées).",
    format: (v) => (v == null ? "—" : v.toFixed(2).replace(".", ",")),
    formula: "Moyenne de −Σ p·log₂(p) normalisée",
    window: "Tick courant",
    unit: "Bits normalisés (0 à 1)",
    source: "Distributions de croyance",
  },
  {
    key: "I3_evacuated",
    code: "I3",
    name: "Part évacuée",
    explain: "Proportion des 60 personnes ayant franchi une sortie depuis le début.",
    format: (v) => (v == null ? "—" : `${Math.round(v * 100)} %`),
    formula: "Sorties cumulées / population initiale",
    window: "Cumulé depuis t0",
    unit: "Pourcentage",
    source: "Moteur physique JuPedSim",
  },
  {
    key: "I4_seconds",
    code: "I4",
    name: "Horloge depuis le début (t0)",
    explain: "Temps simulé écoulé depuis t0 (inclut la période calme avant le premier signal de danger).",
    format: (v) => (v == null ? "—" : `${Math.round(v)} s`),
    formula: "tick × 10 s",
    window: "Depuis t0",
    unit: "Secondes simulées",
    source: "Horloge du moteur",
  },
  {
    key: "I5_max_density",
    code: "I5",
    name: "Densité maximale",
    explain: "Concentration la plus forte observée autour d'une personne (rayon de 2 m).",
    format: (v) => (v == null ? "—" : `${v.toFixed(2).replace(".", ",")} /m²`),
    formula: "max(voisins à moins de 2 m / π·2²)",
    window: "Tick courant",
    unit: "Personnes / m²",
    source: "Positions JuPedSim",
  },
  {
    key: "I6_belief_gap",
    code: "I6",
    name: "Croyance erronée (sortie fermée)",
    explain: "Part des personnes présentes qui visent encore une sortie pourtant fermée.",
    format: (v) => (v == null ? "—" : `${Math.round(v * 100)} %`),
    formula: "Agents visant une sortie fermée / présents",
    window: "Tick courant",
    unit: "Proportion (0 à 1)",
    source: "État du monde + croyances",
  },
  {
    key: "I7_delay_seconds",
    code: "I7",
    name: "Temps depuis le premier danger",
    explain: "Secondes écoulées entre le premier signal de danger (fumée, annonce ou fermeture) et la dernière sortie.",
    format: (v) => (v == null ? "—" : `${Math.round(v)} s`),
    formula: "t(dernière sortie) − t(premier signal)",
    window: "Depuis le premier signal",
    unit: "Secondes simulées",
    source: "Journal du monde",
  },
];

const INDICATOR_SHORT = {
  I1_consensus: "Accord",
  I2_entropy: "Hésitation",
  I3_evacuated: "Évacués",
  I4_seconds: "Horloge",
  I5_max_density: "Densité",
  I6_belief_gap: "Écart",
  I7_delay_seconds: "Délai",
};

// Ces indicateurs n'ont plus de sens quand il n'y a plus personne sur place :
// le dernier tick vaut 0 par construction (voir AGENTS.md, « tick dégénéré »).
const UNDEFINED_WHEN_EMPTY = new Set(["I1_consensus", "I2_entropy", "I5_max_density", "I6_belief_gap"]);

const TICK_SECONDS = 10;
const FEED_LIMIT = 160;
const MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

const state = {
  conn: "offline", // offline | connecting | replay | live | ended
  live: false,
  held: false, // true : l'affichage ne suit plus le flux (figé ou déroulé manipulé)
  runId: null,
  plan: null,
  latest: null, // dernier instantané reçu
  snapshot: null, // instantané affiché
  snapshotsByTick: new Map(),
  indicatorsByTick: new Map(),
  indicators: {},
  selectedId: null,
  decisionsByAgent: new Map(),
  heardByAgent: new Map(),
  timelineSeries: [],
  worldMarkers: [],
  smokeEvent: null,
  smokeBorn: 0,
  announcement: null,
  firstDangerTick: null,
  endFrame: null,
  endDismissed: false,
  placingSmoke: false,
  placeAt: null,
  zoom: 1,
  pan: { x: 0, y: 0 },
  layers: { zones: true, smoke: true, density: true, messages: true, trail: true },
  socket: null,
  retryTimer: null,
  // Effets d'affichage : aucun n'alimente les chiffres.
  tween: { from: new Map(), start: 0, duration: 0 },
  snapInterval: 700,
  lastSnapAt: 0,
  ghosts: [],
  bursts: [],
  ripples: [],
  packets: [],
  flash: null,
  hoverId: null,
};

const canvas = $("#worldCanvas");
const ctx = canvas.getContext("2d");
const ground = document.createElement("canvas");
let groundKey = "";
let box = { width: 0, height: 0, dpr: 1 };
let view = { scale: 1, x: 0, y: 0 };
let loopHandle = null;
let lastPaint = 0;
let toastTimer = null;
let traceTimer = null;

/* ---------- Connexion ---------- */
function resetRunState() {
  state.latest = null;
  state.snapshot = null;
  state.held = false;
  state.selectedId = null;
  state.snapshotsByTick.clear();
  state.indicatorsByTick.clear();
  state.indicators = {};
  state.decisionsByAgent.clear();
  state.heardByAgent.clear();
  state.timelineSeries = [];
  state.worldMarkers = [];
  state.smokeEvent = null;
  state.announcement = null;
  state.firstDangerTick = null;
  state.endFrame = null;
  state.endDismissed = false;
  state.ghosts = [];
  state.bursts = [];
  state.ripples = [];
  state.packets = [];
  state.flash = null;
  state.tween = { from: new Map(), start: 0, duration: 0 };
  feedGroups.clear();
  $("#feed").replaceChildren();
  $("#feedEmpty").hidden = false;
  $("#feedCount").textContent = "";
  $("#announcementBanner").hidden = true;
  $("#endCard").hidden = true;
  $("#mapToast").hidden = true;
  $("#kpiEvacuated").textContent = "—";
  $("#kpiTotal").textContent = "";
  $("#kpiRemaining").textContent = "—";
  $("#kpiAlert").textContent = "—";
  $("#kpiProgress").querySelector("i").style.width = "0";
  $("#simClock").textContent = "—";
  $("#simTick").textContent = "temps simulé";
  syncHoldControls();
  renderPerson();
  renderIndicators();
  renderTimeline();
}

function wsEndpoint() {
  const params = new URLSearchParams(location.search);
  if (params.get("ws")) return params.get("ws");
  const host = location.hostname || "127.0.0.1";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${host}:8765`;
}

function connect() {
  clearTimeout(state.retryTimer);
  const previous = state.socket;
  state.socket = null; // ses événements `close` ne concernent plus la connexion courante
  if (previous && previous.readyState <= WebSocket.OPEN) {
    try { previous.close(); } catch { /* ignore */ }
  }
  const url = wsEndpoint();
  setConnectionState("connecting");

  let socket;
  try {
    socket = new WebSocket(url);
  } catch {
    setConnectionState("offline");
    scheduleRetry();
    return;
  }
  state.socket = socket;

  const timeout = setTimeout(() => {
    if (socket.readyState !== WebSocket.OPEN) {
      try { socket.close(); } catch { /* ignore */ }
    }
  }, 1800);

  socket.addEventListener("open", () => {
    clearTimeout(timeout);
    if (socket !== state.socket) return;
    resetRunState();
    setConnectionState("replay");
  });

  socket.addEventListener("message", (ev) => {
    if (socket !== state.socket) return;
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    handleFrame(msg);
  });

  socket.addEventListener("close", () => {
    clearTimeout(timeout);
    if (socket !== state.socket) return;
    if (state.conn !== "ended") {
      setConnectionState("offline");
      scheduleRetry();
    }
  });

  socket.addEventListener("error", () => clearTimeout(timeout));
}

function scheduleRetry() {
  clearTimeout(state.retryTimer);
  $("#retryLabel").textContent = "Nouvelle tentative automatique dans 4 secondes…";
  state.retryTimer = setTimeout(connect, 4000);
}

function setConnectionState(mode) {
  state.conn = mode;
  $("#statusPill").dataset.state = mode;
  const titles = {
    offline: "Hors ligne",
    connecting: "Connexion…",
    replay: "Rejeu d'un run enregistré",
    live: "Simulation en direct",
    ended: "Run terminé",
  };
  $("#statusLabel").textContent = titles[mode] || mode;

  const hasData = Boolean(state.snapshot);
  $("#mapEmpty").hidden = hasData;
  $("#pauseButton").disabled = mode !== "replay" && mode !== "live";
  $("#replayButton").hidden = mode !== "ended" && mode !== "replay";

  if (!hasData) {
    if (mode === "connecting") {
      $("#emptyTitle").textContent = "Connexion au moteur…";
      $("#emptyText").textContent = `Recherche d'une simulation sur ${wsEndpoint()}.`;
      $("#emptyCommands").hidden = true;
    } else if (mode === "offline") {
      $("#emptyTitle").textContent = "Aucune simulation connectée";
      $("#emptyText").textContent = "Cette interface n'invente aucune donnée. Démarrez le moteur à la racine du dépôt :";
      $("#emptyCommands").hidden = false;
    } else {
      $("#emptyTitle").textContent = "Moteur connecté";
      $("#emptyText").textContent = "En attente du premier instantané…";
      $("#emptyCommands").hidden = true;
    }
  }
  updateInterveneState();
}

/* ---------- Trames ---------- */
function handleFrame(msg) {
  switch (msg.type) {
    case "hello":
      state.runId = msg.run_id || null;
      state.plan = msg.plan || null;
      state.live = Boolean(msg.live);
      groundKey = "";
      if (state.plan?.smoke) state.smokeEvent = state.plan.smoke;
      $("#runTitle").textContent = state.runId
        ? `Port-Aubel · run « ${state.runId} »`
        : "Évacuation de l'esplanade de Port-Aubel";
      setConnectionState(state.live ? "live" : "replay");
      populateExitSelect();
      buildLegend();
      computeView();
      break;

    case "world":
      handleWorld(msg);
      break;

    case "decision": {
      const list = state.decisionsByAgent.get(msg.agent_id) || [];
      list.unshift(msg);
      state.decisionsByAgent.set(msg.agent_id, list.slice(0, 60));
      const intent = msg.intention?.kind;
      if (msg.trigger && msg.trigger !== "periodique" && msg.trigger !== "premiere_decision") {
        const target = msg.intention?.target ? ` ${msg.intention.target}` : "";
        pushGrouped(msg.tick, "decision", "Décisions", `${INTENTION_LABELS[intent] || intent || "Agit"}${target}`, msg.agent_id);
      }
      break;
    }

    case "message":
      if ((msg.tick ?? 0) < 0) break; // préhistoire : un souvenir, pas un présent
      if (!state.held) {
        const created = performance.now();
        state.ripples.push({ from: msg.from, created });
        for (const to of msg.to || []) state.packets.push({ from: msg.from, to, created });
        wake();
      }
      pushGrouped(msg.tick, "talk", "Paroles", `« ${msg.content} »`, msg.from);
      break;

    case "heard": {
      const list = state.heardByAgent.get(msg.agent_id) || [];
      list.unshift(msg);
      state.heardByAgent.set(msg.agent_id, list.slice(0, 40));
      break;
    }

    case "incident":
      pushFeed(msg.tick, "danger", "Incident", `${msg.agent_id} : repli sur les règles (${msg.cause ?? msg.kind ?? "cause inconnue"}).`, msg.agent_id);
      break;

    case "narrative":
      if (msg.text) pushFeed(msg.tick, "world", "Récit", msg.text);
      break;

    case "injection":
      pushFeed(msg.tick, "world", "Intervention", `Action injectée dans le monde : ${msg.kind ?? "?"}.`);
      break;

    case "snapshot":
      ingestSnapshot(msg);
      break;

    case "indicators":
      if (msg.tick != null) state.indicatorsByTick.set(msg.tick, msg);
      if (!state.held) {
        state.indicators = msg;
        renderIndicators();
      }
      break;

    case "trace":
      renderTrace(msg);
      break;

    case "ack":
      setFeedback(`Action enregistrée (${msg.kind}). Elle sera appliquée au prochain tick.`, "ok");
      break;

    case "error":
      setFeedback(msg.reason || "Action refusée par le moteur.", "error");
      break;

    case "end":
      state.endFrame = msg;
      setConnectionState("ended");
      pushFeed(msg.tick, "end", "Fin", `Run terminé : ${msg.evacuated ?? "—"} personnes sorties sur ${msg.total ?? "—"}, en ${msg.ticks ?? "—"} ticks.`);
      syncHoldControls();
      renderEndCard();
      applyFeedFilter();
      break;
  }
}

function handleWorld(msg) {
  const tick = msg.tick ?? 0;
  if (state.firstDangerTick == null) state.firstDangerTick = tick;
  if (msg.kind === "smoke") {
    state.smokeEvent = { position: msg.position, radius: msg.radius, tick };
    state.smokeBorn = performance.now();
    state.worldMarkers.push({ tick, kind: "smoke", label: "Fumée" });
    const zone = zoneNameAt(msg.position);
    const where = zone ? `De la fumée apparaît : ${zone}` : "De la fumée apparaît";
    pushFeed(tick, "danger", "Alerte", `${where}.`);
    announcePolite(`Alerte : ${where}.`);
    alertMap(where, "danger");
  } else if (msg.kind === "announcement") {
    state.announcement = { text: msg.text, tick };
    state.worldMarkers.push({ tick, kind: "announcement", label: "Annonce" });
    pushFeed(tick, "world", "Annonce", `Haut-parleurs : « ${msg.text} »`);
    announcePolite(`Annonce officielle : ${msg.text}`);
    alertMap("Annonce diffusée par les haut-parleurs", "world");
  } else if (msg.kind === "exit_closed") {
    state.worldMarkers.push({ tick, kind: "exit_closed", label: `Sortie ${msg.exit} fermée` });
    pushFeed(tick, "danger", "Sortie fermée", `La sortie ${msg.exit} vient de fermer.`);
    announcePolite(`La sortie ${msg.exit} vient de fermer.`);
    alertMap(`La sortie ${msg.exit} vient de fermer`, "danger");
  }
  renderTimeline();
}

function alertMap(text, kind) {
  if (state.held) return;
  const toast = $("#mapToast");
  toast.textContent = text;
  toast.dataset.kind = kind;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 4200);
  state.flash = { start: performance.now(), rgb: kind === "danger" ? "239, 68, 68" : "230, 159, 0" };
  wake();
}

function ingestSnapshot(msg) {
  const now = performance.now();
  if (state.lastSnapAt) state.snapInterval = clamp(now - state.lastSnapAt, 120, 900);
  state.lastSnapAt = now;
  state.latest = msg;
  if (msg.tick != null) state.snapshotsByTick.set(msg.tick, msg);
  recordTimelinePoint(msg);
  $("#mapEmpty").hidden = true;
  if (state.held) {
    syncHoldControls();
    renderTimeline();
    return;
  }
  show(msg, true);
}

/** Affiche un instantané ; tout ce qui est à l'écran en découle. */
function show(snap, animate) {
  const previous = state.snapshot;
  const now = performance.now();
  const motion = animate && !MOTION.matches;
  const from = new Map();
  if (previous) {
    for (const a of previous.agents || []) {
      if (a.evacuated || !a.pos) continue;
      from.set(a.id, displayPos(a, now));
    }
  }
  if (motion && previous) {
    for (const a of snap.agents || []) {
      const start = from.get(a.id);
      if (a.evacuated && start) {
        const gate = exitPointFor(a, start);
        state.ghosts.push({ id: a.id, belief: a.belief, from: start, to: gate.point, exit: gate.id, start: now, duration: state.snapInterval });
      }
    }
  }
  state.tween = { from, start: now, duration: motion ? state.snapInterval : 0 };
  state.snapshot = snap;
  if (state.indicatorsByTick.has(snap.tick)) state.indicators = state.indicatorsByTick.get(snap.tick);
  renderAll();
  wake();
}

function displayedTick() { return state.snapshot?.tick ?? 0; }

/* ---------- Geler / suivre ---------- */
function hold() {
  state.held = true;
  $("#mapToast").hidden = true;
  syncHoldControls();
  applyFeedFilter();
}

function follow() {
  state.held = false;
  syncHoldControls();
  if (state.latest) show(state.latest, false);
  applyFeedFilter();
}

function syncHoldControls() {
  const frozen = state.held;
  const running = state.conn === "replay" || state.conn === "live";
  $("#pauseButton").setAttribute("aria-pressed", String(frozen && running));
  $("#pauseLabel").textContent = frozen && running ? "Reprendre" : "Figer";
  $("#pauseIconPath").setAttribute("d", frozen && running ? "m8 5 11 7-11 7z" : "M8 5v14M16 5v14");
  const behind = frozen && state.latest && state.snapshot && state.latest.tick !== state.snapshot.tick;
  const btn = $("#followButton");
  btn.hidden = !behind;
  btn.textContent = state.conn === "ended" ? "Revenir à la fin" : "Revenir au présent";
}

function scrubTo(tick) {
  let bestTick = null;
  let bestDiff = Infinity;
  for (const k of state.snapshotsByTick.keys()) {
    const d = Math.abs(k - tick);
    if (d < bestDiff) { bestDiff = d; bestTick = k; }
  }
  if (bestTick == null || bestTick === state.snapshot?.tick) return;
  state.held = bestTick !== state.latest?.tick || state.conn !== "ended";
  if (state.held) $("#mapToast").hidden = true;
  show(state.snapshotsByTick.get(bestTick), false);
  syncHoldControls();
  applyFeedFilter();
}

function recordTimelinePoint(snap) {
  const total = snap.agents?.length ?? 0;
  const evacuated = (snap.agents || []).filter((a) => a.evacuated).length;
  const tick = snap.tick ?? 0;
  const existing = state.timelineSeries.findIndex((p) => p.tick === tick);
  const point = { tick, evacuated, total };
  if (existing >= 0) state.timelineSeries[existing] = point;
  else state.timelineSeries.push(point);
}

/* ---------- Rendu DOM ---------- */
function setText(el, text) {
  if (el.textContent === text) return;
  el.textContent = text;
  if (MOTION.matches) return;
  el.classList.remove("bump");
  void el.offsetWidth; // relance l'animation
  el.classList.add("bump");
}

function renderAll() {
  renderClock();
  renderKpis();
  renderLegend();
  renderBanner();
  renderPerson();
  renderIndicators();
  renderTimeline();
  renderEndCard();
  applyFeedFilter();
  if ($("#findDialog").open) renderFindList($("#findInput").value);
}

function renderClock() {
  const snap = state.snapshot;
  if (!snap) return;
  const seconds = (snap.tick ?? 0) * TICK_SECONDS;
  const secs = String(seconds % 60).padStart(2, "0");
  $("#simClock").textContent = snap.sim_time || `${Math.floor(seconds / 60)}:${secs}`;
  $("#simTick").textContent = `tick ${snap.tick ?? 0}`;
}

function renderKpis() {
  const snap = state.snapshot;
  if (!snap) return;
  const total = snap.agents?.length ?? 0;
  const evacuated = (snap.agents || []).filter((a) => a.evacuated).length;
  const pct = total ? Math.round((evacuated / total) * 100) : 0;

  setText($("#kpiEvacuated"), String(evacuated));
  $("#kpiTotal").textContent = `/ ${total}`;
  setText($("#kpiRemaining"), String(total - evacuated));
  const bar = $("#kpiProgress");
  bar.setAttribute("aria-valuenow", String(pct));
  bar.querySelector("i").style.width = `${pct}%`;

  const first = state.firstDangerTick;
  const alert = first != null && snap.tick != null && snap.tick >= first
    ? `${(snap.tick - first) * TICK_SECONDS} s`
    : "Calme";
  setText($("#kpiAlert"), alert);
}

function buildLegend() {
  const container = $("#exitLegend");
  container.replaceChildren();
  if (!state.plan) return;
  const items = [
    ...(state.plan.exits || []).map((ex) => ({ id: ex.id, title: `Sortie ${ex.id}`, sub: ex.label || "" })),
    { id: "none", title: "Sans sortie", sub: "Hésite ou observe" },
  ];
  for (const item of items) {
    const li = document.createElement("li");
    li.dataset.exit = item.id;
    li.style.setProperty("--tint", (EXIT_PALETTE[item.id] || EXIT_PALETTE.none).fill);

    const shape = document.createElement("span");
    shape.className = `shape shape-${item.id}`;
    shape.setAttribute("aria-hidden", "true");

    const name = document.createElement("div");
    name.className = "legend-name";
    const strong = document.createElement("strong");
    strong.textContent = item.title;
    const sub = document.createElement("span");
    sub.textContent = item.sub;
    sub.dataset.base = item.sub;
    name.append(strong, sub);

    const count = document.createElement("span");
    count.className = "legend-count";
    count.title = "Personnes encore sur l'esplanade visant cette option";
    count.textContent = "—";

    const share = document.createElement("i");
    share.setAttribute("aria-hidden", "true");
    li.append(shape, name, count, share);
    container.append(li);
  }
}

function renderLegend() {
  if (!state.plan) return;
  const active = (state.snapshot?.agents || []).filter((a) => !a.evacuated);
  const counts = {};
  for (const a of active) {
    const key = a.belief && EXIT_PALETTE[a.belief] ? a.belief : "none";
    counts[key] = (counts[key] || 0) + 1;
  }
  for (const li of $("#exitLegend").children) {
    const id = li.dataset.exit;
    const open = id === "none" || isExitOpen(id);
    const n = counts[id] || 0;
    li.dataset.closed = String(!open);
    li.style.setProperty("--share", `${active.length ? (n / active.length) * 100 : 0}%`);
    const sub = li.querySelector(".legend-name span");
    sub.textContent = open ? sub.dataset.base : "FERMÉE";
    sub.classList.toggle("legend-closed", !open);
    setText(li.querySelector(".legend-count"), state.snapshot ? String(n) : "—");
  }
}

function renderBanner() {
  const snap = state.snapshot;
  const known = state.announcement && state.announcement.tick <= (snap?.tick ?? 0) ? state.announcement.text : null;
  const text = snap?.announcement || known;
  const banner = $("#announcementBanner");
  if (text && $("#announcementText").textContent !== text) $("#announcementText").textContent = text;
  banner.hidden = !text;
}

function renderEndCard() {
  const card = $("#endCard");
  const end = state.endFrame;
  const atEnd = end && !state.held && !state.endDismissed && !state.selectedId;
  card.hidden = !atEnd;
  if (!atEnd) return;
  $("#mapToast").hidden = true;
  const agents = state.snapshot?.agents || [];
  const total = end.total ?? agents.length;
  const evacuated = end.evacuated ?? agents.filter((a) => a.evacuated).length;
  const trapped = total - evacuated;
  $("#endEvacuated").textContent = String(evacuated);
  $("#endTotal").textContent = `/ ${total}`;
  const duration = (end.ticks ?? state.snapshot?.tick ?? 0) * TICK_SECONDS;
  $("#endEyebrow").textContent = trapped ? "Run terminé · foule piégée" : "Évacuation terminée";
  $("#endText").textContent = trapped
    ? `${trapped} personne${trapped > 1 ? "s" : ""} encore sur place après ${duration} s simulées.`
    : `Tout le monde est sorti en ${duration} s simulées.`;

  const byBelief = new Map();
  for (const a of agents) {
    if (!a.evacuated) continue;
    const key = a.belief && EXIT_PALETTE[a.belief] ? a.belief : "none";
    byBelief.set(key, (byBelief.get(key) || 0) + 1);
  }
  const list = $("#endExits");
  list.replaceChildren();
  for (const ex of state.plan?.exits || []) {
    const li = document.createElement("li");
    const shape = document.createElement("span");
    shape.className = `shape shape-${ex.id}`;
    shape.setAttribute("aria-hidden", "true");
    li.append(shape, document.createTextNode(`${byBelief.get(ex.id) || 0} visaient ${ex.id}`));
    list.append(li);
  }
}

function asOf(list) {
  const tick = displayedTick();
  return (list || []).filter((item) => (item.tick ?? 0) <= tick);
}

function renderPerson() {
  const agent = (state.snapshot?.agents || []).find((a) => a.id === state.selectedId) || null;
  $("#feedPanel").hidden = Boolean(agent);
  $("#personPanel").hidden = !agent;
  if (!agent) return;

  const beliefKey = agent.belief && EXIT_PALETTE[agent.belief] ? agent.belief : "none";
  $("#personShape").className = `person-shape shape shape-${beliefKey}`;

  $("#personId").textContent = `${agent.id} · ${agent.label || agent.profile || "Personne"}`;
  const modeLabel = agent.kind === "llm" ? "Décide avec un modèle de langage (LLM)" : "Décide selon des règles simples";
  const zone = zoneNameAt(agent.pos);
  $("#personRole").textContent = `${modeLabel}${zone && !agent.evacuated ? ` · ${zone}` : ""}${agent.kin ? ` · Proche de ${agent.kin}` : ""}`;

  const exitLabel = exitLabelFor(agent.belief);
  const sure = Math.round((agent.confidence ?? 0) * 100);
  let headline;
  if (agent.evacuated) {
    headline = "Est sortie de l'esplanade.";
  } else if (agent.intention === "go_exit" && (agent.intention_target || agent.belief)) {
    const target = agent.intention_target || agent.belief;
    headline = `Se dirige vers la sortie ${target}${exitLabelFor(target) ? ` (${exitLabelFor(target)})` : ""} — sûre à ${sure} %.`;
  } else if (agent.intention === "guide" && (agent.intention_target || agent.belief)) {
    const target = agent.intention_target || agent.belief;
    headline = `Oriente la foule vers la sortie ${target}${exitLabelFor(target) ? ` (${exitLabelFor(target)})` : ""}.`;
  } else {
    const base = INTENTION_LABELS[agent.intention] || agent.intention || "Observe";
    headline = `${base}${agent.intention_target ? ` (${agent.intention_target})` : ""}${exitLabel ? ` · pense que la sortie ${agent.belief} est la meilleure (${sure} %)` : ""}.`;
  }
  $("#personHeadline").textContent = headline;

  // Dernière décision à l'instant affiché : le flux, sinon l'instantané.
  const decisions = asOf(state.decisionsByAgent.get(agent.id));
  const latest = decisions[0] || agent.last_decision || null;
  $("#personReason").textContent = latest?.reason || "Pas encore d'explication enregistrée à ce moment du run.";
  if (latest) {
    const trig = TRIGGER_LABELS[latest.trigger] || latest.trigger || "décision";
    const llmInfo = latest.llm?.model ? ` · modèle ${latest.llm.model}` : "";
    const rule = latest.rule && latest.rule !== latest.reason ? ` · règle : ${latest.rule}` : "";
    $("#personTrigger").textContent = `À t${latest.tick} (${trig}${llmInfo})${rule}.`;
  } else {
    $("#personTrigger").textContent = agent.decided_at != null ? `Dernière réflexion au tick t${agent.decided_at}.` : "";
  }

  renderBeliefs(agent);

  const perceivedWrap = $("#personPerceived");
  perceivedWrap.replaceChildren();
  const signals = agent.perceived || [];
  if (!signals.length) {
    perceivedWrap.append(listItem("Aucun signal de danger perçu pour l'instant", "empty"));
  } else {
    for (const sig of signals) perceivedWrap.append(listItem(formatPerceived(sig)));
  }

  const heardWrap = $("#personHeard");
  heardWrap.replaceChildren();
  const heard = asOf(state.heardByAgent.get(agent.id));
  if (!heard.length) {
    heardWrap.append(listItem("Personne ne lui a encore parlé.", "empty"));
  } else {
    for (const h of heard.slice(0, 5)) {
      heardWrap.append(rowItem(`${formatWhen(h.tick)} · de ${h.from}`, `« ${h.content} »`));
    }
  }

  const memoryWrap = $("#personMemory");
  memoryWrap.replaceChildren();
  const memory = agent.memory || [];
  if (!memory.length) {
    memoryWrap.append(listItem("Aucun souvenir enregistré à cet instant.", "empty"));
  } else {
    for (const m of memory) {
      memoryWrap.append(rowItem(`${formatWhen(m.tick)} · ${m.kind ?? "souvenir"}`, m.content ?? ""));
    }
  }

  const histWrap = $("#personHistory");
  histWrap.replaceChildren();
  if (!decisions.length) {
    histWrap.append(listItem("Aucune décision reçue à cet instant.", "empty"));
  } else {
    for (const d of decisions.slice(0, 12)) {
      const kind = d.intention?.kind;
      const target = d.intention?.target ? ` → ${d.intention.target}` : "";
      const li = rowItem(`t${d.tick} · ${TRIGGER_LABELS[d.trigger] || d.trigger || ""}`, d.reason || "");
      const strong = document.createElement("strong");
      strong.textContent = `${INTENTION_LABELS[kind] || kind || ""}${target}`;
      li.insertBefore(strong, li.lastChild);
      histWrap.append(li);
    }
  }

  const docsWrap = $("#personDocs");
  docsWrap.replaceChildren();
  const retrieved = latest?.retrieved || [];
  if (!retrieved.length) {
    docsWrap.append(listItem(
      agent.kind === "llm"
        ? "Aucun extrait documentaire mobilisé sur la dernière décision."
        : "Cette personne suit des règles simples et n'interroge pas le corpus documentaire.",
      "empty",
    ));
  } else {
    for (const doc of retrieved) {
      const score = doc.score != null ? ` · score ${doc.score.toFixed(2).replace(".", ",")}` : "";
      docsWrap.append(rowItem(`${doc.doc_id || doc.id || "Document"}${score}`, doc.text || doc.content || ""));
    }
  }
}

function renderBeliefs(agent) {
  const wrap = $("#personBeliefs");
  const exits = state.plan?.exits || [{ id: "A" }, { id: "B" }, { id: "C" }];
  if (wrap.dataset.agent !== agent.id || wrap.children.length !== exits.length) {
    wrap.dataset.agent = agent.id;
    wrap.replaceChildren();
    for (const ex of exits) {
      const row = document.createElement("div");
      row.className = "belief-row";
      row.dataset.exit = ex.id;
      const icon = document.createElement("span");
      icon.className = `shape shape-${ex.id}`;
      icon.setAttribute("aria-hidden", "true");
      const bar = document.createElement("div");
      bar.className = "bar";
      const fill = document.createElement("i");
      fill.style.background = EXIT_PALETTE[ex.id]?.fill || "#a1a1aa";
      bar.append(fill);
      row.append(icon, bar, document.createElement("strong"), document.createElement("small"));
      wrap.append(row);
    }
  }
  for (const ex of exits) {
    const row = wrap.querySelector(`[data-exit="${ex.id}"]`);
    const entry = agent.beliefs?.[ex.id];
    const conf = entry?.confidence ?? (agent.belief === ex.id ? agent.confidence ?? 0 : 0);
    const pct = Math.round(clamp(conf, 0, 1) * 100);
    row.querySelector("i").style.width = `${pct}%`;
    row.querySelector("strong").textContent = `${pct} %`;
    row.querySelector("small").textContent = `Sortie ${ex.id}${ex.label ? ` (${ex.label})` : ""}${entry?.source ? ` · ${formatBeliefSource(entry.source)}` : " · non connue ou écartée"}`;
  }
}

function listItem(text, className = "") {
  const li = document.createElement("li");
  if (className) li.className = className;
  li.textContent = text;
  return li;
}

function rowItem(when, text) {
  const li = document.createElement("li");
  const head = document.createElement("span");
  head.className = "when";
  head.textContent = when;
  const body = document.createElement("span");
  body.textContent = text;
  li.append(head, body);
  return li;
}

/* ---------- Indicateurs ---------- */
function buildIndicators() {
  const list = $("#indicatorList");
  for (const meta of INDICATORS_META) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.title = meta.explain;
    btn.setAttribute("aria-label", `${meta.code} ${meta.name} : ouvrir sa définition et sa trace`);
    btn.dataset.key = meta.key;

    const spark = svgEl("svg", { class: "ind-spark", viewBox: "0 0 100 26", preserveAspectRatio: "none", "aria-hidden": "true" });
    spark.append(svgEl("path", { d: "" }));
    const name = document.createElement("span");
    name.className = "ind-name";
    const code = document.createElement("b");
    code.textContent = meta.code;
    name.append(code, INDICATOR_SHORT[meta.key]);
    const value = document.createElement("span");
    value.className = "ind-value";
    value.textContent = "—";

    btn.append(spark, name, value);
    btn.addEventListener("click", () => openTrace(meta.key));
    li.append(btn);
    list.append(li);
  }
  const li = document.createElement("li");
  const help = document.createElement("button");
  help.type = "button";
  help.className = "ind-help";
  help.textContent = "Comment les lire ?";
  help.addEventListener("click", () => $("#helpDialog").showModal());
  li.append(help);
  list.append(li);
}

function renderIndicators() {
  const crowdGone = Boolean(state.snapshot) && (state.snapshot.agents || []).every((a) => a.evacuated);
  const tick = displayedTick();
  const ticks = [...state.indicatorsByTick.keys()].filter((t) => t <= tick).sort((a, b) => a - b);
  for (const meta of INDICATORS_META) {
    const btn = $(`#indicatorList [data-key="${meta.key}"]`);
    const undefinedNow = crowdGone && UNDEFINED_WHEN_EMPTY.has(meta.key);
    setText(btn.querySelector(".ind-value"), undefinedNow ? "—" : meta.format(state.indicators?.[meta.key]));
    btn.title = undefinedNow ? "Non défini : plus personne sur place." : meta.explain;

    const values = ticks
      .filter((t) => !(UNDEFINED_WHEN_EMPTY.has(meta.key) && state.indicatorsByTick.get(t)?.counts?.remaining === 0))
      .map((t) => state.indicatorsByTick.get(t)?.[meta.key])
      .filter((v) => v != null);
    btn.querySelector(".ind-spark path").setAttribute("d", sparkPath(values));
  }
}

function sparkPath(values) {
  if (values.length < 2) return "";
  const max = Math.max(...values, 1e-6);
  const step = 100 / (values.length - 1);
  return values.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)} ${(24 - (v / max) * 21).toFixed(1)}`).join("");
}

function openTrace(key) {
  const meta = INDICATORS_META.find((m) => m.key === key) || INDICATORS_META[0];
  $("#traceTitle").textContent = `${meta.code} · ${meta.name}`;
  $("#traceDefinition").textContent = meta.explain;
  const method = $("#traceMethod");
  method.replaceChildren();
  for (const [term, value] of [["Formule", meta.formula], ["Fenêtre", meta.window], ["Unité", meta.unit], ["Source", meta.source]]) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    row.append(dt, dd);
    method.append(row);
  }
  const body = $("#traceBody");
  body.textContent = "Interrogation du journal auprès du serveur…";
  $("#traceDialog").showModal();
  clearTimeout(traceTimer);
  traceTimer = setTimeout(() => {
    body.textContent = "Le serveur n'a pas répondu. La diffusion est peut-être arrêtée : relancez « uv run maree serve » puis réessayez.";
  }, 8000);

  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify({ type: "trace", indicator: key }));
    return;
  }
  // Run terminé : le serveur a fermé la socket de diffusion, on en rouvre une
  // uniquement pour poser la question au journal.
  try {
    const helper = new WebSocket(wsEndpoint());
    helper.addEventListener("open", () => helper.send(JSON.stringify({ type: "trace", indicator: key })));
    helper.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "trace") {
          renderTrace(msg);
          helper.close();
        }
      } catch { /* ignore */ }
    });
    helper.addEventListener("error", () => {
      body.textContent = "Serveur déconnecté : impossible d'interroger le journal.";
    });
  } catch {
    body.textContent = "Serveur déconnecté : impossible d'interroger le journal.";
  }
}

function renderTrace(trace) {
  clearTimeout(traceTimer);
  const body = $("#traceBody");
  body.replaceChildren();
  if (!trace.found) {
    const p = document.createElement("p");
    p.className = "meta";
    p.textContent = trace.reason || "Aucune variation significative enregistrée sur cet indicateur.";
    body.append(p);
    return;
  }
  const summary = document.createElement("p");
  summary.className = "trace-summary";
  const delta = trace.delta >= 0 ? `+${trace.delta}` : String(trace.delta);
  summary.textContent = `Plus forte variation au tick t${trace.tick} : la valeur passe de ${trace.from} à ${trace.to} (${delta}). Voici les événements enregistrés dans les ${trace.lookback ?? 5} ticks précédents :`;
  body.append(summary);

  const ol = document.createElement("ol");
  ol.className = "trace-steps";
  for (const ev of trace.events || []) {
    const li = document.createElement("li");
    const when = document.createElement("span");
    when.className = "when";
    when.textContent = `t${ev.tick} #${ev.seq}`;
    const text = document.createElement("span");
    text.textContent = ev.label || ev.type || "";
    li.append(when, text);
    ol.append(li);
  }
  body.append(ol);
}

/* ---------- Déroulé ---------- */
const TL = { padL: 30, padR: 12, padT: 22, padB: 20 };
let tlScale = { maxTick: 20, plotW: 100 };

function renderTimeline() {
  const svg = $("#timelineSvg");
  const host = $("#timeline");
  const series = [...state.timelineSeries].sort((a, b) => a.tick - b.tick);
  const width = svg.clientWidth || 680;
  const height = svg.clientHeight || 118;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.replaceChildren();

  if (!series.length) {
    $("#timelineDesc").textContent = "Aucune donnée de chronologie pour l'instant.";
    $("#timelineSub").textContent = "Personnes sorties au fil du temps.";
    host.setAttribute("aria-valuemax", "0");
    host.setAttribute("aria-valuenow", "0");
    host.setAttribute("aria-valuetext", "Aucune donnée");
    return;
  }

  const { padL, padR, padT, padB } = TL;
  const plotW = Math.max(100, width - padL - padR);
  const plotH = height - padT - padB;
  const maxTick = Math.max(20, ...series.map((p) => p.tick), ...state.worldMarkers.map((m) => m.tick));
  tlScale = { maxTick, plotW };
  const total = series[0]?.total || 60;
  const xOf = (t) => padL + (t / maxTick) * plotW;
  const yOf = (v) => padT + plotH - (v / total) * plotH;
  const nowTick = displayedTick();

  const defs = svgEl("defs");
  const grad = svgEl("linearGradient", { id: "tlFill", x1: 0, y1: 0, x2: 0, y2: 1 });
  grad.append(
    svgEl("stop", { offset: "0%", "stop-color": "#818cf8", "stop-opacity": ".42" }),
    svgEl("stop", { offset: "100%", "stop-color": "#818cf8", "stop-opacity": "0" }),
  );
  defs.append(grad);
  svg.append(defs);

  for (const val of [0, total]) {
    const y = yOf(val);
    const label = svgEl("text", { x: padL - 6, y: y + 4, "text-anchor": "end" });
    label.textContent = String(val);
    svg.append(svgEl("line", { x1: padL, y1: y, x2: padL + plotW, y2: y, class: val === 0 ? "axis" : "grid" }), label);
  }

  const step = maxTick <= 25 ? 5 : maxTick <= 60 ? 10 : maxTick <= 120 ? 20 : 50;
  for (let t = 0; t <= maxTick; t += step) {
    const label = svgEl("text", { x: xOf(t), y: height - 4, "text-anchor": "middle" });
    label.textContent = `t${t}`;
    svg.append(label);
  }

  const toPoints = (list) => list.map((p) => `${xOf(p.tick).toFixed(1)},${yOf(p.evacuated).toFixed(1)}`).join(" ");
  const past = series.filter((p) => p.tick <= nowTick);
  const ahead = series.filter((p) => p.tick >= nowTick);
  if (past.length) {
    const baseY = yOf(0).toFixed(1);
    const firstX = xOf(past[0].tick).toFixed(1);
    const lastX = xOf(past[past.length - 1].tick).toFixed(1);
    svg.append(svgEl("polygon", { points: `${firstX},${baseY} ${toPoints(past)} ${lastX},${baseY}`, fill: "url(#tlFill)", stroke: "none" }));
  }
  if (ahead.length > 1) svg.append(svgEl("polyline", { points: toPoints(ahead), class: "future" }));
  if (past.length > 1) svg.append(svgEl("polyline", { points: toPoints(past), class: "curve" }));

  const rowEnds = [-Infinity, -Infinity];
  const byTick = new Map();
  for (const m of state.worldMarkers) {
    const same = byTick.get(m.tick);
    if (same) same.label = `${same.label} + ${m.label}`;
    else byTick.set(m.tick, { ...m });
  }
  for (const m of [...byTick.values()].sort((a, b) => a.tick - b.tick)) {
    const x = xOf(m.tick);
    const g = svgEl("g", { class: `marker ${m.kind}` });
    g.append(svgEl("line", { x1: x, y1: padT - 4, x2: x, y2: padT + plotH }));
    const text = `${m.label} · t${m.tick}`;
    const estimate = text.length * 6.6;
    const row = x >= rowEnds[0] ? 0 : 1;
    const flip = x + estimate > padL + plotW;
    const label = svgEl("text", { x: flip ? x - 4 : x + 4, y: 10 + row * 13, "text-anchor": flip ? "end" : "start" });
    label.textContent = text;
    rowEnds[row] = x + estimate + 8;
    g.append(label);
    svg.append(g);
  }

  const point = series.find((p) => p.tick === nowTick) || series[series.length - 1];
  const cx = xOf(nowTick);
  svg.append(
    svgEl("line", { x1: cx, y1: padT - 4, x2: cx, y2: padT + plotH, class: "now" }),
    svgEl("circle", { cx, cy: yOf(point.evacuated), r: 4.5, class: "now-dot" }),
  );

  host.setAttribute("aria-valuemax", String(series[series.length - 1].tick));
  host.setAttribute("aria-valuenow", String(nowTick));
  host.setAttribute("aria-valuetext", `Tick ${nowTick}, ${point.evacuated} personnes sorties sur ${total}`);
  $("#timelineSub").textContent = state.held
    ? `Vous revoyez t${nowTick} : ${point.evacuated} sorties sur ${total}.`
    : "Faites glisser pour revoir un instant.";
  $("#timelineDesc").textContent = `Au tick t${point.tick}, ${point.evacuated} personnes sur ${total} sont sorties.`;
}

function timelineTickAt(clientX) {
  const rect = $("#timeline").getBoundingClientRect();
  const ratio = clamp((clientX - rect.left - TL.padL) / tlScale.plotW, 0, 1);
  return Math.round(ratio * tlScale.maxTick);
}

function showTimelineTip(clientX) {
  const tip = $("#timelineTip");
  const tick = timelineTickAt(clientX);
  const point = state.timelineSeries.find((p) => p.tick === tick);
  if (!point) { tip.hidden = true; return; }
  const seconds = tick * TICK_SECONDS;
  tip.textContent = `t${tick} · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} · ${point.evacuated} sorties`;
  const rect = $("#timeline").getBoundingClientRect();
  tip.style.left = `${clamp(clientX - rect.left, 70, rect.width - 70)}px`;
  tip.hidden = false;
}

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

/* ---------- Carte : repère ---------- */
function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  box = { width: rect.width, height: rect.height, dpr };
  computeView();
  paint();
  renderTimeline();
}

function planBounds() {
  const pts = state.plan.walkable || [[0, 0], [state.plan.width, 0], [state.plan.width, state.plan.height], [0, state.plan.height]];
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function computeView() {
  if (!box.width || !state.plan) return;
  const b = planBounds();
  const compact = box.width < 640;
  const padX = compact ? 16 : 92;
  const padTop = compact ? 58 : 66;
  const padBottom = compact ? 58 : 60;
  const fit = Math.min(
    (box.width - padX * 2) / (b.maxX - b.minX),
    (box.height - padTop - padBottom) / (b.maxY - b.minY),
  );
  const scale = Math.max(fit, 4) * state.zoom;
  const centerX = box.width / 2;
  const centerY = padTop + (box.height - padTop - padBottom) / 2;
  view = {
    scale,
    x: centerX - ((b.minX + b.maxX) / 2) * scale + state.pan.x,
    y: centerY - (state.plan.height - (b.minY + b.maxY) / 2) * scale + state.pan.y,
  };
  $("#mapWrap").dataset.pan = String(state.zoom > 1);
}

function toScreen(pt) {
  return {
    x: view.x + pt[0] * view.scale,
    y: view.y + (state.plan.height - pt[1]) * view.scale,
  };
}

function toWorld(px) {
  return [
    clamp((px.x - view.x) / view.scale, 0, state.plan.width),
    clamp(state.plan.height - (px.y - view.y) / view.scale, 0, state.plan.height),
  ];
}

function setZoom(next, anchor = { x: box.width / 2, y: box.height / 2 }) {
  const zoom = clamp(next, 1, 4);
  const ratio = zoom / state.zoom;
  state.pan.x = (state.pan.x + box.width / 2 - anchor.x) * ratio + anchor.x - box.width / 2;
  state.pan.y = (state.pan.y + box.height / 2 - anchor.y) * ratio + anchor.y - box.height / 2;
  state.zoom = zoom;
  if (zoom === 1) state.pan = { x: 0, y: 0 };
  computeView();
  paint();
}

/* ---------- Carte : sol, murs, décor (rendu une fois par cadrage) ---------- */
function hash2(i, j) {
  const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function polyPath(c, pts) {
  c.beginPath();
  pts.forEach((p, i) => (i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y)));
  c.closePath();
}

function walkablePoints() {
  const b = planBounds();
  const raw = state.plan.walkable || [[b.minX, b.minY], [b.maxX, b.minY], [b.maxX, b.maxY], [b.minX, b.maxY]];
  return raw.map(toScreen);
}

function drawGround() {
  const key = [box.width, box.height, box.dpr, view.scale, view.x, view.y, state.layers.zones, state.runId].join("|");
  if (key === groundKey) return;
  groundKey = key;
  ground.width = canvas.width;
  ground.height = canvas.height;
  const c = ground.getContext("2d");
  c.setTransform(box.dpr, 0, 0, box.dpr, 0, 0);
  const { width, height } = box;

  // Dehors : nuit, à peine une trame.
  c.fillStyle = "#08090c";
  c.fillRect(0, 0, width, height);
  c.strokeStyle = "rgba(255, 255, 255, .018)";
  c.lineWidth = 1;
  c.beginPath();
  for (let x = -height; x < width; x += 14) { c.moveTo(x, height); c.lineTo(x + height, 0); }
  c.stroke();

  // Dalle : ombre portée du plan sur la nuit.
  const walk = walkablePoints();
  c.save();
  c.shadowColor = "rgba(0, 0, 0, .8)";
  c.shadowBlur = 44;
  c.shadowOffsetY = 12;
  polyPath(c, walk);
  c.fillStyle = "#1d1f27";
  c.fill();
  c.restore();

  c.save();
  polyPath(c, walk);
  c.clip();

  // Pavage : dalles de 2,5 m, teinte légèrement différente d'une dalle à l'autre.
  const b = planBounds();
  const tile = 2.5;
  for (let i = 0; i * tile < b.maxX - b.minX; i += 1) {
    for (let j = 0; j * tile < b.maxY - b.minY; j += 1) {
      const offset = j % 2 ? tile / 2 : 0;
      const wx = b.minX + i * tile - offset;
      const wy = b.minY + j * tile;
      const p = toScreen([wx, wy + tile]);
      const n = hash2(i, j);
      const light = 31 + Math.round(n * 4);
      c.fillStyle = `rgb(${light}, ${light + 1}, ${light + 8})`;
      c.fillRect(p.x, p.y, tile * view.scale, tile * view.scale);
      if (offset && i === Math.floor((b.maxX - b.minX) / tile)) {
        c.fillRect(p.x + tile * view.scale, p.y, tile * view.scale, tile * view.scale);
      }
      c.strokeStyle = "rgba(0, 0, 0, .2)";
      c.lineWidth = 1;
      c.strokeRect(p.x + .5, p.y + .5, tile * view.scale, tile * view.scale);
    }
  }

  // Éclairage : une nappe centrale, des bords qui tombent dans le noir.
  const topLeft = toScreen([b.minX, b.maxY]);
  const bottomRight = toScreen([b.maxX, b.minY]);
  const cx = (topLeft.x + bottomRight.x) / 2;
  const cy = (topLeft.y + bottomRight.y) / 2;
  const reach = Math.hypot(bottomRight.x - topLeft.x, bottomRight.y - topLeft.y) * .58;
  const light = c.createRadialGradient(cx, cy - reach * .1, reach * .1, cx, cy, reach);
  light.addColorStop(0, "rgba(190, 196, 255, .075)");
  light.addColorStop(.55, "rgba(0, 0, 0, 0)");
  light.addColorStop(1, "rgba(0, 0, 0, .5)");
  c.fillStyle = light;
  c.fillRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);

  if (state.layers.zones && view.scale >= 9) drawZones(c);
  c.restore();

  for (const ob of state.plan.obstacles || []) drawObstacle(c, ob);

  // Murs de l'esplanade.
  polyPath(c, walk);
  c.lineJoin = "round";
  c.strokeStyle = "#050507";
  c.lineWidth = 7;
  c.stroke();
  c.strokeStyle = "#4a4c59";
  c.lineWidth = 2;
  c.stroke();
}

function drawZones(c) {
  c.font = "600 11px Inter, sans-serif";
  if ("letterSpacing" in c) c.letterSpacing = "1.2px";
  c.textAlign = "left";
  c.textBaseline = "top";
  c.strokeStyle = "rgba(255, 255, 255, .055)";
  c.lineWidth = 1;
  for (const z of state.plan.zones || []) {
    if (z.hidden || !z.polygon?.length) continue;
    const pts = z.polygon.map(toScreen);
    c.setLineDash([2, 6]);
    polyPath(c, pts);
    c.stroke();
    c.setLineDash([]);
    const left = Math.min(...pts.map((p) => p.x));
    const top = Math.min(...pts.map((p) => p.y));
    c.fillStyle = "rgba(228, 228, 231, .62)";
    c.fillText((z.label || z.id).toUpperCase(), left + 10, top + 9);
  }
  if ("letterSpacing" in c) c.letterSpacing = "0px";
}

function drawObstacle(c, ob) {
  if (!ob.polygon?.length) return;
  const base = ob.polygon.map(toScreen);
  const lift = { tour: 15, scene: 8, stand: 6, fontaine: 3 }[ob.kind] ?? 5;
  const h = Math.max(2, lift * clamp(view.scale / 16, .6, 1.6));
  const top = base.map((p) => ({ x: p.x, y: p.y - h }));

  // Ombre portée, lumière venant du nord-ouest.
  c.save();
  c.shadowColor = "rgba(0, 0, 0, .6)";
  c.shadowBlur = 10 + h;
  c.shadowOffsetX = h * .5;
  c.shadowOffsetY = h * .8;
  polyPath(c, base);
  c.fillStyle = "#101116";
  c.fill();
  c.restore();

  // Flancs.
  c.fillStyle = "#23242c";
  for (let dy = 0; dy < h; dy += 1) {
    polyPath(c, base.map((p) => ({ x: p.x, y: p.y - dy })));
    c.fill();
  }

  // Dessus.
  const minY = Math.min(...top.map((p) => p.y));
  const maxY = Math.max(...top.map((p) => p.y));
  const face = c.createLinearGradient(0, minY, 0, maxY);
  const palette = {
    tour: ["#50525f", "#3b3d48"],
    scene: ["#4b4238", "#39322b"],
    stand: ["#474957", "#363742"],
    fontaine: ["#5a5c69", "#44464f"],
  }[ob.kind] || ["#474957", "#363742"];
  face.addColorStop(0, palette[0]);
  face.addColorStop(1, palette[1]);
  polyPath(c, top);
  c.fillStyle = face;
  c.fill();

  c.save();
  polyPath(c, top);
  c.clip();
  const minX = Math.min(...top.map((p) => p.x));
  const maxX = Math.max(...top.map((p) => p.x));
  if (ob.kind === "stand") {
    c.fillStyle = "rgba(255, 255, 255, .07)";
    const band = Math.max(4, view.scale * .4);
    for (let x = minX, i = 0; x < maxX; x += band, i += 1) if (i % 2) c.fillRect(x, minY, band, maxY - minY);
  } else if (ob.kind === "scene") {
    c.strokeStyle = "rgba(0, 0, 0, .28)";
    c.lineWidth = 1;
    c.beginPath();
    for (let y = minY; y < maxY; y += Math.max(4, view.scale * .35)) { c.moveTo(minX, y); c.lineTo(maxX, y); }
    c.stroke();
  } else if (ob.kind === "tour") {
    c.strokeStyle = "rgba(255, 255, 255, .09)";
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(minX, minY); c.lineTo(maxX, maxY);
    c.moveTo(maxX, minY); c.lineTo(minX, maxY);
    c.stroke();
  } else if (ob.kind === "fontaine") {
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const inner = top.map((p) => ({ x: cx + (p.x - cx) * .74, y: cy + (p.y - cy) * .74 }));
    const water = c.createRadialGradient(cx, cy, 1, cx, cy, (maxX - minX) / 2);
    water.addColorStop(0, "#3a7f9e");
    water.addColorStop(1, "#173a4d");
    polyPath(c, inner);
    c.fillStyle = water;
    c.fill();
    c.strokeStyle = "rgba(190, 230, 255, .22)";
    c.lineWidth = 1;
    for (const r of [.16, .3]) {
      c.beginPath();
      c.arc(cx, cy, (maxX - minX) * r, 0, Math.PI * 2);
      c.stroke();
    }
  }
  c.restore();

  polyPath(c, top);
  c.strokeStyle = "rgba(255, 255, 255, .13)";
  c.lineWidth = 1;
  c.stroke();

  if (ob.kind === "tour") {
    c.font = "650 11px Inter, sans-serif";
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillStyle = "#e4e4e7";
    c.fillText(ob.label || "Tour", (minX + maxX) / 2, (minY + maxY) / 2);
  }
}

/* ---------- Carte : ce qui bouge ---------- */
function paint(now = performance.now()) {
  if (!box.width || !state.plan || !state.snapshot) return;
  drawGround();
  const { width, height, dpr } = box;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(ground, 0, 0);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (state.layers.density) drawDensity();
  if (state.layers.smoke) drawSmoke(now);
  drawExits(now);
  if (state.layers.trail) drawSelectedTrail();
  if (state.layers.messages) drawTalk(now);
  drawGhosts(now);
  drawAgents(now);
  drawBursts(now);
  if (state.placingSmoke) drawSmokePreview();

  if (state.flash) {
    const t = (now - state.flash.start) / 1100;
    if (t >= 1) {
      state.flash = null;
    } else {
      const edge = ctx.createRadialGradient(width / 2, height / 2, Math.min(width, height) * .35, width / 2, height / 2, Math.max(width, height) * .68);
      edge.addColorStop(0, `rgba(${state.flash.rgb}, 0)`);
      edge.addColorStop(1, `rgba(${state.flash.rgb}, ${(.34 * (1 - t)).toFixed(3)})`);
      ctx.fillStyle = edge;
      ctx.fillRect(0, 0, width, height);
    }
  }
}

function busy(now) {
  return now - state.tween.start < state.tween.duration
    || state.ghosts.length || state.bursts.length || state.ripples.length || state.packets.length || state.flash;
}

function loop(now) {
  loopHandle = null;
  // Rien n'anime ? 24 images/s suffisent à la fumée et aux chevrons.
  if (busy(now) || now - lastPaint > 41) {
    paint(now);
    lastPaint = now;
  }
  if (!MOTION.matches && !document.hidden && state.snapshot) loopHandle = requestAnimationFrame(loop);
}

function wake() {
  if (MOTION.matches || document.hidden) { paint(); return; }
  if (!loopHandle) loopHandle = requestAnimationFrame(loop);
}

function displayPos(agent, now) {
  const to = agent.pos;
  const from = state.tween.from.get(agent.id);
  if (!from || !state.tween.duration) return to;
  const t = clamp((now - state.tween.start) / state.tween.duration, 0, 1);
  return [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t];
}

function exitPointFor(agent, pos) {
  const exits = state.plan?.exits || [];
  const mid = (ex) => [(ex.a[0] + ex.b[0]) / 2, (ex.a[1] + ex.b[1]) / 2];
  // Le journal ne dit pas par où l'agent est passé : l'issue la plus proche de
  // sa dernière position sert uniquement à placer l'animation.
  let best = exits[0];
  let bestDist = Infinity;
  for (const ex of exits) {
    const m = mid(ex);
    const d = Math.hypot(m[0] - pos[0], m[1] - pos[1]);
    if (d < bestDist) { best = ex; bestDist = d; }
  }
  return { id: best?.id, point: best ? mid(best) : pos };
}

function drawDensity() {
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  const r = view.scale * 1.9;
  for (const cell of state.snapshot.density_grid || []) {
    if ((cell.n ?? 0) < 2) continue;
    const p = toScreen([cell.x + .5, cell.y + .5]);
    const alpha = Math.min(.13 * cell.n, .42);
    const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
    g.addColorStop(0, `rgba(251, 146, 60, ${alpha})`);
    g.addColorStop(1, "rgba(251, 146, 60, 0)");
    ctx.fillStyle = g;
    ctx.fillRect(p.x - r, p.y - r, r * 2, r * 2);
  }
  ctx.restore();
}

const PUFFS = Array.from({ length: 18 }, (_, i) => ({
  angle: hash2(i, 1) * Math.PI * 2,
  dist: .08 + hash2(i, 2) * .66,
  size: .26 + hash2(i, 3) * .3,
  speed: (hash2(i, 4) - .5) * .00012,
  phase: hash2(i, 5) * Math.PI * 2,
}));

function currentSmoke() {
  const snap = state.snapshot;
  if (!snap.smoke_active) return null;
  const smoke = snap.smoke || state.smokeEvent;
  return smoke?.position ? smoke : null;
}

function drawSmoke(now) {
  const smoke = currentSmoke();
  if (!smoke) return;
  const center = toScreen(smoke.position);
  const age = MOTION.matches ? 1 : clamp((now - state.smokeBorn) / 1400, 0, 1);
  const grow = 1 - (1 - age) ** 3;
  const full = (smoke.radius || 12) * view.scale;
  const r = full * (state.held ? 1 : grow);

  ctx.save();
  polyPath(ctx, walkablePoints());
  ctx.clip();

  for (const puff of PUFFS) {
    const a = puff.angle + now * puff.speed;
    const wobble = Math.sin(now * .00035 + puff.phase) * .05;
    const px = center.x + Math.cos(a) * r * (puff.dist + wobble);
    const py = center.y + Math.sin(a) * r * (puff.dist + wobble);
    const pr = r * puff.size;
    const g = ctx.createRadialGradient(px, py, 0, px, py, pr);
    g.addColorStop(0, "rgba(205, 207, 216, .17)");
    g.addColorStop(.6, "rgba(170, 172, 184, .07)");
    g.addColorStop(1, "rgba(150, 152, 165, 0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(px, py, pr, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.setLineDash([3, 7]);
  ctx.strokeStyle = "rgba(228, 228, 231, .34)";
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.arc(center.x, center.y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  const walk = planBounds();
  const labelY = Math.max(center.y - r + 18, toScreen([0, walk.maxY]).y + 18);
  pill(ctx, center.x, labelY, "FUMÉE", { fg: "#e4e4e7", bg: "rgba(20, 21, 26, .78)", border: "rgba(228, 228, 231, .3)" });
}

function pill(c, cx, cy, text, { fg, bg, border }) {
  c.font = "650 11px Inter, sans-serif";
  const w = c.measureText(text).width + 16;
  roundRect(c, cx - w / 2, cy - 10, w, 20, 10);
  c.fillStyle = bg;
  c.fill();
  c.strokeStyle = border;
  c.lineWidth = 1;
  c.stroke();
  c.fillStyle = fg;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText(text, cx, cy + .5);
  c.textAlign = "left";
}

function exitOutward(ex) {
  const b = planBounds();
  const mx = (ex.a[0] + ex.b[0]) / 2;
  const my = (ex.a[1] + ex.b[1]) / 2;
  const toEdge = [
    [Math.abs(my - b.maxY), 0, -1],
    [Math.abs(my - b.minY), 0, 1],
    [Math.abs(mx - b.maxX), 1, 0],
    [Math.abs(mx - b.minX), -1, 0],
  ].sort((p, q) => p[0] - q[0])[0];
  return { x: toEdge[1], y: toEdge[2] }; // repère écran
}

function drawExits(now) {
  for (const ex of state.plan.exits || []) {
    const a = toScreen(ex.a);
    const b = toScreen(ex.b);
    const open = isExitOpen(ex.id);
    const pal = EXIT_PALETTE[ex.id] || EXIT_PALETTE.none;
    const col = open ? pal.fill : "#ef4444";
    const out = exitOutward(ex);
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;

    ctx.save();
    ctx.lineCap = "round";
    ctx.strokeStyle = "#08090c";
    ctx.lineWidth = 9;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.shadowColor = col;
    ctx.shadowBlur = open ? 16 : 10;
    ctx.strokeStyle = col;
    ctx.lineWidth = 5;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.restore();

    if (open) {
      // Chevrons qui filent vers l'extérieur.
      const phase = MOTION.matches ? .5 : (now / 1400) % 1;
      const size = 5;
      const side = { x: -out.y, y: out.x };
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.75;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (let i = 0; i < 2; i += 1) {
        const t = (phase + i / 2) % 1;
        const d = 8 + t * 14;
        ctx.globalAlpha = Math.sin(t * Math.PI) * .9;
        const tipX = mx + out.x * (d + size);
        const tipY = my + out.y * (d + size);
        ctx.beginPath();
        ctx.moveTo(mx + out.x * d + side.x * size, my + out.y * d + side.y * size);
        ctx.lineTo(tipX, tipY);
        ctx.lineTo(mx + out.x * d - side.x * size, my + out.y * d - side.y * size);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    } else {
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      const s = 7;
      ctx.beginPath();
      ctx.moveTo(mx - s, my - s); ctx.lineTo(mx + s, my + s);
      ctx.moveTo(mx + s, my - s); ctx.lineTo(mx - s, my + s);
      ctx.stroke();
    }

    // Étiquette à l'extérieur du plan : elle ne couvre ni la foule ni le décor.
    const title = `Sortie ${ex.id}`;
    const sub = open ? (box.width < 640 ? "" : ex.label || "") : "FERMÉE";
    ctx.font = "650 12px Inter, sans-serif";
    const w1 = ctx.measureText(title).width + 18;
    ctx.font = "500 11px Inter, sans-serif";
    const w2 = ctx.measureText(sub).width;
    const w = Math.max(w1, w2) + 18;
    const h = sub ? 38 : 24;
    const gap = 26;
    let lx = mx + out.x * gap - (out.x === 0 ? w / 2 : out.x < 0 ? w : 0);
    let ly = my + out.y * gap - (out.y === 0 ? h / 2 : out.y < 0 ? h : 0);
    lx = clamp(lx, 6, box.width - w - 6);
    ly = clamp(ly, 6, box.height - h - 6);

    roundRect(ctx, lx, ly, w, h, 9);
    ctx.fillStyle = "rgba(16, 17, 22, .9)";
    ctx.fill();
    ctx.strokeStyle = open ? `${col}88` : col;
    ctx.lineWidth = 1;
    ctx.stroke();
    agentShape(ctx, pal.shape, lx + 15, ly + 12.5, 4.6);
    ctx.fillStyle = col;
    ctx.fill();
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = "650 12px Inter, sans-serif";
    ctx.fillStyle = "#f4f4f5";
    ctx.fillText(title, lx + 25, ly + 13);
    if (sub) {
      ctx.font = open ? "500 11px Inter, sans-serif" : "700 11px Inter, sans-serif";
      ctx.fillStyle = open ? "#a9a9b4" : "#fb8a8a";
      ctx.fillText(sub, lx + 9, ly + 27);
    }
  }
}

function drawSelectedTrail() {
  if (!state.selectedId) return;
  const tick = displayedTick();
  const pts = [];
  for (const t of [...state.snapshotsByTick.keys()].sort((a, b) => a - b)) {
    if (t > tick) break;
    const a = state.snapshotsByTick.get(t).agents?.find((x) => x.id === state.selectedId);
    if (a && !a.evacuated && a.pos) pts.push(a.pos);
  }
  if (pts.length < 2) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (let i = 1; i < pts.length; i += 1) {
    const p0 = toScreen(pts[i - 1]);
    const p1 = toScreen(pts[i]);
    ctx.strokeStyle = `rgba(158, 165, 251, ${(.15 + .75 * (i / pts.length)).toFixed(2)})`;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke();
  }
}

function drawTalk(now) {
  const byId = new Map((state.snapshot.agents || []).map((a) => [a.id, a]));
  const LIFE = 1300;
  state.ripples = state.ripples.filter((r) => now - r.created < LIFE);
  state.packets = state.packets.filter((p) => now - p.created < LIFE);

  for (const ripple of state.ripples) {
    const from = byId.get(ripple.from);
    if (!from?.pos || from.evacuated) continue;
    const p = toScreen(displayPos(from, now));
    const t = (now - ripple.created) / LIFE;
    ctx.strokeStyle = `rgba(158, 165, 251, ${(.6 * (1 - t)).toFixed(3)})`;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 6 + t * view.scale * 2.4, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Les liens un à un : seulement ceux qui se lisent. À 300 d'un coup, ce n'est
  // plus de l'information, c'est un gribouillis qui masque les formes.
  const selected = state.selectedId;
  const few = state.packets.length <= 24;
  for (const pkt of state.packets) {
    if (!few && pkt.from !== selected && pkt.to !== selected) continue;
    const from = byId.get(pkt.from);
    const to = byId.get(pkt.to);
    if (!from?.pos || !to?.pos || from.evacuated || to.evacuated) continue;
    const a = toScreen(displayPos(from, now));
    const b = toScreen(displayPos(to, now));
    const t = (now - pkt.created) / LIFE;
    ctx.strokeStyle = `rgba(158, 165, 251, ${(.4 * (1 - t)).toFixed(3)})`;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.fillStyle = "#e0e7ff";
    ctx.beginPath();
    ctx.arc(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function agentShape(c, shape, x, y, r) {
  c.beginPath();
  if (shape === "square") {
    c.rect(x - r * .85, y - r * .85, r * 1.7, r * 1.7);
  } else if (shape === "triangle") {
    c.moveTo(x, y - r * 1.1);
    c.lineTo(x + r * 1.05, y + r * .9);
    c.lineTo(x - r * 1.05, y + r * .9);
    c.closePath();
  } else if (shape === "diamond") {
    c.moveTo(x, y - r * 1.05);
    c.lineTo(x + r * 1.05, y);
    c.lineTo(x, y + r * 1.05);
    c.lineTo(x - r * 1.05, y);
    c.closePath();
  } else {
    c.arc(x, y, r, 0, Math.PI * 2);
  }
}

function agentRadius() { return clamp(view.scale * .38, 5.5, 9); }

function drawGhosts(now) {
  const r = agentRadius();
  state.ghosts = state.ghosts.filter((g) => {
    const t = (now - g.start) / g.duration;
    if (t >= 1) {
      state.bursts.push({ exit: g.exit, start: now });
      return false;
    }
    const p = toScreen([g.from[0] + (g.to[0] - g.from[0]) * t, g.from[1] + (g.to[1] - g.from[1]) * t]);
    const pal = EXIT_PALETTE[g.belief] || EXIT_PALETTE.none;
    ctx.globalAlpha = 1 - t * t;
    agentShape(ctx, pal.shape, p.x, p.y, r);
    ctx.fillStyle = pal.fill;
    ctx.fill();
    ctx.globalAlpha = 1;
    return true;
  });
}

function drawBursts(now) {
  const LIFE = 620;
  state.bursts = state.bursts.filter((b) => now - b.start < LIFE);
  for (const burst of state.bursts) {
    const ex = (state.plan.exits || []).find((e) => e.id === burst.exit);
    if (!ex) continue;
    const t = (now - burst.start) / LIFE;
    const p = toScreen([(ex.a[0] + ex.b[0]) / 2, (ex.a[1] + ex.b[1]) / 2]);
    ctx.strokeStyle = (EXIT_PALETTE[ex.id] || EXIT_PALETTE.none).fill;
    ctx.globalAlpha = (1 - t) * .8;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 6 + t * 26, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
}

function drawAgents(now) {
  const active = (state.snapshot.agents || []).filter((a) => !a.evacuated && a.pos);
  const r = agentRadius();
  const selected = state.selectedId;
  const positions = active.map((a) => ({ a, pos: displayPos(a, now), p: toScreen(displayPos(a, now)) }));

  // Ombres d'abord : aucune ne doit passer sur une personne voisine.
  ctx.fillStyle = "rgba(0, 0, 0, .42)";
  for (const { p } of positions) {
    ctx.beginPath();
    ctx.ellipse(p.x + 1.5, p.y + r * .7, r * 1.05, r * .5, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  for (const { a, p } of positions) {
    const key = a.belief && EXIT_PALETTE[a.belief] ? a.belief : "none";
    const pal = EXIT_PALETTE[key];
    const dimmed = selected && selected !== a.id;
    ctx.globalAlpha = dimmed ? .38 : 1;

    // Traînée : le mouvement de ce tick, tel qu'il est dans le journal.
    const from = state.tween.from.get(a.id);
    if (from && state.tween.duration) {
      const d = Math.hypot(a.pos[0] - from[0], a.pos[1] - from[1]);
      if (d > .4) {
        const len = Math.min(r * 2.4, d * view.scale * .4);
        const ux = (a.pos[0] - from[0]) / d;
        const uy = -(a.pos[1] - from[1]) / d;
        ctx.strokeStyle = pal.fill;
        ctx.globalAlpha = (dimmed ? .38 : 1) * .4;
        ctx.lineWidth = r * .8;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x - ux * len, p.y - uy * len);
        ctx.stroke();
        ctx.globalAlpha = dimmed ? .38 : 1;
      }
    }

    agentShape(ctx, pal.shape, p.x, p.y, r);
    ctx.fillStyle = pal.fill;
    ctx.fill();
    ctx.strokeStyle = "#0c0d11";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    if (a.belief && !isExitOpen(a.belief)) {
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 1.75;
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    if (a.id === state.hoverId && a.id !== selected) {
      ctx.strokeStyle = "rgba(255, 255, 255, .7)";
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 4, 0, Math.PI * 2); ctx.stroke();
    }
  }

  const chosen = positions.find(({ a }) => a.id === selected);
  if (chosen) {
    const { a, p } = chosen;
    const pulse = MOTION.matches ? 0 : (now / 1300) % 1;
    ctx.strokeStyle = `rgba(255, 255, 255, ${(.7 * (1 - pulse)).toFixed(3)})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(p.x, p.y, r + 5 + pulse * 11, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(p.x, p.y, r + 4.5, 0, Math.PI * 2); ctx.stroke();
    pill(ctx, p.x, p.y - r - 20, a.id, { fg: "#0c0d11", bg: "#f4f4f5", border: "#f4f4f5" });
  }
}

function drawSmokePreview() {
  const at = state.placeAt;
  if (!at) return;
  const c = toScreen(at);
  const r = 15 * view.scale;
  ctx.setLineDash([6, 6]);
  ctx.strokeStyle = "rgba(251, 138, 138, .9)";
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI * 2); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(248, 113, 113, .1)";
  ctx.fill();
  ctx.fillStyle = "#fb8a8a";
  ctx.beginPath(); ctx.arc(c.x, c.y, 3.5, 0, Math.PI * 2); ctx.fill();
}

/* ---------- Fil ---------- */
const feedGroups = new Map();

function feedRow(tick, kind) {
  const li = document.createElement("li");
  li.dataset.kind = kind;
  li.dataset.tick = String(tick ?? 0);
  const time = document.createElement("time");
  time.textContent = tick != null ? `t${tick}` : "—";
  const body = document.createElement("div");
  body.className = "feed-text";
  li.append(time, body);
  return { li, body };
}

function insertFeed(li) {
  const feed = $("#feed");
  $("#feedEmpty").hidden = true;
  feed.prepend(li);
  while (feed.children.length > FEED_LIMIT) {
    const last = feed.lastElementChild;
    for (const [key, group] of feedGroups) if (group.li === last) feedGroups.delete(key);
    last.remove();
  }
  if (state.held) li.hidden = Number(li.dataset.tick) > displayedTick();
}

function pushFeed(tick, kind, tag, text, agentId = null) {
  const { li, body } = feedRow(tick, kind);
  const badge = document.createElement("span");
  badge.className = "tag";
  badge.textContent = tag;
  const line = document.createElement("span");
  line.className = "feed-line";
  if (agentId && text.startsWith(agentId)) {
    line.append(agentButton(agentId), document.createTextNode(text.slice(agentId.length)));
  } else {
    line.textContent = text;
  }
  body.append(badge, line);
  insertFeed(li);
}

/** Une ligne par tick et par nature : 30 paroles identiques se lisent en une. */
function pushGrouped(tick, kind, tag, text, agentId) {
  const key = `${tick}|${kind}`;
  let group = feedGroups.get(key);
  if (!group) {
    const { li, body } = feedRow(tick, kind === "talk" ? "talk" : "decision");
    const badge = document.createElement("span");
    badge.className = "tag";
    const lines = document.createElement("div");
    lines.className = "feed-lines";
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Voir qui";
    const agents = document.createElement("div");
    agents.className = "feed-agents";
    details.append(summary, agents);
    body.append(badge, lines, details);
    group = { li, badge, lines, agents, tag, counts: new Map(), people: new Set() };
    feedGroups.set(key, group);
    insertFeed(li);
  }
  let entry = group.counts.get(text);
  if (!entry) {
    const line = document.createElement("div");
    line.className = "feed-line";
    line.textContent = text;
    const times = document.createElement("span");
    times.className = "times";
    line.append(times);
    group.lines.append(line);
    entry = { n: 0, times };
    group.counts.set(text, entry);
  }
  entry.n += 1;
  entry.times.textContent = entry.n > 1 ? `×${entry.n}` : "";
  if (agentId && !group.people.has(agentId)) {
    group.people.add(agentId);
    group.agents.append(agentButton(agentId));
  }
  const n = group.people.size;
  group.badge.textContent = `${group.tag} · ${n} personne${n > 1 ? "s" : ""}`;
}

function agentButton(agentId) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "agent-link";
  btn.textContent = agentId;
  btn.addEventListener("click", () => selectPerson(agentId, true));
  return btn;
}

/** Le fil suit l'instant affiché : revenir à t12 masque ce qui vient après. */
function applyFeedFilter() {
  const limit = state.held ? displayedTick() : Infinity;
  for (const li of $("#feed").children) li.hidden = Number(li.dataset.tick) > limit;
  $("#feedCount").textContent = state.held && state.snapshot ? `jusqu'à t${displayedTick()}` : "";
}

/* ---------- Sélection et annuaire ---------- */
function selectPerson(id, focusHeading = false) {
  state.selectedId = id;
  renderPerson();
  renderEndCard();
  paint();
  if (id && focusHeading) $("#personId").focus();
}

function renderFindList(query = "") {
  const list = $("#findList");
  list.replaceChildren();
  const q = query.trim().toLowerCase();
  const agents = (state.snapshot?.agents || []).filter((a) => {
    const hay = `${a.id} ${a.label || ""} ${a.profile || ""} ${a.belief ? `sortie ${a.belief}` : "sans sortie"} ${a.evacuated ? "sortie évacuée" : "présente"}`.toLowerCase();
    return hay.includes(q);
  });

  $("#findCount").textContent = state.snapshot ? `${agents.length} personne(s) affichée(s).` : "Aucune simulation connectée.";

  for (const a of agents) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    if (a.id === state.selectedId) btn.setAttribute("aria-current", "true");
    const key = a.belief && EXIT_PALETTE[a.belief] ? a.belief : "none";
    const status = a.evacuated
      ? "Sortie de l'esplanade"
      : a.belief
        ? `Vise la sortie ${a.belief} (${Math.round((a.confidence ?? 0) * 100)} %)`
        : "Sans sortie choisie";
    const shape = document.createElement("span");
    shape.className = `shape shape-${key}`;
    shape.setAttribute("aria-hidden", "true");
    const id = document.createElement("strong");
    id.textContent = a.id;
    const small = document.createElement("small");
    small.textContent = `${a.label || a.profile || "Personne"} · ${status}`;
    btn.append(shape, id, small);
    btn.addEventListener("click", () => {
      $("#findDialog").close();
      selectPerson(a.id, true);
    });
    li.append(btn);
    list.append(li);
  }
}

/* ---------- Interventions ---------- */
function populateExitSelect() {
  const sel = $("#exitSelect");
  sel.replaceChildren();
  for (const ex of state.plan?.exits || [{ id: "A" }, { id: "B" }, { id: "C" }]) {
    const opt = document.createElement("option");
    opt.value = ex.id;
    opt.textContent = `Sortie ${ex.id}${ex.label ? ` · ${ex.label}` : ""}`;
    sel.append(opt);
  }
}

function updateInterveneState() {
  const enabled = state.conn === "live" && state.live;
  const notice = $("#interveneNotice");
  notice.dataset.state = enabled ? "live" : "readonly";
  if (enabled) {
    notice.textContent = "Simulation en direct : chaque action ci-dessous est envoyée au moteur et inscrite au journal.";
  } else if (state.conn === "replay" || state.conn === "ended") {
    notice.textContent = "Vous regardez un run enregistré (maree serve). Un journal terminé ne peut pas être modifié : lancez « uv run maree live » pour intervenir en direct.";
  } else {
    notice.textContent = "Aucun moteur en direct connecté. Lancez « uv run maree live » pour pouvoir agir sur le monde.";
  }
  $("#interveneControls").setAttribute("aria-disabled", String(!enabled));
  for (const el of ["#announceInput", "#announceButton", "#exitSelect", "#closeExitButton", "#smokeButton"]) {
    $(el).disabled = !enabled;
  }
}

function sendInjection(payload) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    setFeedback("Pas de connexion active avec le moteur.", "error");
    return;
  }
  state.socket.send(JSON.stringify({ type: "inject", ...payload }));
}

function setFeedback(text, type = "") {
  const el = $("#interveneFeedback");
  el.textContent = text;
  el.dataset.type = type;
}

function stopPlacing() {
  state.placingSmoke = false;
  state.placeAt = null;
  $("#mapWrap").dataset.placing = "false";
  $("#smokeHint").hidden = true;
  paint();
}

function placeSmoke(at) {
  const position = [Math.round(at[0] * 10) / 10, Math.round(at[1] * 10) / 10];
  stopPlacing();
  sendInjection({ kind: "smoke", position, radius: 15 });
}

/* ---------- Helpers ---------- */
function isExitOpen(id) {
  const open = state.snapshot?.exits_open;
  return !open || open.includes(id);
}

function exitLabelFor(id) {
  if (!id || !state.plan?.exits) return "";
  return state.plan.exits.find((e) => e.id === id)?.label || "";
}

function zoneNameAt(pos) {
  if (!pos || !state.plan?.zones) return "";
  const [x, y] = pos;
  for (const z of state.plan.zones) {
    if (!z.polygon?.length) continue;
    const xs = z.polygon.map((p) => p[0]);
    const ys = z.polygon.map((p) => p[1]);
    if (x >= Math.min(...xs) && x <= Math.max(...xs) && y >= Math.min(...ys) && y <= Math.max(...ys)) {
      return z.label || z.id;
    }
  }
  return "";
}

function formatWhen(tick) {
  const t = tick ?? 0;
  return t < 0 ? `J-${Math.round(-t / 8640)}` : `t${t}`;
}

function formatBeliefSource(src) {
  if (src === "connu") return "connue dès le départ";
  if (src.startsWith("decision:")) return `choisie à ${src.split(":")[1]}`;
  if (src.startsWith("message:")) return "recommandée par un voisin";
  return src;
}

function formatPerceived(sig) {
  if (PERCEIVED_LABELS[sig]) return PERCEIVED_LABELS[sig];
  if (sig.startsWith("closed:")) return `Sait que la sortie ${sig.slice(7)} est fermée`;
  return sig;
}

function roundRect(context, x, y, w, h, r) {
  const rad = Math.min(r, w / 2, h / 2);
  context.beginPath();
  context.moveTo(x + rad, y);
  context.arcTo(x + w, y, x + w, y + h, rad);
  context.arcTo(x + w, y + h, x, y + h, rad);
  context.arcTo(x, y + h, x, y, rad);
  context.arcTo(x, y, x + w, y, rad);
  context.closePath();
}

function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }
function announcePolite(text) { $("#announcer").textContent = text; }

function agentAt(pt, radius) {
  let best = null;
  let bestDist = radius;
  const now = performance.now();
  for (const a of state.snapshot?.agents || []) {
    if (a.evacuated || !a.pos) continue;
    const p = toScreen(displayPos(a, now));
    const d = Math.hypot(pt.x - p.x, pt.y - p.y);
    if (d < bestDist) { best = a; bestDist = d; }
  }
  return best;
}

function canvasPoint(ev) {
  const rect = canvas.getBoundingClientRect();
  return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
}

/* ---------- Événements : carte ---------- */
let drag = null;

canvas.addEventListener("pointerdown", (ev) => {
  drag = { x: ev.clientX, y: ev.clientY, panX: state.pan.x, panY: state.pan.y, moved: false };
  canvas.setPointerCapture(ev.pointerId);
});

canvas.addEventListener("pointermove", (ev) => {
  if (!state.snapshot || !state.plan) return;
  const pt = canvasPoint(ev);
  if (drag) {
    const dx = ev.clientX - drag.x;
    const dy = ev.clientY - drag.y;
    if (Math.hypot(dx, dy) > 4) drag.moved = true;
    if (drag.moved && state.zoom > 1 && !state.placingSmoke) {
      state.pan = { x: drag.panX + dx, y: drag.panY + dy };
      computeView();
      paint();
    }
  }
  if (state.placingSmoke) {
    state.placeAt = toWorld(pt);
    paint();
    return;
  }
  const hit = agentAt(pt, 14);
  const tip = $("#mapTip");
  state.hoverId = hit?.id ?? null;
  $("#mapWrap").dataset.hover = String(Boolean(hit));
  if (!hit || drag?.moved) {
    tip.hidden = true;
    return;
  }
  const strong = document.createElement("strong");
  strong.textContent = hit.id;
  const detail = document.createElement("span");
  const aim = hit.belief ? ` · vise ${hit.belief} (${Math.round((hit.confidence ?? 0) * 100)} %)` : " · sans sortie";
  detail.textContent = ` ${hit.label || hit.profile || ""}${aim}`;
  tip.replaceChildren(strong, detail);
  const p = toScreen(displayPos(hit, performance.now()));
  tip.style.left = `${clamp(p.x, 120, box.width - 120)}px`;
  tip.style.top = `${p.y}px`;
  tip.hidden = false;
});

canvas.addEventListener("pointerleave", () => {
  state.hoverId = null;
  $("#mapTip").hidden = true;
});

canvas.addEventListener("pointerup", (ev) => {
  const wasDrag = drag?.moved;
  drag = null;
  if (wasDrag || !state.snapshot || !state.plan) return;
  const pt = canvasPoint(ev);
  if (state.placingSmoke) {
    placeSmoke(toWorld(pt));
    return;
  }
  const best = agentAt(pt, 24);
  state.endDismissed = true; // la carte de fin ne doit pas cacher les personnes piégées
  selectPerson(best ? best.id : null, Boolean(best));
});

canvas.addEventListener("wheel", (ev) => {
  if (!state.plan) return;
  ev.preventDefault();
  setZoom(state.zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15), canvasPoint(ev));
}, { passive: false });

canvas.addEventListener("keydown", (ev) => {
  const arrows = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
  if (state.placingSmoke) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      if (state.placeAt) placeSmoke(state.placeAt);
    } else if (arrows[ev.key]) {
      ev.preventDefault();
      const [dx, dy] = arrows[ev.key];
      state.placeAt = [
        clamp(state.placeAt[0] + dx, 0, state.plan.width),
        clamp(state.placeAt[1] + dy, 0, state.plan.height),
      ];
      paint();
    }
    return;
  }
  if (ev.key === "Enter") {
    ev.preventDefault();
    renderFindList($("#findInput").value);
    $("#findDialog").showModal();
    return;
  }
  if (!arrows[ev.key]) return;
  ev.preventDefault();
  const active = (state.snapshot?.agents || []).filter((a) => !a.evacuated);
  if (!active.length) return;
  const idx = Math.max(0, active.findIndex((a) => a.id === state.selectedId));
  const step = ev.key === "ArrowRight" || ev.key === "ArrowDown" ? 1 : -1;
  selectPerson(active[(idx + step + active.length) % active.length].id);
});

window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && state.placingSmoke) stopPlacing();
});

/* ---------- Événements : déroulé ---------- */
const timelineEl = $("#timeline");
let scrubbing = false;

timelineEl.addEventListener("pointerdown", (ev) => {
  if (!state.snapshotsByTick.size) return;
  scrubbing = true;
  timelineEl.setPointerCapture(ev.pointerId);
  scrubTo(timelineTickAt(ev.clientX));
});
timelineEl.addEventListener("pointermove", (ev) => {
  if (scrubbing) scrubTo(timelineTickAt(ev.clientX));
  showTimelineTip(ev.clientX);
});
timelineEl.addEventListener("pointerup", () => { scrubbing = false; });
timelineEl.addEventListener("pointerleave", () => { $("#timelineTip").hidden = true; });
timelineEl.addEventListener("keydown", (ev) => {
  if (!state.snapshotsByTick.size) return;
  const ticks = [...state.snapshotsByTick.keys()];
  const current = displayedTick();
  const moves = {
    ArrowLeft: current - 1,
    ArrowDown: current - 1,
    ArrowRight: current + 1,
    ArrowUp: current + 1,
    PageDown: current - 5,
    PageUp: current + 5,
    Home: Math.min(...ticks),
    End: Math.max(...ticks),
  };
  if (moves[ev.key] == null) return;
  ev.preventDefault();
  scrubTo(clamp(moves[ev.key], Math.min(...ticks), Math.max(...ticks)));
});

/* ---------- Événements : commandes ---------- */
$("#backButton").addEventListener("click", () => selectPerson(null));
$("#retryButton").addEventListener("click", () => connect());
$("#replayButton").addEventListener("click", () => connect());
$("#followButton").addEventListener("click", () => follow());
$("#pauseButton").addEventListener("click", () => {
  if (state.held) follow();
  else hold();
});

$("#findButton").addEventListener("click", () => {
  renderFindList($("#findInput").value);
  $("#findDialog").showModal();
});
$("#findInput").addEventListener("input", (ev) => renderFindList(ev.target.value));

$("#interveneButton").addEventListener("click", () => {
  updateInterveneState();
  $("#interveneDialog").showModal();
});
$("#announceButton").addEventListener("click", () => {
  const text = $("#announceInput").value.trim();
  if (!text) { setFeedback("Saisissez le texte de l'annonce.", "error"); return; }
  sendInjection({ kind: "announcement", text });
});
$("#closeExitButton").addEventListener("click", () => {
  sendInjection({ kind: "exit_closed", exit: $("#exitSelect").value });
});
$("#smokeButton").addEventListener("click", () => {
  $("#interveneDialog").close();
  state.placingSmoke = true;
  state.placeAt = [state.plan.width / 2, state.plan.height / 2];
  $("#mapWrap").dataset.placing = "true";
  $("#smokeHint").hidden = false;
  canvas.focus();
  paint();
});

$("#helpButton").addEventListener("click", () => $("#helpDialog").showModal());

$("#zoomInButton").addEventListener("click", () => setZoom(state.zoom + .5));
$("#zoomOutButton").addEventListener("click", () => setZoom(state.zoom - .5));
$("#zoomResetButton").addEventListener("click", () => { state.pan = { x: 0, y: 0 }; setZoom(1); });

$("#layersButton").addEventListener("click", (ev) => {
  const menu = $("#layersMenu");
  const open = menu.hidden;
  menu.hidden = !open;
  ev.currentTarget.setAttribute("aria-expanded", String(open));
});
$$("[data-layer]").forEach((input) => {
  input.addEventListener("change", () => {
    state.layers[input.dataset.layer] = input.checked;
    paint();
  });
});

document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });
MOTION.addEventListener("change", () => wake());
document.fonts?.ready.then(() => { groundKey = ""; paint(); });

new ResizeObserver(resizeCanvas).observe(canvas);
new ResizeObserver(() => renderTimeline()).observe(timelineEl);
buildIndicators();
renderIndicators();
connect();
