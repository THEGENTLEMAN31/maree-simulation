// MARÉE — Observatoire web (données réelles uniquement, via WebSocket).

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
    format: (v) => (v == null ? "—" : `${v.toFixed(2).replace(".", ",")} pers./m²`),
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

const state = {
  conn: "offline", // offline | connecting | replay | live | ended
  live: false,
  paused: false,
  pauseQueue: [],
  runId: null,
  plan: null,
  snapshot: null,
  snapshotsByTick: new Map(),
  indicatorsByTick: new Map(),
  indicators: {},
  selectedId: null,
  decisionsByAgent: new Map(),
  heardByAgent: new Map(),
  trails: new Map(),
  packets: [],
  timelineSeries: [],
  worldMarkers: [],
  smokeEvent: null,
  announcement: null,
  firstDangerTick: null,
  placingSmoke: false,
  zoom: 1,
  layers: { zones: true, smoke: true, density: true, messages: true, trail: true },
  socket: null,
  retryTimer: null,
};

const canvas = $("#worldCanvas");
const ctx = canvas.getContext("2d");
let box = { width: 0, height: 0, dpr: 1 };
let view = { scale: 1, x: 0, y: 0 };
let animFrame = null;

function resetRunState() {
  state.snapshot = null;
  state.snapshotsByTick.clear();
  state.indicatorsByTick.clear();
  state.indicators = {};
  state.decisionsByAgent.clear();
  state.heardByAgent.clear();
  state.trails.clear();
  state.packets = [];
  state.timelineSeries = [];
  state.worldMarkers = [];
  state.smokeEvent = null;
  state.announcement = null;
  state.firstDangerTick = null;
  state.pauseQueue = [];
  $("#feed").replaceChildren();
  $("#feedEmpty").hidden = false;
  $("#announcementBanner").hidden = true;
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
  if (state.socket && state.socket.readyState <= WebSocket.OPEN) {
    try { state.socket.close(); } catch { /* ignore */ }
  }
  const url = wsEndpoint();
  $("#endpointLabel").textContent = url;
  setConnectionState("connecting");

  let socket;
  try {
    socket = new WebSocket(url);
  } catch {
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
    resetRunState();
    setConnectionState("replay");
  });

  socket.addEventListener("message", (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (state.paused && msg.type !== "hello" && msg.type !== "trace" && msg.type !== "ack" && msg.type !== "error") {
      state.pauseQueue.push(msg);
      return;
    }
    handleFrame(msg);
  });

  socket.addEventListener("close", () => {
    clearTimeout(timeout);
    if (state.conn !== "ended") {
      setConnectionState("offline");
      scheduleRetry();
    }
  });

  socket.addEventListener("error", () => {
    clearTimeout(timeout);
  });
}

function scheduleRetry() {
  clearTimeout(state.retryTimer);
  $("#retryLabel").textContent = "Nouvelle tentative automatique dans 4 secondes…";
  state.retryTimer = setTimeout(connect, 4000);
}

function setConnectionState(mode) {
  state.conn = mode;
  const pill = $("#statusPill");
  const label = $("#statusLabel");
  pill.dataset.state = mode;

  const titles = {
    offline: "Hors ligne",
    connecting: "Connexion…",
    replay: "Rejeu d'un run enregistré",
    live: "Simulation en direct",
    ended: "Run terminé",
  };
  label.textContent = titles[mode] || mode;

  const hasData = Boolean(state.snapshot);
  $("#mapEmpty").hidden = hasData;
  $("#pauseButton").disabled = mode !== "replay" && mode !== "live";
  $("#replayButton").hidden = mode !== "ended" && mode !== "replay";

  if (!hasData) {
    if (mode === "connecting") {
      $("#emptySpinner").hidden = false;
      $("#emptyTitle").textContent = "Connexion au moteur…";
      $("#emptyText").hidden = false;
      $("#emptyCommands").hidden = true;
    } else if (mode === "offline") {
      $("#emptySpinner").hidden = true;
      $("#emptyTitle").textContent = "Aucune simulation connectée";
      $("#emptyText").textContent = "Cette interface n'invente aucune donnée. Pour afficher l'esplanade, démarrez le serveur WebSocket de MARÉE :";
      $("#emptyCommands").hidden = false;
    }
  }
  updateInterveneState();
}

function handleFrame(msg) {
  switch (msg.type) {
    case "hello":
      state.runId = msg.run_id || null;
      state.plan = msg.plan || null;
      state.live = Boolean(msg.live);
      if (state.plan?.smoke) state.smokeEvent = state.plan.smoke;
      $("#runTitle").textContent = state.runId
        ? `Port-Aubel · run « ${state.runId} »`
        : "Évacuation de l'esplanade de Port-Aubel";
      setConnectionState(state.live ? "live" : "replay");
      populateExitSelect();
      renderLegend();
      break;

    case "world":
      if (state.firstDangerTick == null) state.firstDangerTick = msg.tick ?? 0;
      if (msg.kind === "smoke") {
        state.smokeEvent = { position: msg.position, radius: msg.radius, tick: msg.tick };
        state.worldMarkers.push({ tick: msg.tick ?? 0, kind: "smoke", label: "Fumée" });
        pushFeed(msg.tick, "danger", "Alerte", "De la fumée apparaît près de la scène.");
        announcePolite("Alerte : de la fumée apparaît près de la scène.");
      } else if (msg.kind === "announcement") {
        state.announcement = msg.text;
        state.worldMarkers.push({ tick: msg.tick ?? 0, kind: "announcement", label: "Annonce" });
        $("#announcementText").textContent = msg.text || "";
        $("#announcementBanner").hidden = !msg.text;
        pushFeed(msg.tick, "world", "Annonce", `Haut-parleurs : « ${msg.text} »`);
        announcePolite(`Annonce officielle : ${msg.text}`);
      } else if (msg.kind === "exit_closed") {
        state.worldMarkers.push({ tick: msg.tick ?? 0, kind: "exit_closed", label: `Sortie ${msg.exit} fermée` });
        pushFeed(msg.tick, "danger", "Sortie fermée", `La sortie ${msg.exit} vient de fermer.`);
        announcePolite(`La sortie ${msg.exit} vient de fermer.`);
      }
      break;

    case "decision": {
      const list = state.decisionsByAgent.get(msg.agent_id) || [];
      list.unshift(msg);
      state.decisionsByAgent.set(msg.agent_id, list.slice(0, 12));
      const intent = msg.intention?.kind;
      if (msg.trigger && msg.trigger !== "periodique" && msg.trigger !== "premiere_decision") {
        const target = msg.intention?.target ? ` (${msg.intention.target})` : "";
        pushFeed(
          msg.tick,
          "decision",
          "Décision",
          `${msg.agent_id} : ${INTENTION_LABELS[intent] || intent || "agit"}${target} — « ${msg.reason || ""} »`,
          msg.agent_id
        );
      }
      break;
    }

    case "message":
      for (const to of msg.to || []) {
        state.packets.push({ from: msg.from, to, created: performance.now() });
      }
      pushFeed(
        msg.tick,
        "talk",
        "Parole",
        `${msg.from} dit à ${(msg.to || []).length} personne(s) : « ${msg.content} »`,
        msg.from
      );
      startPacketLoop();
      break;

    case "heard": {
      const list = state.heardByAgent.get(msg.agent_id) || [];
      list.unshift(msg);
      state.heardByAgent.set(msg.agent_id, list.slice(0, 10));
      break;
    }

    case "incident":
      pushFeed(msg.tick, "danger", "Incident", `${msg.agent_id} : repli sur les règles (${msg.cause}).`, msg.agent_id);
      break;

    case "narrative":
      if (msg.text) pushFeed(msg.tick, "world", "Récit", msg.text);
      break;

    case "snapshot":
      state.snapshot = msg;
      if (msg.tick != null) state.snapshotsByTick.set(msg.tick, msg);
      $("#mapEmpty").hidden = true;
      recordTrails(msg.agents || []);
      recordTimelinePoint(msg);
      renderAll();
      break;

    case "indicators":
      state.indicators = msg;
      if (msg.tick != null) state.indicatorsByTick.set(msg.tick, msg);
      renderIndicators();
      renderKpis();
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

    case "end": {
      setConnectionState("ended");
      pushFeed(msg.tick, "end", "Fin", `Run terminé : ${msg.evacuated ?? "—"} / ${msg.total ?? "—"} personnes sorties en ${msg.ticks ?? "—"} ticks.`);
      const activeAtEnd = (state.snapshot?.agents || []).filter((a) => !a.evacuated).length;
      if (!state.live && activeAtEnd === 0 && state.snapshotsByTick.size) {
        const pivot = state.firstDangerTick != null ? state.firstDangerTick + 3 : Math.floor(state.snapshotsByTick.size / 2);
        const snap = state.snapshotsByTick.get(pivot) || [...state.snapshotsByTick.values()].find((s) => (s.agents || []).some((a) => !a.evacuated));
        if (snap) {
          state.snapshot = snap;
          if (state.indicatorsByTick.has(snap.tick)) state.indicators = state.indicatorsByTick.get(snap.tick);
        }
      }
      renderAll();
      break;
    }
  }
}

function recordTrails(agents) {
  for (const a of agents) {
    if (!a.pos || a.evacuated) continue;
    const trail = state.trails.get(a.id) || [];
    const last = trail[trail.length - 1];
    if (!last || Math.hypot(last[0] - a.pos[0], last[1] - a.pos[1]) > 0.05) {
      trail.push([a.pos[0], a.pos[1]]);
      if (trail.length > 40) trail.shift();
      state.trails.set(a.id, trail);
    }
  }
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

function renderAll() {
  renderClock();
  renderKpis();
  renderLegend();
  renderPerson();
  renderIndicators();
  renderTimeline();
  drawMap();
  if ($("#findDialog").open) renderFindList($("#findInput").value);
}

function renderClock() {
  const snap = state.snapshot;
  if (!snap) return;
  const seconds = (snap.tick ?? 0) * 10;
  const mins = Math.floor(seconds / 60);
  const secs = String(seconds % 60).padStart(2, "0");
  $("#simClock").textContent = snap.sim_time || `${mins}:${secs}`;
  $("#simTick").textContent = `· tick ${snap.tick ?? 0}`;
}

function renderKpis() {
  const snap = state.snapshot;
  if (!snap) return;
  const total = snap.agents?.length ?? 0;
  const evacuated = (snap.agents || []).filter((a) => a.evacuated).length;
  const remaining = total - evacuated;
  const pct = total ? Math.round((evacuated / total) * 100) : 0;

  $("#kpiEvacuated").textContent = `${evacuated} sur ${total}`;
  $("#kpiRemaining").textContent = String(remaining);
  const bar = $("#kpiProgress");
  bar.setAttribute("aria-valuenow", String(pct));
  bar.querySelector("i").style.width = `${pct}%`;

  const delay = state.indicators?.I7_delay_seconds;
  if (delay != null && delay > 0) {
    $("#kpiAlert").textContent = `${Math.round(delay)} s`;
  } else if (state.firstDangerTick != null && snap.tick != null && snap.tick >= state.firstDangerTick) {
    $("#kpiAlert").textContent = `${(snap.tick - state.firstDangerTick) * 10} s`;
  } else {
    $("#kpiAlert").textContent = "Calme";
  }
}

function renderLegend() {
  const container = $("#exitLegend");
  if (!state.plan) return;
  const active = (state.snapshot?.agents || []).filter((a) => !a.evacuated);
  const counts = { A: 0, B: 0, C: 0, none: 0 };
  for (const a of active) {
    const key = a.belief && counts[a.belief] != null ? a.belief : "none";
    counts[key] += 1;
  }

  container.replaceChildren();
  const items = [
    ...(state.plan.exits || []).map((ex) => ({
      id: ex.id,
      title: `Sortie ${ex.id}`,
      sub: ex.label || "",
      open: isExitOpen(ex.id),
      count: counts[ex.id] ?? 0,
    })),
    {
      id: "none",
      title: "Sans sortie choisie",
      sub: "Hésite ou observe",
      open: true,
      count: counts.none,
    },
  ];

  for (const item of items) {
    const li = document.createElement("li");
    li.dataset.closed = String(!item.open);
    const shape = document.createElement("span");
    shape.className = `shape shape-${item.id}`;
    shape.setAttribute("aria-hidden", "true");

    const name = document.createElement("div");
    name.className = "legend-name";
    const strong = document.createElement("strong");
    strong.textContent = item.title;
    const sub = document.createElement("span");
    sub.textContent = item.open ? item.sub : `${item.sub} · FERMÉE`;
    if (!item.open) sub.className = "legend-closed";
    name.append(strong, sub);

    const count = document.createElement("span");
    count.className = "legend-count";
    count.title = "Personnes encore sur l'esplanade visant cette option";
    count.textContent = state.snapshot ? String(item.count) : "—";

    li.append(shape, name, count);
    container.append(li);
  }
}

function renderPerson() {
  const agent = (state.snapshot?.agents || []).find((a) => a.id === state.selectedId) || null;
  $("#feedPanel").hidden = Boolean(agent);
  $("#personPanel").hidden = !agent;
  if (!agent) return;

  const beliefKey = agent.belief && EXIT_PALETTE[agent.belief] ? agent.belief : "none";
  const shape = $("#personShape");
  shape.className = `person-shape shape shape-${beliefKey}`;

  $("#personId").textContent = `${agent.id} · ${agent.label || agent.profile || "Personne"}`;
  const modeLabel = agent.kind === "llm" ? "Décide avec un modèle de langage (LLM)" : "Décide selon des règles simples";
  const zone = zoneNameAt(agent.pos);
  $("#personRole").textContent = `${modeLabel}${zone ? ` · ${zone}` : ""}${agent.kin ? ` · Proche de ${agent.kin}` : ""}`;

  // Headline
  const exitLabel = exitLabelFor(agent.belief);
  if (agent.evacuated) {
    $("#personHeadline").textContent = "Est sortie de l'esplanade.";
  } else if (agent.intention === "go_exit" && (agent.intention_target || agent.belief)) {
    const target = agent.intention_target || agent.belief;
    $("#personHeadline").textContent = `Se dirige vers la sortie ${target}${exitLabelFor(target) ? ` (${exitLabelFor(target)})` : ""} — sûre à ${Math.round((agent.confidence ?? 0) * 100)} %.`;
  } else if (agent.intention === "guide" && (agent.intention_target || agent.belief)) {
    const target = agent.intention_target || agent.belief;
    $("#personHeadline").textContent = `Oriente la foule vers la sortie ${target}${exitLabelFor(target) ? ` (${exitLabelFor(target)})` : ""}.`;
  } else {
    const base = INTENTION_LABELS[agent.intention] || agent.intention || "Observe";
    $("#personHeadline").textContent = `${base}${agent.intention_target ? ` (${agent.intention_target})` : ""}${exitLabel ? ` · pense que la sortie ${agent.belief} est la meilleure (${Math.round((agent.confidence ?? 0) * 100)} %)` : ""}.`;
  }

  // Latest decision from stream
  const decisions = state.decisionsByAgent.get(agent.id) || [];
  const latest = decisions[0];
  $("#personReason").textContent = latest?.reason || "Pas encore d'explication enregistrée à ce moment du run.";
  if (latest) {
    const trig = TRIGGER_LABELS[latest.trigger] || latest.trigger || "décision";
    const llmInfo = latest.llm?.model ? ` · modèle ${latest.llm.model}` : "";
    $("#personTrigger").textContent = `À t${latest.tick} (${trig}${llmInfo}).`;
  } else {
    $("#personTrigger").textContent = agent.decided_at != null ? `Dernière réflexion au tick t${agent.decided_at}.` : "";
  }

  // Beliefs bars
  const beliefsWrap = $("#personBeliefs");
  beliefsWrap.replaceChildren();
  for (const ex of state.plan?.exits || [{ id: "A" }, { id: "B" }, { id: "C" }]) {
    const entry = agent.beliefs?.[ex.id];
    const conf = entry?.confidence ?? (agent.belief === ex.id ? agent.confidence ?? 0 : 0);
    const pct = Math.round(clamp(conf, 0, 1) * 100);
    const row = document.createElement("div");
    row.className = "belief-row";
    const icon = document.createElement("span");
    icon.className = `shape shape-${ex.id}`;
    icon.setAttribute("aria-hidden", "true");
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("i");
    fill.style.width = `${pct}%`;
    fill.style.background = EXIT_PALETTE[ex.id]?.fill || "#52525b";
    bar.append(fill);
    const val = document.createElement("strong");
    val.textContent = `${pct} %`;
    const sub = document.createElement("small");
    sub.textContent = `Sortie ${ex.id}${ex.label ? ` (${ex.label})` : ""}${entry?.source ? ` · ${formatBeliefSource(entry.source)}` : " · non connue ou écartée"}`;
    row.append(icon, bar, val, sub);
    beliefsWrap.append(row);
  }

  // Perceived signals
  const perceivedWrap = $("#personPerceived");
  perceivedWrap.replaceChildren();
  const signals = agent.perceived || [];
  if (!signals.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Aucun signal de danger perçu pour l'instant";
    perceivedWrap.append(li);
  } else {
    for (const sig of signals) {
      const li = document.createElement("li");
      li.textContent = formatPerceived(sig);
      perceivedWrap.append(li);
    }
  }

  // Heard messages
  const heardWrap = $("#personHeard");
  heardWrap.replaceChildren();
  const heard = state.heardByAgent.get(agent.id) || [];
  if (!heard.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Personne ne lui a encore parlé.";
    heardWrap.append(li);
  } else {
    for (const h of heard.slice(0, 5)) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="when">t${h.tick} · de ${escapeHtml(h.from)}</span><span>« ${escapeHtml(h.content)} »</span>`;
      heardWrap.append(li);
    }
  }

  // Decision history
  const histWrap = $("#personHistory");
  histWrap.replaceChildren();
  if (!decisions.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Aucune décision reçue depuis l'ouverture de la page.";
    histWrap.append(li);
  } else {
    for (const d of decisions) {
      const li = document.createElement("li");
      const kind = d.intention?.kind;
      const target = d.intention?.target ? ` → ${d.intention.target}` : "";
      li.innerHTML = `<span class="when">t${d.tick} · ${escapeHtml(TRIGGER_LABELS[d.trigger] || d.trigger || "")}</span><strong>${escapeHtml(INTENTION_LABELS[kind] || kind || "")}${escapeHtml(target)}</strong><span>${escapeHtml(d.reason || "")}</span>`;
      histWrap.append(li);
    }
  }

  // Retrieved RAG passages
  const docsWrap = $("#personDocs");
  docsWrap.replaceChildren();
  const retrieved = latest?.retrieved || [];
  if (!retrieved.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = agent.kind === "llm"
      ? "Aucun extrait documentaire mobilisé sur la dernière décision."
      : "Cette personne suit des règles simples et n'interroge pas le corpus documentaire.";
    docsWrap.append(li);
  } else {
    for (const doc of retrieved) {
      const li = document.createElement("li");
      const title = document.createElement("strong");
      const score = doc.score != null ? ` · score ${doc.score.toFixed(2).replace(".", ",")}` : "";
      title.textContent = `${doc.doc_id || doc.id || "Document"}${score}`;
      const text = document.createElement("span");
      text.textContent = doc.text || doc.content || "";
      li.append(title, text);
      docsWrap.append(li);
    }
  }
}

function renderIndicators() {
  const list = $("#indicatorList");
  if (!list.children.length) {
    for (const meta of INDICATORS_META) {
      const li = document.createElement("li");
      li.dataset.key = meta.key;
      li.innerHTML = `
        <div class="ind-name"><span>${meta.code}</span>${meta.name}</div>
        <div class="ind-value" data-val="${meta.key}">—</div>
        <p>${meta.explain}</p>
        <button type="button" data-trace="${meta.key}">D'où vient ce chiffre ?</button>
      `;
      li.querySelector("button").addEventListener("click", () => openTrace(meta.key));
      list.append(li);
    }
  }
  for (const meta of INDICATORS_META) {
    const el = list.querySelector(`[data-val="${meta.key}"]`);
    if (el) el.textContent = meta.format(state.indicators?.[meta.key]);
  }
}

function openTrace(key) {
  const meta = INDICATORS_META.find((m) => m.key === key) || INDICATORS_META[0];
  $("#traceTitle").textContent = `${meta.code} · ${meta.name}`;
  $("#traceDefinition").textContent = meta.explain;
  $("#traceMethod").innerHTML = `
    <div><dt>Formule</dt><dd>${escapeHtml(meta.formula)}</dd></div>
    <div><dt>Fenêtre</dt><dd>${escapeHtml(meta.window)}</dd></div>
    <div><dt>Unité</dt><dd>${escapeHtml(meta.unit)}</dd></div>
    <div><dt>Source</dt><dd>${escapeHtml(meta.source)}</dd></div>
  `;
  const body = $("#traceBody");
  body.textContent = "Interrogation du journal auprès du serveur…";
  $("#traceDialog").showModal();

  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify({ type: "trace", indicator: key }));
    return;
  }
  try {
    const helper = new WebSocket(wsEndpoint());
    helper.addEventListener("open", () => {
      helper.send(JSON.stringify({ type: "trace", indicator: key }));
    });
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

/* ---------- Timeline SVG ---------- */
function renderTimeline() {
  const svg = $("#timelineSvg");
  const series = state.timelineSeries;
  const width = svg.clientWidth || 680;
  const height = 150;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.replaceChildren();

  if (!series.length) {
    $("#timelineDesc").textContent = "Aucune donnée de chronologie pour l'instant.";
    return;
  }

  const padL = 38;
  const padR = 18;
  const padT = 22;
  const padB = 26;
  const plotW = Math.max(100, width - padL - padR);
  const plotH = height - padT - padB;

  const maxTick = Math.max(20, ...series.map((p) => p.tick), ...state.worldMarkers.map((m) => m.tick));
  const total = series[0]?.total || 60;
  const xOf = (t) => padL + (t / maxTick) * plotW;
  const yOf = (v) => padT + plotH - (v / total) * plotH;

  // Horizontal grid + labels (0, half, total)
  for (const val of [0, Math.round(total / 2), total]) {
    const y = yOf(val);
    const line = svgEl("line", { x1: padL, y1: y, x2: padL + plotW, y2: y, class: val === 0 ? "axis" : "grid" });
    const txt = svgEl("text", { x: padL - 8, y: y + 4, "text-anchor": "end" });
    txt.textContent = String(val);
    svg.append(line, txt);
  }

  // Tick labels along X
  const step = maxTick <= 25 ? 5 : maxTick <= 60 ? 10 : 15;
  for (let t = 0; t <= maxTick; t += step) {
    const x = xOf(t);
    const txt = svgEl("text", { x, y: height - 6, "text-anchor": "middle" });
    txt.textContent = `t${t}`;
    svg.append(txt);
  }

  // Area + curve
  const sorted = [...series].sort((a, b) => a.tick - b.tick);
  const pts = sorted.map((p) => `${xOf(p.tick).toFixed(1)},${yOf(p.evacuated).toFixed(1)}`).join(" ");
  const firstX = xOf(sorted[0].tick).toFixed(1);
  const lastX = xOf(sorted[sorted.length - 1].tick).toFixed(1);
  const baseY = yOf(0).toFixed(1);
  svg.append(
    svgEl("polygon", { points: `${firstX},${baseY} ${pts} ${lastX},${baseY}`, class: "area" }),
    svgEl("polyline", { points: pts, class: "curve" })
  );

  // World event markers
  for (const m of state.worldMarkers) {
    const x = xOf(m.tick);
    const g = svgEl("g", { class: `marker ${m.kind}` });
    g.append(svgEl("line", { x1: x, y1: padT, x2: x, y2: padT + plotH }));
    const label = svgEl("text", { x: clamp(x + 4, padL + 4, padL + plotW - 60), y: padT - 6 });
    label.textContent = `t${m.tick} · ${m.label}`;
    g.append(label);
    svg.append(g);
  }

  // Current tick cursor
  if (state.snapshot?.tick != null) {
    const cx = xOf(state.snapshot.tick);
    svg.append(svgEl("line", { x1: cx, y1: padT, x2: cx, y2: padT + plotH, class: "now" }));
  }

  svg.onclick = (ev) => {
    if (!state.snapshotsByTick.size) return;
    const rect = svg.getBoundingClientRect();
    const ratio = clamp((ev.clientX - rect.left - padL) / plotW, 0, 1);
    const targetTick = Math.round(ratio * maxTick);
    let bestTick = null;
    let bestDiff = Infinity;
    for (const k of state.snapshotsByTick.keys()) {
      const d = Math.abs(k - targetTick);
      if (d < bestDiff) { bestDiff = d; bestTick = k; }
    }
    if (bestTick != null) {
      state.snapshot = state.snapshotsByTick.get(bestTick);
      if (state.indicatorsByTick.has(bestTick)) state.indicators = state.indicatorsByTick.get(bestTick);
      renderAll();
    }
  };

  const last = sorted[sorted.length - 1];
  $("#timelineDesc").textContent = `Au tick t${last.tick}, ${last.evacuated} personnes sur ${total} sont sorties.`;
}

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

/* ---------- Map canvas ---------- */
function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  box = { width: rect.width, height: rect.height, dpr };
  drawMap();
  renderTimeline();
}

function drawMap() {
  if (!box.width || !state.plan || !state.snapshot) return;
  const { width, height, dpr } = box;
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#111113";
  ctx.fillRect(0, 0, width, height);

  const margin = 34;
  const scale = Math.min((width - margin * 2) / state.plan.width, (height - margin * 2) / state.plan.height) * state.zoom;
  view = {
    scale,
    x: (width - state.plan.width * scale) / 2,
    y: (height - state.plan.height * scale) / 2,
  };

  drawWalkable();
  if (state.layers.zones) drawZones();
  if (state.layers.density) drawDensity();
  drawObstacles();
  if (state.layers.smoke) drawSmoke();
  drawExits();
  if (state.layers.trail) drawSelectedTrail();
  if (state.layers.messages) drawPackets();
  drawAgents();
  ctx.restore();
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

function drawWalkable() {
  const poly = (state.plan.walkable || [[0, 0], [state.plan.width, 0], [state.plan.width, state.plan.height], [0, state.plan.height]]).map(toScreen);
  ctx.beginPath();
  poly.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  ctx.closePath();
  ctx.fillStyle = "#18181b";
  ctx.fill();
  ctx.strokeStyle = "#3f3f46";
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // 10m grid
  ctx.strokeStyle = "rgba(255,255,255,0.04)";
  ctx.lineWidth = 1;
  for (let x = 10; x < state.plan.width; x += 10) {
    const a = toScreen([x, 0]);
    const b = toScreen([x, state.plan.height]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  for (let y = 10; y < state.plan.height; y += 10) {
    const a = toScreen([0, y]);
    const b = toScreen([state.plan.width, y]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
}

function drawZones() {
  ctx.font = "500 12px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const z of state.plan.zones || []) {
    if (z.hidden || !z.polygon?.length) continue;
    const pts = z.polygon.map(toScreen);
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.closePath();
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.stroke();
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    ctx.fillStyle = "rgba(228,228,231,0.38)";
    ctx.fillText(z.label || z.id, cx, cy);
  }
  ctx.textAlign = "start";
}

function drawDensity() {
  for (const cell of state.snapshot.density_grid || []) {
    if ((cell.n ?? 0) < 2) continue;
    const p = toScreen([cell.x, cell.y + 1]);
    const alpha = Math.min(0.12 * cell.n, 0.45);
    ctx.fillStyle = `rgba(251, 146, 60, ${alpha})`;
    ctx.fillRect(p.x, p.y, view.scale, view.scale);
  }
}

function drawObstacles() {
  ctx.font = "600 11px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const ob of state.plan.obstacles || []) {
    if (!ob.polygon?.length) continue;
    const pts = ob.polygon.map(toScreen);
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.closePath();
    ctx.fillStyle = "#27272a";
    ctx.fill();
    ctx.strokeStyle = "#52525b";
    ctx.lineWidth = 1;
    ctx.stroke();
    if (ob.kind === "scene" || ob.kind === "tour" || ob.kind === "fontaine") {
      const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
      const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
      ctx.fillStyle = "#d4d4d8";
      ctx.fillText((ob.label || ob.id || "").toUpperCase(), cx, cy);
    }
  }
  ctx.textAlign = "start";
}

function drawSmoke() {
  if (!state.snapshot.smoke_active || !state.smokeEvent?.position) return;
  const center = toScreen(state.smokeEvent.position);
  const r = (state.smokeEvent.radius || 12) * view.scale;
  const grad = ctx.createRadialGradient(center.x, center.y, r * 0.08, center.x, center.y, r);
  grad.addColorStop(0, "rgba(228, 228, 231, 0.34)");
  grad.addColorStop(1, "rgba(161, 161, 170, 0.03)");
  ctx.fillStyle = grad;
  ctx.beginPath(); ctx.arc(center.x, center.y, r, 0, Math.PI * 2); ctx.fill();

  ctx.setLineDash([5, 5]);
  ctx.strokeStyle = "rgba(244, 244, 245, 0.35)";
  ctx.lineWidth = 1.25;
  ctx.beginPath(); ctx.arc(center.x, center.y, r, 0, Math.PI * 2); ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "#fafafa";
  ctx.font = "600 12px Inter, sans-serif";
  ctx.fillText("FUMÉE", center.x - 22, center.y + 4);
}

function drawExits() {
  ctx.font = "700 13px Inter, sans-serif";
  for (const ex of state.plan.exits || []) {
    const a = toScreen(ex.a);
    const b = toScreen(ex.b);
    const open = isExitOpen(ex.id);
    const col = open ? (EXIT_PALETTE[ex.id]?.fill || "#fafafa") : "#ef4444";

    ctx.strokeStyle = col;
    ctx.lineWidth = 8;
    ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();

    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const text = `${EXIT_PALETTE[ex.id]?.symbol || ""} Sortie ${ex.id}${ex.label ? ` · ${ex.label}` : ""}${open ? "" : " (FERMÉE)"}`.trim();
    const tw = ctx.measureText(text).width + 16;
    const lx = clamp(mx - tw / 2, 6, box.width - tw - 6);
    const ly = my < box.height / 2 ? Math.max(6, my - 30) : Math.min(box.height - 28, my + 10);

    ctx.fillStyle = "rgba(24, 24, 27, 0.92)";
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.5;
    roundRect(ctx, lx, ly, tw, 24, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#fafafa";
    ctx.fillText(text, lx + 8, ly + 16);
  }
}

function drawSelectedTrail() {
  if (!state.selectedId) return;
  const trail = state.trails.get(state.selectedId) || [];
  if (trail.length < 2) return;
  ctx.beginPath();
  trail.forEach((pt, i) => {
    const p = toScreen(pt);
    if (i) ctx.lineTo(p.x, p.y);
    else ctx.moveTo(p.x, p.y);
  });
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = "#a5b4fc";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawPackets() {
  const byId = new Map((state.snapshot.agents || []).map((a) => [a.id, a]));
  const now = performance.now();
  for (const pkt of state.packets) {
    const from = byId.get(pkt.from);
    const to = byId.get(pkt.to);
    if (!from?.pos || !to?.pos || from.evacuated || to.evacuated) continue;
    const a = toScreen(from.pos);
    const b = toScreen(to.pos);
    const t = clamp((now - pkt.created) / 1600, 0, 1);
    ctx.strokeStyle = "rgba(165, 180, 252, 0.55)";
    ctx.lineWidth = 1.25;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#e0e7ff";
    ctx.beginPath();
    ctx.arc(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawAgents() {
  const active = (state.snapshot.agents || []).filter((a) => !a.evacuated && a.pos);
  if (!active.length && (state.snapshot.agents || []).length) {
    const c = toScreen([state.plan.width / 2, state.plan.height / 2]);
    const msg = "Évacuation terminée — cliquez sur la courbe « Déroulé » pour revoir un tick";
    ctx.font = "600 13px Inter, sans-serif";
    const w = ctx.measureText(msg).width + 28;
    ctx.fillStyle = "rgba(24, 24, 27, 0.92)";
    ctx.strokeStyle = "#52525b";
    ctx.lineWidth = 1.5;
    roundRect(ctx, c.x - w / 2, c.y - 20, w, 40, 8);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#fafafa";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(msg, c.x, c.y);
    ctx.textAlign = "start";
    return;
  }
  const r = clamp(view.scale * 0.36, 5.5, 8.5);
  for (const a of active) {
    const p = toScreen(a.pos);
    const key = a.belief && EXIT_PALETTE[a.belief] ? a.belief : "none";
    const pal = EXIT_PALETTE[key];
    const dimmed = state.selectedId && state.selectedId !== a.id;

    ctx.globalAlpha = dimmed ? 0.35 : 1;
    ctx.fillStyle = pal.fill;
    ctx.strokeStyle = "#111113";
    ctx.lineWidth = 1.5;

    ctx.beginPath();
    if (pal.shape === "square") {
      ctx.rect(p.x - r * 0.85, p.y - r * 0.85, r * 1.7, r * 1.7);
    } else if (pal.shape === "triangle") {
      ctx.moveTo(p.x, p.y - r * 1.1);
      ctx.lineTo(p.x + r * 1.05, p.y + r * 0.9);
      ctx.lineTo(p.x - r * 1.05, p.y + r * 0.9);
      ctx.closePath();
    } else if (pal.shape === "diamond") {
      ctx.moveTo(p.x, p.y - r * 1.05);
      ctx.lineTo(p.x + r * 1.05, p.y);
      ctx.lineTo(p.x, p.y + r * 1.05);
      ctx.lineTo(p.x - r * 1.05, p.y);
      ctx.closePath();
    } else {
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    }
    ctx.fill();
    ctx.stroke();

    // Red ring if believing in a closed exit
    if (a.belief && !isExitOpen(a.belief)) {
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 4, 0, Math.PI * 2); ctx.stroke();
    }

    // White halo + label for the selected person
    if (a.id === state.selectedId) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 6, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = "700 12px Inter, sans-serif";
      ctx.fillText(a.id, p.x + r + 8, p.y + 4);
    }
    ctx.globalAlpha = 1;
  }
}

function startPacketLoop() {
  if (animFrame) return;
  const tick = () => {
    state.packets = state.packets.filter((p) => performance.now() - p.created < 1600);
    drawMap();
    animFrame = state.packets.length ? requestAnimationFrame(tick) : null;
  };
  animFrame = requestAnimationFrame(tick);
}

/* ---------- Feed ---------- */
function pushFeed(tick, kind, tag, text, agentId = null) {
  const feed = $("#feed");
  $("#feedEmpty").hidden = true;
  const li = document.createElement("li");
  li.dataset.kind = kind;

  const time = document.createElement("time");
  time.textContent = tick != null ? `t${tick}` : "—";

  const body = document.createElement("div");
  body.className = "feed-text";
  const badge = document.createElement("span");
  badge.className = "tag";
  badge.textContent = tag;

  const line = document.createElement("span");
  if (agentId && text.startsWith(agentId)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "agent-link";
    btn.textContent = agentId;
    btn.addEventListener("click", () => selectPerson(agentId, true));
    line.append(btn, document.createTextNode(text.slice(agentId.length)));
  } else {
    line.textContent = text;
  }

  body.append(badge, line);
  li.append(time, body);
  feed.prepend(li);
  while (feed.children.length > 40) feed.lastElementChild.remove();
}

/* ---------- Selection & Directory ---------- */
function selectPerson(id, focusHeading = false) {
  state.selectedId = id;
  renderPerson();
  drawMap();
  if (id && focusHeading) {
    $("#personId").focus();
  }
}

function renderFindList(query = "") {
  const list = $("#findList");
  list.replaceChildren();
  const q = query.trim().toLowerCase();
  const agents = (state.snapshot?.agents || []).filter((a) => {
    const hay = `${a.id} ${a.label || ""} ${a.profile || ""} ${a.belief ? `sortie ${a.belief}` : "sans sortie"} ${a.evacuated ? "sortie évacuée" : "présente"}`.toLowerCase();
    return hay.includes(q);
  });

  $("#findCount").textContent = `${agents.length} personne(s) affichée(s).`;

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
    btn.innerHTML = `
      <span class="shape shape-${key}" aria-hidden="true"></span>
      <strong>${escapeHtml(a.id)}</strong>
      <small>${escapeHtml(a.label || a.profile || "Personne")} · ${escapeHtml(status)}</small>
    `;
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
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function announcePolite(text) { $("#announcer").textContent = text; }

/* ---------- Event wiring ---------- */
canvas.addEventListener("click", (ev) => {
  if (!state.snapshot || !state.plan) return;
  const rect = canvas.getBoundingClientRect();
  const pt = { x: ev.clientX - rect.left, y: ev.clientY - rect.top };

  if (state.placingSmoke) {
    const [wx, wy] = toWorld(pt);
    state.placingSmoke = false;
    $("#mapWrap").dataset.placing = "false";
    $("#smokeHint").hidden = true;
    sendInjection({ kind: "smoke", position: [Math.round(wx * 10) / 10, Math.round(wy * 10) / 10], radius: 15 });
    return;
  }

  let best = null;
  let bestDist = 24;
  for (const a of state.snapshot.agents || []) {
    if (a.evacuated || !a.pos) continue;
    const p = toScreen(a.pos);
    const d = Math.hypot(pt.x - p.x, pt.y - p.y);
    if (d < bestDist) { best = a; bestDist = d; }
  }
  selectPerson(best ? best.id : null, Boolean(best));
});

canvas.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    renderFindList($("#findInput").value);
    $("#findDialog").showModal();
    return;
  }
  if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(ev.key)) return;
  ev.preventDefault();
  const active = (state.snapshot?.agents || []).filter((a) => !a.evacuated);
  if (!active.length) return;
  const idx = Math.max(0, active.findIndex((a) => a.id === state.selectedId));
  const step = ev.key === "ArrowRight" || ev.key === "ArrowDown" ? 1 : -1;
  const next = active[(idx + step + active.length) % active.length];
  selectPerson(next.id);
});

window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && state.placingSmoke) {
    state.placingSmoke = false;
    $("#mapWrap").dataset.placing = "false";
    $("#smokeHint").hidden = true;
  }
});

$("#backButton").addEventListener("click", () => selectPerson(null));
$("#retryButton").addEventListener("click", () => connect());
$("#replayButton").addEventListener("click", () => connect());

$("#pauseButton").addEventListener("click", () => {
  state.paused = !state.paused;
  $("#pauseButton").setAttribute("aria-pressed", String(state.paused));
  $("#pauseLabel").textContent = state.paused ? "Reprendre" : "Figer";
  $("#pauseIconPath").setAttribute("d", state.paused ? "m8 5 11 7-11 7z" : "M8 5v14M16 5v14");
  if (!state.paused && state.pauseQueue.length) {
    const queued = state.pauseQueue.splice(0);
    for (const m of queued) handleFrame(m);
  }
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
  $("#mapWrap").dataset.placing = "true";
  $("#smokeHint").hidden = false;
});

$("#helpButton").addEventListener("click", () => $("#helpDialog").showModal());

$("#zoomInButton").addEventListener("click", () => { state.zoom = clamp(state.zoom + 0.25, 0.75, 2.5); drawMap(); });
$("#zoomOutButton").addEventListener("click", () => { state.zoom = clamp(state.zoom - 0.25, 0.75, 2.5); drawMap(); });
$("#zoomResetButton").addEventListener("click", () => { state.zoom = 1; drawMap(); });

$("#layersButton").addEventListener("click", (ev) => {
  const menu = $("#layersMenu");
  const open = menu.hidden;
  menu.hidden = !open;
  ev.currentTarget.setAttribute("aria-expanded", String(open));
});
$$("[data-layer]").forEach((input) => {
  input.addEventListener("change", () => {
    state.layers[input.dataset.layer] = input.checked;
    drawMap();
  });
});

new ResizeObserver(resizeCanvas).observe(canvas);
renderIndicators();
connect();
