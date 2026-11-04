extends Node2D
## Observatoire Godot 4 de MARÉE (données réelles via WebSocket).
##
## Même système que web/styles.css, « salle de crise » :
##   * tout est sombre, la carte est la seule source de lumière ;
##   * neutres zinc, un accent indigo, rouge réservé au danger ;
##   * sorties codées par couleur Okabe-Ito ET par forme
##     (● A bleu, ■ B ambre, ▲ C mauve, ◆ incertain gris) ;
##   * Inter embarquée, cartes arrondies, ombres douces ;
##   * à droite les chiffres clés puis le fil ou la fiche d'une personne,
##     dessous le déroulé cliquable et les indicateurs I1–I7.
##
## L'interpolation entre deux ticks et les effets sont de l'affichage : aucun
## chiffre n'en dépend, tout découle de l'instantané affiché (`_snap`).

const GAP := 12.0
const TOP_H := 60.0
const RAIL_W := 392.0
const DECK_H := 172.0
const HEAD_H := 60.0
const HERO_H := 122.0
const RADIUS := 14
const TICK_SECONDS := 10
const TALK_LIFE := 1.3
const FEED_LIMIT := 60

# --- Palette : miroir de web/styles.css --------------------------------
const BG_SHELL := Color("#0c0d11")
const SURFACE := Color("#14151a")
const SURFACE_2 := Color("#1c1d24")
const SURFACE_3 := Color("#272831")
const LINE := Color(1, 1, 1, 0.075)
const LINE_STRONG := Color(1, 1, 1, 0.16)
const TEXT := Color("#f4f4f5")
const MUTED := Color("#a9a9b4")
const SUBTLE := Color("#8e8e9a")
const ACCENT := Color("#9ea5fb")
const ACCENT_SOLID := Color("#4338ca")
const ACCENT_HOVER := Color("#4f46e5")
const ACCENT_SOFT := Color(0.506, 0.549, 0.973, 0.14)
const DANGER := Color("#fb8a8a")
const DANGER_LINE := Color("#ef4444")
const DANGER_SOFT := Color(0.973, 0.443, 0.443, 0.14)
const WARN := Color("#fcd34d")
const WARN_SOFT := Color(0.902, 0.624, 0.0, 0.12)

const MAP_BG := Color("#08090c")
const WALL := Color("#4a4c59")

const BELIEF_COLORS := {
	"A": Color("#56b4e9"), # ● Grand Quai
	"B": Color("#e69f00"), # ■ Ruelle des Cordiers
	"C": Color("#cc79a7"), # ▲ Passage des Halles
}
const UNKNOWN := Color("#a1a1aa")

# Sans objet quand il n'y a plus personne : le dernier tick vaut 0 par
# construction (voir AGENTS.md, « tick dégénéré »).
const UNDEFINED_WHEN_EMPTY := ["I1_consensus", "I2_entropy", "I5_max_density", "I6_belief_gap"]

const INTENTION_LABELS := {
	"stay": "Reste sur place",
	"go_exit": "Se dirige vers la sortie",
	"go_zone": "Rejoint la zone",
	"search": "Cherche un repère ou un proche",
	"guide": "Guide la foule vers la sortie",
	"follow": "Suit",
}

const TRIGGER_LABELS := {
	"premiere_decision": "première observation",
	"periodique": "point régulier",
	"fumee_visible": "voit la fumée",
	"annonce": "entend l'annonce",
	"sortie_fermee": "sortie fermée",
	"proche_disparu": "proche hors de vue",
	"message_recu": "prévenu par un voisin",
}

var _ws := WebSocketPeer.new()
var _trace_ws := WebSocketPeer.new()
var _trace_pending_key := ""
var _ws_url := "ws://127.0.0.1:8765"
var _reconnect_at := -1.0
var _run_id := ""
var _plan: Dictionary = {}
var _snap: Dictionary = {}
var _latest: Dictionary = {}
var _ind: Dictionary = {}
var _snapshots_by_tick: Dictionary = {}
var _indicators_by_tick: Dictionary = {}
var _decisions_by_agent: Dictionary = {}
var _heard_by_agent: Dictionary = {}
var _packets: Array = []
var _ripples: Array = []
var _ghosts: Array = []
var _bursts: Array = []
var _timeline: Array = []
var _world_markers: Array = []
var _feed: Array = []
var _end: Dictionary = {}
var _end_dismissed := false
var _selected := ""
var _status := "connexion…"
var _paused := false
var _first_danger_tick := -1
var _font: Font
var _font_b: Font
var _theme: Theme
var _box_style := StyleBoxFlat.new()
var _glow: Texture2D
var _paving: Texture2D
var _px := 11.0
var _off := Vector2.ZERO
var _bounds := Rect2(0, 0, 60, 40)
var _map_rect := Rect2()
var _timeline_rect := Rect2()
var _timeline_max := 20
var _rail_scroll := 0.0
var _rail_content := 0.0
var _rail_rect := Rect2()

# Interpolation d'affichage entre deux instantanés.
var _tween_from: Dictionary = {}
var _tween_start := 0.0
var _tween_dur := 0.0
var _snap_interval := 0.7
var _last_snap_at := 0.0
var _smoke_born := -100.0
var _flash_at := -100.0
var _flash_color := DANGER_LINE
var _toast := ""
var _toast_at := -100.0
var _toast_color := DANGER

# --- D3 : état d'injection (noms conservés pour test_client.gd) -------
var _live := false
var _world_smoke: Dictionary = {}
var _announcement := ""
var _announcement_at := -100000.0
var _notes: Array[String] = []
var _last_click_m := Vector2(-1.0, -1.0)
var _announce_edit: LineEdit
var _exit_pick: OptionButton
var _buttons: Array[Button] = []
var _hint: Label
var _panel: PanelContainer
var _toggle: Button
var _pause_btn: Button
var _replay_btn: Button
var _clear_sel_btn: Button
var _last_note := ""

var _screenshot_path := ""
var _screenshot_at := -1.0
var _screenshot_done := false
var _screenshot_tick := -1
var _preselect := ""
var _debug := false
var _debug_at := -1.0

# --- F6 : zones cliquables des indicateurs I1–I7 ----------------------
var _ind_boxes: Array = []
var _trace: Dictionary = {}
var _close_trace_rect := Rect2()


func _ready() -> void:
	_load_fonts()
	_glow = _make_glow()
	_build_theme()
	_build_inject_ui()
	_screenshot_path = OS.get_environment("MAREE_SCREENSHOT")
	_preselect = OS.get_environment("MAREE_SELECT")
	_debug = OS.get_environment("MAREE_DEBUG") == "1"
	var shot_tick := OS.get_environment("MAREE_SCREENSHOT_TICK")
	if not shot_tick.is_empty():
		_screenshot_tick = int(shot_tick)
	_ws.inbound_buffer_size = 8 * 1024 * 1024
	_ws.outbound_buffer_size = 1 * 1024 * 1024
	_trace_ws.inbound_buffer_size = 2 * 1024 * 1024
	var url := OS.get_environment("MAREE_WS_URL")
	if not url.is_empty():
		_ws_url = url
	_connect_ws()


func _load_fonts() -> void:
	# Chargée à l'exécution : pas de dépendance à l'import de l'éditeur, le
	# client tourne avec `godot --path` sur un dépôt fraîchement cloné.
	var file := FontFile.new()
	if file.load_dynamic_font("res://fonts/InterVariable.ttf") != OK:
		_font = ThemeDB.fallback_font
		_font_b = ThemeDB.fallback_font
		return
	var regular := FontVariation.new()
	regular.base_font = file
	regular.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): 450}
	var bold := FontVariation.new()
	bold.base_font = file
	bold.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): 650}
	_font = regular
	_font_b = bold


func _make_glow() -> Texture2D:
	var gradient := Gradient.new()
	gradient.set_color(0, Color(1, 1, 1, 1))
	gradient.set_color(1, Color(1, 1, 1, 0))
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.width = 128
	texture.height = 128
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	return texture


func _flat(bg: Color, border: Color, radius: int = 10, margin_x: int = 14) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = margin_x
	style.content_margin_right = margin_x
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	style.anti_aliasing = true
	return style


func _build_theme() -> void:
	_theme = Theme.new()
	_theme.default_font = _font
	_theme.default_font_size = 14
	for kind in ["Button", "OptionButton"]:
		_theme.set_stylebox("normal", kind, _flat(SURFACE_2, LINE_STRONG))
		_theme.set_stylebox("hover", kind, _flat(SURFACE_3, LINE_STRONG))
		_theme.set_stylebox("pressed", kind, _flat(SURFACE_3, ACCENT))
		_theme.set_stylebox("disabled", kind, _flat(SURFACE, LINE))
		_theme.set_stylebox("focus", kind, _flat(Color(0, 0, 0, 0), ACCENT))
		_theme.set_color("font_color", kind, TEXT)
		_theme.set_color("font_hover_color", kind, TEXT)
		_theme.set_color("font_pressed_color", kind, TEXT)
		_theme.set_color("font_disabled_color", kind, SUBTLE)
	_theme.set_stylebox("normal", "LineEdit", _flat(BG_SHELL, LINE_STRONG, 10, 12))
	_theme.set_stylebox("focus", "LineEdit", _flat(Color(0, 0, 0, 0), ACCENT, 10, 12))
	_theme.set_stylebox("read_only", "LineEdit", _flat(SURFACE, LINE, 10, 12))
	_theme.set_color("font_color", "LineEdit", TEXT)
	_theme.set_color("caret_color", "LineEdit", ACCENT)
	_theme.set_color("font_color", "Label", TEXT)
	_theme.set_stylebox("panel", "PopupMenu", _flat(SURFACE_2, LINE_STRONG))
	_theme.set_color("font_color", "PopupMenu", TEXT)
	_theme.set_color("font_hover_color", "PopupMenu", TEXT)
	_theme.set_stylebox("hover", "PopupMenu", _flat(SURFACE_3, LINE))
	var tip := _flat(BG_SHELL, LINE_STRONG, 8, 8)
	_theme.set_stylebox("panel", "TooltipPanel", tip)
	_theme.set_color("font_color", "TooltipLabel", TEXT)


func _reset_run() -> void:
	_snap = {}
	_latest = {}
	_ind = {}
	_snapshots_by_tick.clear()
	_indicators_by_tick.clear()
	_decisions_by_agent.clear()
	_heard_by_agent.clear()
	_packets.clear()
	_ripples.clear()
	_ghosts.clear()
	_bursts.clear()
	_timeline.clear()
	_world_markers.clear()
	_feed.clear()
	_tween_from.clear()
	_end = {}
	_end_dismissed = false
	_selected = ""
	_trace = {}
	_announcement = ""
	_world_smoke = {}
	_first_danger_tick = -1
	_rail_scroll = 0.0
	_toast = ""
	_paused = false
	if _pause_btn != null:
		_pause_btn.text = "Figer"


func _connect_ws(reset_state: bool = false) -> void:
	if reset_state:
		_reset_run()
	_ws.close()
	_ws = WebSocketPeer.new()
	_ws.inbound_buffer_size = 8 * 1024 * 1024
	_ws.outbound_buffer_size = 1 * 1024 * 1024
	_status = "connexion…"
	var err := _ws.connect_to_url(_ws_url)
	if err != OK:
		_status = "connexion impossible : %s" % _ws_url


func _process(_delta: float) -> void:
	_ws.poll()
	while _ws.get_available_packet_count() > 0:
		_handle(_ws.get_packet().get_string_from_utf8())
	var now_s := _now()
	match _ws.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			_reconnect_at = -1.0
			if _status != "connecté" and _status != "terminé":
				_status = "connecté"
		WebSocketPeer.STATE_CLOSED:
			if _status != "terminé":
				_status = "déconnecté"
				if _ws_url != "ws://127.0.0.1:1":
					if _reconnect_at < 0.0:
						_reconnect_at = now_s + 3.0
					elif now_s >= _reconnect_at:
						_reconnect_at = now_s + 3.0
						_connect_ws(false)
	_poll_trace_ws()
	if _clear_sel_btn != null:
		_clear_sel_btn.visible = _selected != "" and not _agent_by_id(_selected).is_empty()
	if _replay_btn != null:
		_replay_btn.disabled = _plan.is_empty()
	if _pause_btn != null:
		_pause_btn.disabled = _plan.is_empty() or (_status == "terminé" and not _paused)
	_packets = _packets.filter(func(p): return now_s - float(p.get("t", 0.0)) < TALK_LIFE)
	_ripples = _ripples.filter(func(p): return now_s - float(p.get("t", 0.0)) < TALK_LIFE)
	_bursts = _bursts.filter(func(p): return now_s - float(p.get("t", 0.0)) < 0.62)
	if _debug and now_s > _debug_at:
		_debug_at = now_s + 2.0
		print("debug : %s · tick %s · plan %d · agents %d · fumée %s" % [
			_status, str(_snap.get("tick", "?")), _plan.size(),
			_snap.get("agents", []).size(), str(_snap.get("smoke_active", false)),
		])
	_maybe_screenshot()
	queue_redraw()


func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


func _maybe_screenshot() -> void:
	if _screenshot_path.is_empty() or _screenshot_done:
		return
	if _snap.get("agents", []).is_empty():
		return
	var ready: bool = bool(_snap.get("smoke_active", false))
	if _screenshot_tick >= 0:
		ready = int(_snap.get("tick", 0)) >= _screenshot_tick
	if OS.get_environment("MAREE_SCREENSHOT_END") == "1":
		ready = not _end.is_empty()
	if not ready:
		return
	if _screenshot_at < 0.0:
		_screenshot_at = _now() + 1.0
		return
	if _now() < _screenshot_at:
		return
	var image := get_viewport().get_texture().get_image()
	if image == null:
		return
	image.save_png(_screenshot_path)
	_screenshot_done = true
	print("capture : %s" % _screenshot_path)
	if OS.get_environment("MAREE_SCREENSHOT_QUIT") == "1":
		get_tree().quit()


func _handle(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var message: Dictionary = parsed
	match str(message.get("type", "")):
		"hello":
			# Le serveur rediffuse tout depuis le début : repartir d'une page
			# blanche, sinon une reconnexion double le fil et la courbe.
			if not _snapshots_by_tick.is_empty():
				_reset_run()
			_run_id = str(message.get("run_id", ""))
			_plan = message.get("plan", {})
			_paving = null
			_live = bool(message.get("live", false))
			if _plan.has("smoke") and typeof(_plan["smoke"]) == TYPE_DICTIONARY:
				_world_smoke = _plan["smoke"]
			_apply_live_state()
		"snapshot":
			_ingest_snapshot(message)
		"indicators":
			if not _paused or _ind.is_empty():
				_ind = message
			_indicators_by_tick[int(message.get("tick", 0))] = message
		"decision":
			var aid := str(message.get("agent_id", ""))
			if aid != "":
				var arr: Array = _decisions_by_agent.get(aid, [])
				arr.push_front(message)
				if arr.size() > 40:
					arr.resize(40)
				_decisions_by_agent[aid] = arr
				var trig := str(message.get("trigger", ""))
				if trig != "" and trig != "periodique" and trig != "premiere_decision":
					var intent: Dictionary = message.get("intention", {})
					var ikind := str(intent.get("kind", ""))
					var itarget := str(intent.get("target", "")) if intent.get("target") != null else ""
					_push_group(
						int(message.get("tick", 0)),
						"DÉCISIONS",
						"decision",
						"%s%s" % [INTENTION_LABELS.get(ikind, ikind), " %s" % itarget if itarget != "" else ""],
						aid,
					)
		"message":
			var tick_m := int(message.get("tick", 0))
			if tick_m < 0:
				return # préhistoire : un souvenir, pas un présent
			var sender := str(message.get("from", ""))
			var recipients: Array = message.get("to", [])
			var now_s := _now()
			if not _paused:
				_ripples.append({"from": sender, "t": now_s})
				for r in recipients:
					_packets.append({"from": sender, "to": str(r), "t": now_s})
			_push_group(tick_m, "PAROLES", "talk", "« %s »" % str(message.get("content", "")), sender)
		"heard":
			var listener := str(message.get("agent_id", ""))
			if listener != "":
				var harr: Array = _heard_by_agent.get(listener, [])
				harr.push_front(message)
				if harr.size() > 40:
					harr.resize(40)
				_heard_by_agent[listener] = harr
		"trace":
			_trace = message
		"world":
			_handle_world(message)
		"injection":
			_note("injecté : %s" % str(message.get("kind", "?")))
			_push_feed(int(message.get("tick", 0)), "INTERVENTION", "world", "Action injectée dans le monde : %s." % str(message.get("kind", "?")))
		"ack":
			_note("✔ %s en file" % str(message.get("kind", "?")))
		"error":
			_note("✖ %s" % str(message.get("reason", "erreur")))
		"incident":
			var iaid := str(message.get("agent_id", "?"))
			var icause := str(message.get("cause", message.get("kind", "?")))
			_note("incident %s : %s" % [iaid, icause])
			_push_feed(int(message.get("tick", 0)), "INCIDENT", "danger", "%s : repli sur les règles (%s)." % [iaid, icause])
		"narrative":
			_push_feed(int(message.get("tick", 0)), "RÉCIT", "world", str(message.get("text", "")))
		"end":
			_status = "terminé"
			_end = message
			_push_feed(
				int(message.get("tick", 0)),
				"FIN",
				"end",
				"Run terminé : %s personnes sorties sur %s, en %s ticks." % [
					_num(message.get("evacuated")),
					_num(message.get("total")),
					_num(message.get("ticks")),
				]
			)


func _ingest_snapshot(message: Dictionary) -> void:
	var now_s := _now()
	if _last_snap_at > 0.0:
		_snap_interval = clampf(now_s - _last_snap_at, 0.12, 0.9)
	_last_snap_at = now_s
	_latest = message
	var t := int(message.get("tick", 0))
	_snapshots_by_tick[t] = message
	_record_timeline(message)
	if _preselect != "" and _selected == "" and not _agent_by_id(_preselect).is_empty():
		_selected = _preselect
	if not _paused or _snap.is_empty():
		_show(message, true)
		if _preselect != "" and _selected == "":
			for a in message.get("agents", []):
				if str(a.get("id", "")) == _preselect:
					_selected = _preselect


## Affiche un instantané ; tout ce qui est à l'écran en découle.
func _show(snap: Dictionary, animate: bool) -> void:
	var now_s := _now()
	var from: Dictionary = {}
	for a in _snap.get("agents", []):
		if not bool(a.get("evacuated", false)):
			from[str(a.get("id", ""))] = _display_pos(a, now_s)
	if animate and not _snap.is_empty():
		for a in snap.get("agents", []):
			var id := str(a.get("id", ""))
			if bool(a.get("evacuated", false)) and from.has(id):
				var start: Vector2 = from[id]
				var gate := _exit_nearest(start)
				_ghosts.append({
					"from": start,
					"to": gate.get("point", start),
					"exit": gate.get("id", ""),
					"belief": str(a.get("belief", "")),
					"t": now_s,
					"dur": _snap_interval,
				})
	_tween_from = from
	_tween_start = now_s
	_tween_dur = _snap_interval if animate else 0.0
	_snap = snap
	var tick := int(snap.get("tick", 0))
	if _indicators_by_tick.has(tick):
		_ind = _indicators_by_tick[tick]


func _display_pos(agent: Dictionary, now_s: float) -> Vector2:
	var raw: Array = agent.get("pos", [0.0, 0.0])
	var to := Vector2(float(raw[0]), float(raw[1]))
	var id := str(agent.get("id", ""))
	if _tween_dur <= 0.0 or not _tween_from.has(id):
		return to
	var from: Vector2 = _tween_from[id]
	return from.lerp(to, clampf((now_s - _tween_start) / _tween_dur, 0.0, 1.0))


## Le journal ne dit pas par où l'agent est passé : l'issue la plus proche de
## sa dernière position sert uniquement à placer l'animation.
func _exit_nearest(pos: Vector2) -> Dictionary:
	var best: Dictionary = {}
	var best_d := INF
	for exit in _plan.get("exits", []):
		var mid := (_vec(exit["a"]) + _vec(exit["b"])) * 0.5
		var d := mid.distance_to(pos)
		if d < best_d:
			best_d = d
			best = {"id": str(exit["id"]), "point": mid}
	return best


func _vec(point: Variant) -> Vector2:
	return Vector2(float(point[0]), float(point[1]))


func _handle_world(message: Dictionary) -> void:
	var t := int(message.get("tick", 0))
	if _first_danger_tick < 0:
		_first_danger_tick = t
	match str(message.get("kind", "")):
		"smoke":
			_world_smoke = {
				"position": message.get("position", []),
				"radius": float(message.get("radius", 0.0)),
				"tick": t,
			}
			_smoke_born = _now()
			_world_markers.append({"tick": t, "label": "Fumée", "color": MUTED})
			_note("fumée visible (t%s)" % t)
			var zone := _zone_name_at(message.get("position", []))
			var where := "De la fumée apparaît : %s" % zone if zone != "" else "De la fumée apparaît"
			_push_feed(t, "ALERTE", "danger", "%s." % where)
			_alert(where, DANGER, DANGER_LINE)
		"announcement":
			_announcement = str(message.get("text", ""))
			_announcement_at = Time.get_ticks_msec()
			_world_markers.append({"tick": t, "label": "Annonce", "color": WARN})
			_note("annonce diffusée")
			_push_feed(t, "ANNONCE", "world", "Haut-parleurs : « %s »" % _announcement)
			_alert("Annonce diffusée par les haut-parleurs", WARN, BELIEF_COLORS["B"])
		"exit_closed":
			var ex := str(message.get("exit", "?"))
			_world_markers.append({"tick": t, "label": "Sortie %s fermée" % ex, "color": DANGER})
			_note("sortie %s fermée" % ex)
			_push_feed(t, "SORTIE FERMÉE", "danger", "La sortie %s vient de fermer." % ex)
			_alert("La sortie %s vient de fermer" % ex, DANGER, DANGER_LINE)


func _alert(text: String, ink: Color, flash: Color) -> void:
	if _paused:
		return
	_toast = text
	_toast_at = _now()
	_toast_color = ink
	_flash_at = _now()
	_flash_color = flash


func _zone_name_at(pos: Variant) -> String:
	if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		return ""
	var x := float(pos[0])
	var y := float(pos[1])
	for z in _plan.get("zones", []):
		var poly: Array = z.get("polygon", [])
		if poly.is_empty():
			continue
		var r := Rect2(_vec(poly[0]), Vector2.ZERO)
		for pt in poly:
			r = r.expand(_vec(pt))
		if x >= r.position.x and x <= r.end.x and y >= r.position.y and y <= r.end.y:
			return str(z.get("label", z.get("id", "")))
	return ""


func _record_timeline(snap: Dictionary) -> void:
	var agents: Array = snap.get("agents", [])
	var total := agents.size()
	var evac := total - _active_count(snap)
	var tick := int(snap.get("tick", 0))
	for i in range(_timeline.size()):
		if int(_timeline[i]["tick"]) == tick:
			_timeline[i] = {"tick": tick, "evacuated": evac, "total": total}
			return
	_timeline.append({"tick": tick, "evacuated": evac, "total": total})


func _push_feed(tick: int, tag: String, kind: String, text: String) -> void:
	_feed.push_front({"tick": tick, "tag": tag, "kind": kind, "text": text})
	if _feed.size() > FEED_LIMIT:
		_feed.resize(FEED_LIMIT)


## Une ligne par tick et par nature : 30 paroles identiques se lisent en une.
func _push_group(tick: int, tag: String, kind: String, text: String, agent_id: String) -> void:
	var group: Dictionary = {}
	for item in _feed:
		if int(item.get("tick", 0)) == tick and str(item.get("kind", "")) == kind:
			group = item
			break
	if group.is_empty():
		group = {"tick": tick, "tag": tag, "kind": kind, "lines": {}, "people": {}}
		_feed.push_front(group)
		if _feed.size() > FEED_LIMIT:
			_feed.resize(FEED_LIMIT)
	var lines: Dictionary = group["lines"]
	lines[text] = int(lines.get(text, 0)) + 1
	var people: Dictionary = group["people"]
	people[agent_id] = true


func _active_count(snap: Dictionary) -> int:
	var count := 0
	for a in snap.get("agents", []):
		if not bool(a.get("evacuated", false)):
			count += 1
	return count


# ------------------------------------------------------------------
# D3 — Panneau d'intervention et commandes hautes
# ------------------------------------------------------------------
func _build_inject_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	var primary := _flat(ACCENT_SOLID, Color(1, 1, 1, 0.12))
	var primary_hover := _flat(ACCENT_HOVER, Color(1, 1, 1, 0.16))
	var ghost := _flat(Color(0, 0, 0, 0), Color(0, 0, 0, 0))
	var ghost_hover := _flat(SURFACE_3, Color(0, 0, 0, 0))

	_pause_btn = Button.new()
	_pause_btn.text = "Figer"
	_pause_btn.tooltip_text = "Figer l'affichage (Espace)"
	_pause_btn.theme = _theme
	_pause_btn.custom_minimum_size = Vector2(96, 44)
	_pause_btn.add_theme_stylebox_override("normal", ghost)
	_pause_btn.add_theme_stylebox_override("hover", ghost_hover)
	_pause_btn.add_theme_stylebox_override("disabled", ghost)
	_pause_btn.pressed.connect(_toggle_pause)
	layer.add_child(_pause_btn)

	_replay_btn = Button.new()
	_replay_btn.text = "Rejouer"
	_replay_btn.theme = _theme
	_replay_btn.custom_minimum_size = Vector2(92, 44)
	_replay_btn.add_theme_stylebox_override("normal", ghost)
	_replay_btn.add_theme_stylebox_override("hover", ghost_hover)
	_replay_btn.add_theme_stylebox_override("disabled", ghost)
	_replay_btn.pressed.connect(func(): _connect_ws(true))
	layer.add_child(_replay_btn)

	_toggle = Button.new()
	_toggle.text = "Intervenir"
	_toggle.theme = _theme
	_toggle.custom_minimum_size = Vector2(118, 44)
	_toggle.add_theme_stylebox_override("normal", primary)
	_toggle.add_theme_stylebox_override("hover", primary_hover)
	_toggle.add_theme_stylebox_override("pressed", primary_hover)
	_toggle.add_theme_color_override("font_color", Color.WHITE)
	_toggle.add_theme_color_override("font_hover_color", Color.WHITE)
	_toggle.pressed.connect(_toggle_panel)
	layer.add_child(_toggle)

	_clear_sel_btn = Button.new()
	_clear_sel_btn.text = "‹  Retour au fil"
	_clear_sel_btn.theme = _theme
	_clear_sel_btn.custom_minimum_size = Vector2(130, 44)
	_clear_sel_btn.add_theme_stylebox_override("normal", ghost)
	_clear_sel_btn.add_theme_stylebox_override("hover", ghost_hover)
	_clear_sel_btn.visible = false
	_clear_sel_btn.pressed.connect(func(): _selected = "")
	layer.add_child(_clear_sel_btn)

	var panel_style := _flat(SURFACE, LINE_STRONG, 14)
	panel_style.content_margin_left = 16
	panel_style.content_margin_right = 16
	panel_style.content_margin_top = 14
	panel_style.content_margin_bottom = 14
	panel_style.shadow_color = Color(0, 0, 0, 0.6)
	panel_style.shadow_size = 24
	panel_style.shadow_offset = Vector2(0, 10)

	_panel = PanelContainer.new()
	_panel.theme = _theme
	_panel.custom_minimum_size = Vector2(360, 0)
	_panel.add_theme_stylebox_override("panel", panel_style)
	_panel.visible = false
	layer.add_child(_panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_panel.add_child(box)

	var title := Label.new()
	title.text = "Intervenir dans la simulation"
	title.add_theme_font_override("font", _font_b)
	title.add_theme_font_size_override("font_size", 15)
	box.add_child(title)

	_announce_edit = LineEdit.new()
	_announce_edit.text = "Évacuation immédiate, sortie B"
	_announce_edit.tooltip_text = "Texte de l'annonce diffusée aux agents"
	_announce_edit.custom_minimum_size = Vector2(0, 44)
	box.add_child(_announce_edit)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	var announce := Button.new()
	announce.text = "Diffuser l'annonce"
	announce.custom_minimum_size = Vector2(0, 44)
	announce.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	announce.add_theme_stylebox_override("normal", primary)
	announce.add_theme_stylebox_override("hover", primary_hover)
	announce.add_theme_color_override("font_color", Color.WHITE)
	announce.add_theme_color_override("font_hover_color", Color.WHITE)
	announce.pressed.connect(_inject_announcement)
	row.add_child(announce)
	_buttons.append(announce)

	var row2 := HBoxContainer.new()
	row2.add_theme_constant_override("separation", 8)
	box.add_child(row2)
	_exit_pick = OptionButton.new()
	for exit_id in ["A", "B", "C"]:
		_exit_pick.add_item(exit_id)
	_exit_pick.custom_minimum_size = Vector2(76, 44)
	row2.add_child(_exit_pick)
	_buttons.append(_exit_pick)

	var close := Button.new()
	close.text = "Fermer cette sortie"
	close.custom_minimum_size = Vector2(0, 44)
	close.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	close.add_theme_stylebox_override("normal", _flat(DANGER_SOFT, Color(0.973, 0.443, 0.443, 0.5)))
	close.add_theme_stylebox_override("hover", _flat(Color(0.973, 0.443, 0.443, 0.24), Color(0.973, 0.443, 0.443, 0.5)))
	close.add_theme_color_override("font_color", DANGER)
	close.add_theme_color_override("font_hover_color", DANGER)
	close.pressed.connect(_inject_exit_closed)
	row2.add_child(close)
	_buttons.append(close)

	var smoke := Button.new()
	smoke.text = "Fumée au dernier point cliqué sur la carte"
	smoke.custom_minimum_size = Vector2(0, 44)
	smoke.pressed.connect(_inject_smoke)
	box.add_child(smoke)
	_buttons.append(smoke)

	_hint = Label.new()
	_hint.text = "connexion…"
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint.custom_minimum_size = Vector2(328, 0)
	_hint.add_theme_font_size_override("font_size", 13)
	_hint.add_theme_color_override("font_color", MUTED)
	box.add_child(_hint)


func _toggle_panel() -> void:
	_panel.visible = not _panel.visible
	_toggle.text = "Fermer" if _panel.visible else "Intervenir"


func _toggle_pause() -> void:
	_paused = not _paused
	if _pause_btn != null:
		_pause_btn.text = "Reprendre" if _paused else "Figer"
	if _paused:
		_toast = ""
	elif not _latest.is_empty():
		_show(_latest, false)


func _apply_live_state() -> void:
	for button in _buttons:
		button.disabled = not _live
	if _live:
		_hint.text = "Mode direct : cliquez la carte, puis le bouton Fumée."
		_hint.add_theme_color_override("font_color", MUTED)
	else:
		_hint.text = "Vous regardez un rejeu : aucune injection possible (lancez maree live)."
		_hint.add_theme_color_override("font_color", WARN)


func _send(command: Dictionary) -> void:
	if _ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		_note("✖ socket fermée : rien n'a été envoyé")
		return
	_ws.send_text(JSON.stringify(command))


func _inject_announcement() -> void:
	var text := _announce_edit.text.strip_edges()
	if text.is_empty():
		_note("✖ annonce vide : écrivez un texte")
		return
	_send({"type": "inject", "kind": "announcement", "text": text})


func _inject_exit_closed() -> void:
	var exit_id := _exit_pick.get_item_text(_exit_pick.selected)
	_send({"type": "inject", "kind": "exit_closed", "exit": exit_id})


func _inject_smoke() -> void:
	if _last_click_m.x < 0.0:
		_note("✖ cliquez d'abord sur le plan")
		return
	_send({
		"type": "inject",
		"kind": "smoke",
		"position": [_last_click_m.x, _last_click_m.y],
		"radius": 8.0,
	})


func _note(text: String) -> void:
	_notes.append(text)
	while _notes.size() > 3:
		_notes.pop_front()
	_last_note = text
	if _hint != null:
		_hint.text = "\n".join(_notes)


# ------------------------------------------------------------------
# Dessin principal. L'ordre compte : la carte d'abord, puis la coque par
# dessus, ce qui rogne tout ce qui déborde sans avoir à découper.
# ------------------------------------------------------------------
func _draw() -> void:
	var view := _viewport()
	draw_rect(Rect2(Vector2.ZERO, view), BG_SHELL)
	_layout_buttons(view)

	var stage_w := view.x - RAIL_W - GAP * 3.0
	var card := Rect2(GAP, TOP_H + GAP, stage_w, view.y - TOP_H - GAP * 3.0 - DECK_H)
	_map_rect = Rect2(card.position + Vector2(0, HEAD_H), card.size - Vector2(0, HEAD_H))
	_rail_rect = Rect2(view.x - RAIL_W - GAP, TOP_H + GAP * 2.0 + HERO_H, RAIL_W, view.y - TOP_H - GAP * 3.0 - HERO_H)

	draw_rect(_map_rect, MAP_BG)
	if not _plan.is_empty() and not _snap.is_empty():
		_fit()
		var now_s := _now()
		_draw_ground()
		_draw_obstacles()
		_draw_density()
		_draw_smoke(now_s)
		_mask_outside_plan(view)
		_draw_walls()
		_draw_smoke_label()
		_draw_exits(now_s)
		_draw_selected_trail()
		_draw_talk(now_s)
		_draw_ghosts(now_s)
		_draw_agents(now_s)
		_draw_bursts(now_s)
		_draw_flash(now_s)
		_draw_announcement()
		_draw_toast(now_s)
		_draw_end_card()

	# Coque : couvre ce qui dépasse de la carte.
	draw_rect(Rect2(0, 0, view.x, card.position.y + HEAD_H), BG_SHELL)
	draw_rect(Rect2(0, 0, card.position.x, view.y), BG_SHELL)
	draw_rect(Rect2(card.end.x, 0, view.x - card.end.x, view.y), BG_SHELL)
	draw_rect(Rect2(0, card.end.y, view.x, view.y - card.end.y), BG_SHELL)

	if _plan.is_empty() or _snap.is_empty():
		_draw_empty_state()
	_card(card, Color(0, 0, 0, 0), LINE, RADIUS)
	_draw_map_head(card)
	_draw_bottom_deck(Rect2(GAP, card.end.y + GAP, stage_w, DECK_H))
	_draw_rail(view)
	_draw_topbar(view)
	_draw_trace(view)


func _card(rect: Rect2, fill: Color, border: Color = LINE, radius: int = RADIUS, shadow: int = 0) -> void:
	_box_style.bg_color = fill
	_box_style.border_color = border
	_box_style.set_border_width_all(1)
	_box_style.set_corner_radius_all(radius)
	_box_style.anti_aliasing = true
	_box_style.shadow_size = shadow
	_box_style.shadow_color = Color(0, 0, 0, 0.55)
	_box_style.shadow_offset = Vector2(0, shadow * 0.4)
	draw_style_box(_box_style, rect)


func _layout_buttons(view: Vector2) -> void:
	var y := (TOP_H - 44.0) * 0.5
	var x := view.x - GAP
	if _toggle != null:
		x -= _toggle.size.x
		_toggle.position = Vector2(x, y)
	if _replay_btn != null:
		x -= _replay_btn.size.x + 4.0
		_replay_btn.position = Vector2(x, y)
	if _pause_btn != null:
		x -= _pause_btn.size.x + 4.0
		_pause_btn.position = Vector2(x, y)
	if _panel != null:
		_panel.position = Vector2(view.x - GAP - _panel.size.x, TOP_H + 6.0)
	if _clear_sel_btn != null:
		_clear_sel_btn.position = Vector2(_rail_rect.position.x + 6.0, _rail_rect.position.y + 2.0)


func _draw_topbar(view: Vector2) -> void:
	draw_rect(Rect2(0, 0, view.x, TOP_H), BG_SHELL)
	draw_line(Vector2(0, TOP_H), Vector2(view.x, TOP_H), LINE, 1.0)

	# Marque : le même logo que le web.
	_card(Rect2(GAP + 2.0, 13, 34, 34), ACCENT_SOLID, Color(0, 0, 0, 0), 9)
	var wave := PackedVector2Array()
	for i in range(25):
		var u := float(i) / 24.0
		wave.append(Vector2(GAP + 8.0 + u * 22.0, 30.0 + sin(u * TAU) * -3.5))
	draw_polyline(wave, Color("#fafafa"), 2.4, true)

	_text_b(Vector2(GAP + 48.0, 27), "M A R É E", 13, TEXT)
	var subtitle := "Port-Aubel · run « %s »" % _run_id if _run_id != "" else "Évacuation de l'esplanade de Port-Aubel"
	_text(Vector2(GAP + 48.0, 45), subtitle, 13, MUTED)

	# Pastille d'état + horloge, centrées.
	var mode_txt := "Simulation en direct" if _live else "Rejeu d'un run enregistré"
	var ink := DANGER if _live else ACCENT
	var fill := DANGER_SOFT if _live else ACCENT_SOFT
	if _status == "terminé":
		mode_txt = "Run terminé"
		ink = MUTED
		fill = SURFACE_2
	elif _plan.is_empty():
		mode_txt = "Hors ligne" if _status == "déconnecté" else "Connexion…"
		ink = MUTED
		fill = SURFACE_2
	var pill_w := _font_b.get_string_size(mode_txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x + 36.0
	var clock := str(_snap.get("sim_time", "—"))
	var tick_txt := "tick %d" % int(_snap.get("tick", 0)) if not _snap.is_empty() else "temps simulé"
	var clock_w := _font_b.get_string_size(clock, HORIZONTAL_ALIGNMENT_LEFT, -1, 22).x
	var tick_w := _font.get_string_size(tick_txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x
	var x := view.x * 0.5 - (pill_w + 18.0 + clock_w + 8.0 + tick_w) * 0.5
	_card(Rect2(x, 15, pill_w, 30), fill, Color(ink.r, ink.g, ink.b, 0.4), 15)
	draw_circle(Vector2(x + 15, 30), 4.0, ink, true, -1.0, true)
	if _live:
		var ping := fmod(_now(), 1.6) / 1.6
		draw_circle(Vector2(x + 15, 30), 4.0 + ping * 7.0, Color(ink.r, ink.g, ink.b, 0.5 * (1.0 - ping)), true, -1.0, true)
	_text_b(Vector2(x + 26, 35), mode_txt, 13, ink)
	x += pill_w + 18.0
	_text_b(Vector2(x, 38), clock, 22, TEXT)
	_text(Vector2(x + clock_w + 8.0, 37), tick_txt, 13, SUBTLE)


func _draw_empty_state() -> void:
	var c := _map_rect.get_center()
	draw_rect(_map_rect, MAP_BG)
	draw_texture_rect(_glow, Rect2(c - _map_rect.size * 0.5, _map_rect.size), false, Color(0.263, 0.22, 0.792, 0.28))
	var t := _now()
	for row in range(2):
		var pts := PackedVector2Array()
		for i in range(61):
			var u := float(i) / 60.0
			pts.append(Vector2(c.x - 60.0 + u * 120.0, c.y - 96.0 + row * 12.0 + sin(u * TAU * 2.0 + t * 1.4 + row) * 5.0))
		draw_polyline(pts, Color(ACCENT.r, ACCENT.g, ACCENT.b, 1.0 - row * 0.6), 2.0, true)

	var connected := _status == "connecté" and not _plan.is_empty()
	var title := "En attente du premier instantané…" if connected else "Aucune simulation connectée"
	_text_center(Vector2(c.x, c.y - 42.0), title, 20, TEXT, true)
	_text_center(Vector2(c.x, c.y - 16.0), "Ce client n'invente aucune donnée. Démarrez le moteur à la racine du dépôt :", 14, MUTED)
	var rows := [["Revoir le dernier run enregistré", "uv run maree serve"], ["Lancer une simulation en direct", "uv run maree live"]]
	var y := c.y + 4.0
	for row in rows:
		var box := Rect2(c.x - 230.0, y, 460.0, 44.0)
		_card(box, SURFACE, LINE, 10)
		_text(box.position + Vector2(14, 27), str(row[0]), 14, MUTED)
		_text_right(Vector2(box.end.x - 14, box.position.y + 27), str(row[1]), 13, TEXT)
		y += 52.0
	_text_center(Vector2(c.x, y + 16.0), "Nouvelle tentative automatique toutes les 3 secondes…", 13, SUBTLE)


func _draw_map_head(card: Rect2) -> void:
	var head := Rect2(card.position, Vector2(card.size.x, HEAD_H))
	_card(head, SURFACE, LINE, RADIUS)
	draw_rect(Rect2(head.position.x + 1.0, head.end.y - RADIUS, head.size.x - 2.0, RADIUS), SURFACE)
	draw_line(Vector2(head.position.x, head.end.y), head.end, LINE, 1.0)
	_text_b(head.position + Vector2(16, 36), "Qui va où ?", 16, TEXT)

	var counts := {"A": 0, "B": 0, "C": 0, "": 0}
	var active := 0
	for a in _snap.get("agents", []):
		if bool(a.get("evacuated", false)):
			continue
		active += 1
		var b := str(a.get("belief", ""))
		counts[b if counts.has(b) else ""] += 1

	var items: Array = []
	for exit in _plan.get("exits", []):
		items.append([str(exit["id"]), "Sortie %s" % str(exit["id"]), str(exit.get("label", ""))])
	items.append(["", "Sans sortie", "Hésite ou observe"])
	if _plan.get("exits", []).is_empty():
		return

	var x := head.position.x + 112.0
	var gap := 6.0
	var chip_w := (head.end.x - 8.0 - x - gap * (items.size() - 1)) / float(items.size())
	for item in items:
		var key := str(item[0])
		var closed := key != "" and not _is_open(key)
		var chip := Rect2(x, head.position.y + 8.0, chip_w, 44.0)
		_card(chip, DANGER_SOFT if closed else SURFACE_2, Color(0.973, 0.443, 0.443, 0.5) if closed else LINE, 10)
		var col: Color = BELIEF_COLORS.get(key, UNKNOWN)
		_draw_agent_shape(chip.position + Vector2(17, 22), 6.5, key, col)
		_text_b(chip.position + Vector2(32, 19), str(item[1]), 13, TEXT)
		var sub := "FERMÉE" if closed else _fit_text(str(item[2]), chip_w - 74.0, 12)
		_text(chip.position + Vector2(32, 35), sub, 12, DANGER if closed else MUTED)
		_text_right(Vector2(chip.end.x - 10, chip.position.y + 29), "%d" % counts.get(key, 0) if not _snap.is_empty() else "—", 18, TEXT, true)
		if active > 0 and int(counts.get(key, 0)) > 0:
			var share := float(counts.get(key, 0)) / float(active)
			draw_rect(Rect2(chip.position.x + 3.0, chip.end.y - 2.0, (chip_w - 6.0) * share, 2.0), col)
		x += chip_w + gap


func _fit_text(text: String, width: float, font_size: int) -> String:
	if _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x <= width:
		return text
	var out := text
	while out.length() > 1 and _font.get_string_size(out + "…", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x > width:
		out = out.substr(0, out.length() - 1)
	return out + "…"


# ------------------------------------------------------------------
# Carte : sol, décor
# ------------------------------------------------------------------
func _hash2(i: int, j: int) -> float:
	var s := sin(float(i) * 127.1 + float(j) * 311.7) * 43758.5453
	return s - floor(s)


## Pavage cuit une fois par plan : 8 pixels par mètre, dalles de 2,5 m.
func _bake_paving() -> void:
	var ppm := 8
	var w := int(_bounds.size.x) * ppm
	var h := int(_bounds.size.y) * ppm
	var image := Image.create(maxi(w, 1), maxi(h, 1), false, Image.FORMAT_RGB8)
	image.fill(Color8(31, 32, 39))
	var tile := int(2.5 * ppm)
	var rows := int(ceil(float(h) / float(tile)))
	var cols := int(ceil(float(w) / float(tile))) + 1
	for j in range(rows):
		var offset := tile / 2 if j % 2 == 1 else 0
		for i in range(cols):
			var light := 31 + int(_hash2(i, j) * 4.0)
			var rect := Rect2i(i * tile - offset, j * tile, tile - 1, tile - 1)
			image.fill_rect(rect, Color8(light, light + 1, light + 8))
	_paving = ImageTexture.create_from_image(image)


func _plan_rect() -> Rect2:
	var a := _to_screen([_bounds.position.x, _bounds.end.y])
	var b := _to_screen([_bounds.end.x, _bounds.position.y])
	return Rect2(a, b - a)


func _draw_ground() -> void:
	if _paving == null:
		_bake_paving()
	var r := _plan_rect()
	# Ombre du plan sur la nuit.
	draw_texture_rect(_glow, r.grow(r.size.x * 0.12), false, Color(0, 0, 0, 0.9))
	draw_texture_rect(_paving, r, false)

	# Éclairage : nappe centrale, bords qui tombent dans le noir.
	draw_texture_rect(_glow, Rect2(r.get_center() - r.size * 0.62, r.size * 1.24), false, Color(0.75, 0.77, 1.0, 0.09))
	var edge := Color(0, 0, 0, 0.42)
	var clear := Color(0, 0, 0, 0)
	var depth := minf(r.size.x, r.size.y) * 0.24
	_gradient_quad(r.position, Vector2(r.end.x, r.position.y), Vector2(r.end.x, r.position.y + depth), Vector2(r.position.x, r.position.y + depth), edge, clear)
	_gradient_quad(Vector2(r.position.x, r.end.y), r.end, Vector2(r.end.x, r.end.y - depth), Vector2(r.position.x, r.end.y - depth), edge, clear)
	draw_polygon(PackedVector2Array([r.position, Vector2(r.position.x + depth, r.position.y), Vector2(r.position.x + depth, r.end.y), Vector2(r.position.x, r.end.y)]), PackedColorArray([edge, clear, clear, edge]))
	draw_polygon(PackedVector2Array([Vector2(r.end.x, r.position.y), Vector2(r.end.x - depth, r.position.y), Vector2(r.end.x - depth, r.end.y), r.end]), PackedColorArray([edge, clear, clear, edge]))

	if _px < 9.0:
		return
	for z in _plan.get("zones", []):
		if bool(z.get("hidden", false)):
			continue
		var zpts: Array = z.get("polygon", [])
		if zpts.size() < 3:
			continue
		var left := INF
		var top := INF
		var screen := PackedVector2Array()
		for pt in zpts:
			var sp := _to_screen(pt)
			screen.append(sp)
			left = minf(left, sp.x)
			top = minf(top, sp.y)
		for i in range(screen.size()):
			draw_dashed_line(screen[i], screen[(i + 1) % screen.size()], Color(1, 1, 1, 0.05), 1.0, 3.0)
		_text_b(Vector2(left + 10.0, top + 20.0), str(z.get("label", z.get("id", ""))).to_upper(), 11, Color(0.894, 0.894, 0.906, 0.62))


func _gradient_quad(a: Vector2, b: Vector2, c: Vector2, d: Vector2, near: Color, far: Color) -> void:
	draw_polygon(PackedVector2Array([a, b, c, d]), PackedColorArray([near, near, far, far]))


func _draw_obstacles() -> void:
	var lifts := {"tour": 15.0, "scene": 8.0, "stand": 6.0, "fontaine": 3.0}
	var faces := {
		"tour": [Color("#50525f"), Color("#3b3d48")],
		"scene": [Color("#4b4238"), Color("#39322b")],
		"stand": [Color("#474957"), Color("#363742")],
		"fontaine": [Color("#5a5c69"), Color("#44464f")],
	}
	for obstacle in _plan.get("obstacles", []):
		var base := PackedVector2Array()
		for point in obstacle.get("polygon", []):
			base.append(_to_screen(point))
		if base.size() < 3:
			continue
		var kind := str(obstacle.get("kind", ""))
		var h: float = float(lifts.get(kind, 5.0)) * clampf(_px / 16.0, 0.6, 1.6)

		# Ombre portée, lumière venant du nord-ouest.
		for step in [1.0, 0.6]:
			var shade := PackedVector2Array()
			for p in base:
				shade.append(p + Vector2(h * 0.5, h * 0.8) * float(step) + Vector2(2, 3))
			draw_colored_polygon(shade, Color(0, 0, 0, 0.3))

		# Flancs.
		var dy := 0.0
		while dy < h:
			var slice := PackedVector2Array()
			for p in base:
				slice.append(p - Vector2(0, dy))
			draw_colored_polygon(slice, Color("#23242c"))
			dy += 1.0

		# Dessus, dégradé nord-sud.
		var top := PackedVector2Array()
		var colors := PackedColorArray()
		var box := Rect2(base[0] - Vector2(0, h), Vector2.ZERO)
		for p in base:
			box = box.expand(p - Vector2(0, h))
		var pair: Array = faces.get(kind, faces["stand"])
		for p in base:
			var q := p - Vector2(0, h)
			top.append(q)
			var t := (q.y - box.position.y) / maxf(box.size.y, 1.0)
			colors.append((pair[0] as Color).lerp(pair[1], t))
		draw_polygon(top, colors)

		if kind == "stand":
			var band := maxf(4.0, _px * 0.4)
			var x := box.position.x
			var i := 0
			while x < box.end.x:
				if i % 2 == 1:
					draw_rect(Rect2(x, box.position.y, minf(band, box.end.x - x), box.size.y), Color(1, 1, 1, 0.07))
				x += band
				i += 1
		elif kind == "scene":
			var y := box.position.y
			while y < box.end.y:
				draw_line(Vector2(box.position.x, y), Vector2(box.end.x, y), Color(0, 0, 0, 0.28), 1.0)
				y += maxf(4.0, _px * 0.35)
		elif kind == "tour":
			draw_line(box.position, box.end, Color(1, 1, 1, 0.09), 1.0, true)
			draw_line(Vector2(box.end.x, box.position.y), Vector2(box.position.x, box.end.y), Color(1, 1, 1, 0.09), 1.0, true)
			_text_center(box.get_center() + Vector2(0, 4), str(obstacle.get("label", "Tour")), 11, Color("#e4e4e7"), true)
		elif kind == "fontaine":
			var c := box.get_center()
			var inner := PackedVector2Array()
			for q in top:
				inner.append(c + (q - c) * 0.74)
			draw_colored_polygon(inner, Color("#173a4d"))
			draw_texture_rect(_glow, Rect2(c - box.size * 0.36, box.size * 0.72), false, Color("#3a7f9e"))
			for ring in [0.16, 0.3]:
				draw_arc(c, box.size.x * float(ring), 0.0, TAU, 40, Color(0.745, 0.902, 1.0, 0.22), 1.0, true)

		var outline := top.duplicate()
		outline.append(top[0])
		draw_polyline(outline, Color(1, 1, 1, 0.13), 1.0, true)


func _draw_walls() -> void:
	var r := _plan_rect()
	draw_rect(r.grow(2.0), Color("#050507"), false, 5.0)
	draw_rect(r, WALL, false, 2.0)


## Le plan est un rectangle : quatre bandes suffisent à borner la fumée.
func _mask_outside_plan(view: Vector2) -> void:
	var r := _plan_rect()
	draw_rect(Rect2(0, 0, view.x, r.position.y), MAP_BG)
	draw_rect(Rect2(0, r.end.y, view.x, view.y - r.end.y), MAP_BG)
	draw_rect(Rect2(0, r.position.y, r.position.x, r.size.y), MAP_BG)
	draw_rect(Rect2(r.end.x, r.position.y, view.x - r.end.x, r.size.y), MAP_BG)


# ------------------------------------------------------------------
# Carte : ce qui bouge
# ------------------------------------------------------------------
func _draw_density() -> void:
	var r := _px * 1.9
	for cell in _snap.get("density_grid", []):
		var n := int(cell.get("n", 0))
		if n < 2:
			continue
		var p := _to_screen([float(cell["x"]) + 0.5, float(cell["y"]) + 0.5])
		var alpha: float = minf(0.13 * float(n), 0.42)
		draw_texture_rect(_glow, Rect2(p - Vector2(r, r), Vector2(r, r) * 2.0), false, Color(0.984, 0.573, 0.235, alpha))


func _current_smoke() -> Dictionary:
	if not bool(_snap.get("smoke_active", false)):
		return {}
	var smoke: Variant = _snap.get("smoke")
	if typeof(smoke) != TYPE_DICTIONARY or smoke.is_empty():
		smoke = _world_smoke
	var position: Variant = smoke.get("position", [])
	if typeof(position) != TYPE_ARRAY or position.size() < 2 or float(smoke.get("radius", 0.0)) <= 0.0:
		return {}
	return smoke


func _draw_smoke(now_s: float) -> void:
	var smoke := _current_smoke()
	if smoke.is_empty():
		return
	var centre := _to_screen(smoke["position"])
	var age := clampf((now_s - _smoke_born) / 1.4, 0.0, 1.0)
	var grow := 1.0 - pow(1.0 - age, 3.0)
	var radius := float(smoke["radius"]) * _px * (1.0 if _paused else grow)
	for i in range(18):
		var angle := _hash2(i, 1) * TAU + now_s * (_hash2(i, 4) - 0.5) * 0.12
		var wobble := sin(now_s * 0.35 + _hash2(i, 5) * TAU) * 0.05
		var dist := 0.08 + _hash2(i, 2) * 0.66 + wobble
		var size := radius * (0.26 + _hash2(i, 3) * 0.3)
		var at := centre + Vector2(cos(angle), sin(angle)) * radius * dist
		draw_texture_rect(_glow, Rect2(at - Vector2(size, size), Vector2(size, size) * 2.0), false, Color(0.8, 0.81, 0.85, 0.17))
	var dashes := 150
	for i in range(dashes):
		if i % 2 == 0:
			var a0 := TAU * float(i) / float(dashes)
			draw_arc(centre, radius, a0, a0 + TAU / float(dashes), 4, Color(0.894, 0.894, 0.906, 0.34), 1.25, true)


func _draw_smoke_label() -> void:
	var smoke := _current_smoke()
	if smoke.is_empty():
		return
	var centre := _to_screen(smoke["position"])
	var y := maxf(centre.y - float(smoke["radius"]) * _px + 18.0, _plan_rect().position.y + 18.0)
	_pill(Vector2(centre.x, y), "FUMÉE", Color("#e4e4e7"), Color(0.078, 0.082, 0.102, 0.8), Color(0.894, 0.894, 0.906, 0.3))


func _pill(center: Vector2, text: String, ink: Color, fill: Color, border: Color) -> void:
	var w := _font_b.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x + 16.0
	_card(Rect2(center.x - w * 0.5, center.y - 10.0, w, 20.0), fill, border, 10)
	_text_center(center + Vector2(0, 4), text, 11, ink, true)


func _exit_outward(exit: Dictionary) -> Vector2:
	var mid := (_vec(exit["a"]) + _vec(exit["b"])) * 0.5
	var options := [
		[absf(mid.y - _bounds.end.y), Vector2(0, -1)],
		[absf(mid.y - _bounds.position.y), Vector2(0, 1)],
		[absf(mid.x - _bounds.end.x), Vector2(1, 0)],
		[absf(mid.x - _bounds.position.x), Vector2(-1, 0)],
	]
	options.sort_custom(func(p, q): return float(p[0]) < float(q[0]))
	return options[0][1]


func _draw_exits(now_s: float) -> void:
	for exit in _plan.get("exits", []):
		var eid := str(exit["id"])
		var a := _to_screen(exit["a"])
		var b := _to_screen(exit["b"])
		var open := _is_open(eid)
		var col: Color = BELIEF_COLORS.get(eid, Color.WHITE) if open else DANGER_LINE
		var mid := (a + b) * 0.5
		var out := _exit_outward(exit)

		var glow := maxf(a.distance_to(b), 30.0) * 1.1
		draw_texture_rect(_glow, Rect2(mid - Vector2(glow, glow) * 0.5, Vector2(glow, glow)), false, Color(col.r, col.g, col.b, 0.34))
		draw_line(a, b, Color("#08090c"), 9.0, true)
		draw_line(a, b, col, 5.0, true)

		if open:
			var side := Vector2(-out.y, out.x)
			for i in range(2):
				var t := fmod(now_s / 1.4 + float(i) * 0.5, 1.0)
				var d := 8.0 + t * 14.0
				var alpha := sin(t * PI) * 0.9
				var chevron := PackedVector2Array([
					mid + out * d + side * 5.0,
					mid + out * (d + 5.0),
					mid + out * d - side * 5.0,
				])
				draw_polyline(chevron, Color(col.r, col.g, col.b, alpha), 1.75, true)
		else:
			draw_line(mid + Vector2(-7, -7), mid + Vector2(7, 7), DANGER_LINE, 2.5, true)
			draw_line(mid + Vector2(7, -7), mid + Vector2(-7, 7), DANGER_LINE, 2.5, true)

		# Étiquette à l'extérieur du plan : elle ne couvre ni la foule ni le décor.
		var title := "Sortie %s" % eid
		var sub := str(exit.get("label", "")) if open else "FERMÉE"
		var w1 := _font_b.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 18.0
		var w2 := _font.get_string_size(sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x
		var w := maxf(w1, w2) + 18.0
		var h := 38.0 if sub != "" else 24.0
		var gap := 26.0
		var lx := mid.x + out.x * gap - (w * 0.5 if out.x == 0.0 else (w if out.x < 0.0 else 0.0))
		var ly := mid.y + out.y * gap - (h * 0.5 if out.y == 0.0 else (h if out.y < 0.0 else 0.0))
		lx = clampf(lx, _map_rect.position.x + 6.0, _map_rect.end.x - w - 6.0)
		ly = clampf(ly, _map_rect.position.y + 6.0, _map_rect.end.y - h - 6.0)
		_card(Rect2(lx, ly, w, h), Color(0.063, 0.067, 0.086, 0.92), Color(col.r, col.g, col.b, 0.55 if open else 1.0), 9)
		_draw_agent_shape(Vector2(lx + 15, ly + 13), 4.6, eid, col)
		_text_b(Vector2(lx + 25, ly + 17), title, 12, TEXT)
		if sub != "":
			if open:
				_text(Vector2(lx + 9, ly + 31), sub, 11, MUTED)
			else:
				_text_b(Vector2(lx + 9, ly + 31), sub, 11, DANGER)


func _draw_selected_trail() -> void:
	if _selected == "":
		return
	var tick := int(_snap.get("tick", 0))
	var keys: Array = _snapshots_by_tick.keys()
	keys.sort()
	var pts: Array = []
	for k in keys:
		if int(k) > tick:
			break
		for a in _snapshots_by_tick[k].get("agents", []):
			if str(a.get("id", "")) == _selected:
				if not bool(a.get("evacuated", false)):
					pts.append(a["pos"])
				break
	for i in range(1, pts.size()):
		var alpha := 0.15 + 0.75 * float(i) / float(pts.size())
		draw_line(_to_screen(pts[i - 1]), _to_screen(pts[i]), Color(ACCENT.r, ACCENT.g, ACCENT.b, alpha), 2.0, true)


func _draw_talk(now_s: float) -> void:
	for ripple in _ripples:
		var from := _agent_by_id(str(ripple.get("from", "")))
		if from.is_empty() or bool(from.get("evacuated", false)):
			continue
		var t := (now_s - float(ripple.get("t", 0.0))) / TALK_LIFE
		var p := _to_screen_v(_display_pos(from, now_s))
		draw_arc(p, 6.0 + t * _px * 2.4, 0.0, TAU, 32, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.6 * (1.0 - t)), 1.25, true)

	# Les liens un à un : seulement ceux qui se lisent. À 300 d'un coup, ce
	# n'est plus de l'information, c'est un gribouillis qui masque les formes.
	var few := _packets.size() <= 24
	for pkt in _packets:
		var source := str(pkt.get("from", ""))
		var target := str(pkt.get("to", ""))
		if not few and source != _selected and target != _selected:
			continue
		var a := _agent_by_id(source)
		var b := _agent_by_id(target)
		if a.is_empty() or b.is_empty() or bool(a.get("evacuated", false)) or bool(b.get("evacuated", false)):
			continue
		var pa := _to_screen_v(_display_pos(a, now_s))
		var pb := _to_screen_v(_display_pos(b, now_s))
		var phase := clampf((now_s - float(pkt.get("t", 0.0))) / TALK_LIFE, 0.0, 1.0)
		draw_line(pa, pb, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.4 * (1.0 - phase)), 1.0, true)
		draw_circle(pa.lerp(pb, phase), 2.0, Color("#e0e7ff"), true, -1.0, true)


func _agent_radius() -> float:
	return clampf(_px * 0.38, 5.5, 9.0)


func _draw_ghosts(now_s: float) -> void:
	var r := _agent_radius()
	var kept: Array = []
	for g in _ghosts:
		var t := (now_s - float(g["t"])) / maxf(float(g["dur"]), 0.01)
		if t >= 1.0:
			_bursts.append({"exit": g["exit"], "t": now_s})
			continue
		kept.append(g)
		var from: Vector2 = g["from"]
		var to: Vector2 = g["to"]
		var belief := str(g["belief"])
		var col: Color = BELIEF_COLORS.get(belief, UNKNOWN)
		col.a = 1.0 - t * t
		_draw_agent_shape(_to_screen_v(from.lerp(to, t)), r, belief, col)
	_ghosts = kept


func _draw_bursts(now_s: float) -> void:
	for burst in _bursts:
		var t := (now_s - float(burst["t"])) / 0.62
		for exit in _plan.get("exits", []):
			if str(exit["id"]) != str(burst["exit"]):
				continue
			var p := (_to_screen(exit["a"]) + _to_screen(exit["b"])) * 0.5
			var col: Color = BELIEF_COLORS.get(str(exit["id"]), UNKNOWN)
			col.a = (1.0 - t) * 0.8
			draw_arc(p, 6.0 + t * 26.0, 0.0, TAU, 32, col, 1.5, true)


func _draw_agents(now_s: float) -> void:
	var r := _agent_radius()
	var moving := _tween_dur > 0.0
	var items: Array = []
	for agent in _snap.get("agents", []):
		if not bool(agent.get("evacuated", false)):
			items.append([agent, _to_screen_v(_display_pos(agent, now_s))])

	# Ombres d'abord : aucune ne doit passer sur une personne voisine.
	for item in items:
		var p: Vector2 = item[1]
		draw_set_transform(p + Vector2(1.5, r * 0.7), 0.0, Vector2(1.0, 0.48))
		draw_circle(Vector2.ZERO, r * 1.05, Color(0, 0, 0, 0.42), true, -1.0, true)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

	var chosen: Array = []
	for item in items:
		var agent: Dictionary = item[0]
		var p: Vector2 = item[1]
		var aid := str(agent["id"])
		var belief := str(agent.get("belief", ""))
		var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
		var dimmed := _selected != "" and aid != _selected
		var alpha := 0.38 if dimmed else 1.0

		# Traînée : le mouvement de ce tick, tel qu'il est dans le journal.
		if moving and _tween_from.has(aid):
			var from: Vector2 = _tween_from[aid]
			var to := _vec(agent["pos"])
			var d := from.distance_to(to)
			if d > 0.4:
				var dir := (to - from) / d
				var length := minf(r * 2.4, d * _px * 0.4)
				draw_line(p, p - Vector2(dir.x, -dir.y) * length, Color(colour.r, colour.g, colour.b, alpha * 0.4), r * 0.8, true)

		_draw_agent_shape(p, r, belief, Color(colour.r, colour.g, colour.b, alpha), true)
		if belief != "" and not _is_open(belief):
			draw_arc(p, r + 3.5, 0.0, TAU, 24, Color(DANGER_LINE.r, DANGER_LINE.g, DANGER_LINE.b, alpha), 1.75, true)
		if aid == _selected:
			chosen = [agent, p]

	if not chosen.is_empty():
		var p: Vector2 = chosen[1]
		var pulse := fmod(now_s / 1.3, 1.0)
		draw_arc(p, r + 5.0 + pulse * 11.0, 0.0, TAU, 32, Color(1, 1, 1, 0.7 * (1.0 - pulse)), 1.5, true)
		draw_arc(p, r + 4.5, 0.0, TAU, 32, Color.WHITE, 2.0, true)
		_pill(p - Vector2(0, r + 20.0), str(chosen[0]["id"]), BG_SHELL, TEXT, TEXT)


func _draw_agent_shape(center: Vector2, r: float, belief: String, col: Color, outlined: bool = false) -> void:
	var edge := Color(0.047, 0.051, 0.067, col.a)
	if belief == "B":
		var box := Rect2(center - Vector2(r * 0.85, r * 0.85), Vector2(r * 1.7, r * 1.7))
		draw_rect(box, col)
		if outlined:
			draw_rect(box, edge, false, 1.5)
	elif belief == "C":
		var tri := PackedVector2Array([
			center + Vector2(0, -r * 1.1),
			center + Vector2(r * 1.05, r * 0.9),
			center + Vector2(-r * 1.05, r * 0.9),
		])
		draw_colored_polygon(tri, col)
		tri.append(tri[0])
		draw_polyline(tri, edge if outlined else col, 1.5 if outlined else 1.0, true)
	elif belief == "":
		var dia := PackedVector2Array([
			center + Vector2(0, -r * 1.05),
			center + Vector2(r * 1.05, 0),
			center + Vector2(0, r * 1.05),
			center + Vector2(-r * 1.05, 0),
		])
		draw_colored_polygon(dia, col)
		dia.append(dia[0])
		draw_polyline(dia, edge if outlined else col, 1.5 if outlined else 1.0, true)
	else:
		draw_circle(center, r, col, true, -1.0, true)
		if outlined:
			draw_arc(center, r, 0.0, TAU, 24, edge, 1.5, true)


func _draw_flash(now_s: float) -> void:
	var t := (now_s - _flash_at) / 1.1
	if t < 0.0 or t >= 1.0:
		return
	var r := _map_rect
	var edge := Color(_flash_color.r, _flash_color.g, _flash_color.b, 0.34 * (1.0 - t))
	var clear := Color(edge.r, edge.g, edge.b, 0.0)
	var depth := minf(r.size.x, r.size.y) * 0.3
	_gradient_quad(r.position, Vector2(r.end.x, r.position.y), Vector2(r.end.x, r.position.y + depth), Vector2(r.position.x, r.position.y + depth), edge, clear)
	_gradient_quad(Vector2(r.position.x, r.end.y), r.end, Vector2(r.end.x, r.end.y - depth), Vector2(r.position.x, r.end.y - depth), edge, clear)


func _draw_announcement() -> void:
	var txt := ""
	if _snap.get("announcement") != null:
		txt = str(_snap.get("announcement", ""))
	elif not _paused:
		txt = _announcement
	if txt.is_empty():
		return
	var width := minf(_map_rect.size.x * 0.5 - 90.0, 330.0)
	var line := _fit_text(txt, width - 24.0, 13)
	var box := Rect2(_map_rect.position + Vector2(12, 10), Vector2(width, 46))
	_card(box, Color(0.118, 0.098, 0.039, 0.92), Color(0.988, 0.827, 0.302, 0.4), 12, 10)
	_text_b(box.position + Vector2(12, 18), "ANNONCE OFFICIELLE", 11, WARN)
	_text(box.position + Vector2(12, 36), line, 13, TEXT)


func _draw_toast(now_s: float) -> void:
	if _toast == "" or now_s - _toast_at > 4.2 or not _end.is_empty():
		return
	var w := _font_b.get_string_size(_toast, HORIZONTAL_ALIGNMENT_LEFT, -1, 14).x + 36.0
	var center := Vector2(_map_rect.get_center().x, _map_rect.end.y - 72.0)
	var rect := Rect2(center.x - w * 0.5, center.y - 19.0, w, 38.0)
	_card(rect, Color(0.09, 0.07, 0.08, 0.94), Color(_toast_color.r, _toast_color.g, _toast_color.b, 0.6), 19, 12)
	_text_center(center + Vector2(0, 5), _toast, 14, _toast_color, true)


func _draw_end_card() -> void:
	if _end.is_empty() or _paused or _end_dismissed or _selected != "":
		return
	var agents: Array = _snap.get("agents", [])
	var total := int(_end.get("total", agents.size()))
	var evacuated := int(_end.get("evacuated", total - _active_count(_snap)))
	var trapped := total - evacuated
	var seconds := int(_end.get("ticks", _snap.get("tick", 0))) * TICK_SECONDS
	var by_belief := {}
	for a in agents:
		if bool(a.get("evacuated", false)):
			var key := str(a.get("belief", ""))
			by_belief[key] = int(by_belief.get(key, 0)) + 1

	var c := _map_rect.get_center()
	var box := Rect2(c.x - 210.0, c.y - 118.0, 420.0, 236.0)
	_card(box, Color(0.063, 0.067, 0.086, 0.94), LINE_STRONG, 18, 28)
	var eyebrow := "RUN TERMINÉ · FOULE PIÉGÉE" if trapped > 0 else "ÉVACUATION TERMINÉE"
	_text_center(Vector2(c.x, box.position.y + 36.0), eyebrow, 13, ACCENT, true)
	var big := str(evacuated)
	var small := " / %d" % total
	var big_w := _font_b.get_string_size(big, HORIZONTAL_ALIGNMENT_LEFT, -1, 52).x
	var small_w := _font.get_string_size(small, HORIZONTAL_ALIGNMENT_LEFT, -1, 20).x
	var x := c.x - (big_w + small_w) * 0.5
	_text_b(Vector2(x, box.position.y + 96.0), big, 52, TEXT)
	_text(Vector2(x + big_w, box.position.y + 96.0), small, 20, MUTED)
	var line := "%d personne%s encore sur place après %d s simulées." % [trapped, "s" if trapped > 1 else "", seconds] if trapped > 0 else "Tout le monde est sorti en %d s simulées." % seconds
	_text_center(Vector2(c.x, box.position.y + 130.0), line, 14, MUTED)

	var exits: Array = _plan.get("exits", [])
	var cell := 120.0
	var ex_x := c.x - cell * float(exits.size()) * 0.5
	for exit in exits:
		var eid := str(exit["id"])
		_draw_agent_shape(Vector2(ex_x + 12.0, box.position.y + 165.0), 6.0, eid, BELIEF_COLORS.get(eid, UNKNOWN))
		_text(Vector2(ex_x + 24.0, box.position.y + 170.0), "%d visaient %s" % [int(by_belief.get(eid, 0)), eid], 14, TEXT)
		ex_x += cell
	_text_center(Vector2(c.x, box.position.y + 208.0), "Cliquez le déroulé pour revoir n'importe quel instant.", 13, SUBTLE)


# ------------------------------------------------------------------
# Bas : déroulé (cliquable) + indicateurs I1–I7
# ------------------------------------------------------------------
func _draw_bottom_deck(deck: Rect2) -> void:
	_card(deck, SURFACE)
	var chart_w := deck.size.x * 0.555
	var split := deck.position.x + chart_w
	draw_line(Vector2(split, deck.position.y + 1.0), Vector2(split, deck.end.y - 1.0), LINE, 1.0)

	_text_b(deck.position + Vector2(14, 26), "Déroulé", 15, TEXT)
	var tick := int(_snap.get("tick", 0))
	var note := "Cliquez pour revoir un instant."
	if _paused:
		note = "Vous revoyez t%d. Espace pour reprendre." % tick
	_text(deck.position + Vector2(84, 26), note, 13, MUTED)

	_timeline_rect = Rect2(deck.position.x + 44.0, deck.position.y + 62.0, chart_w - 62.0, deck.size.y - 90.0)
	_draw_timeline(tick)

	var ix := split + 14.0
	var iw := deck.end.x - ix - 14.0
	_text_b(Vector2(ix, deck.position.y + 26.0), "Indicateurs", 15, TEXT)
	_text(Vector2(ix + 92.0, deck.position.y + 26.0), "Cliquez un chiffre : trace.", 13, MUTED)

	var gone := not _snap.is_empty() and _active_count(_snap) == 0
	var items := [
		["I1_consensus", "I1", "Accord", _pct(_ind.get("I1_consensus"))],
		["I2_entropy", "I2", "Hésitation", _dec(_ind.get("I2_entropy"), "")],
		["I3_evacuated", "I3", "Évacués", _pct(_ind.get("I3_evacuated"))],
		["I4_seconds", "I4", "Horloge", _secs(_ind.get("I4_seconds"))],
		["I5_max_density", "I5", "Densité", _dec(_ind.get("I5_max_density"), " /m²")],
		["I6_belief_gap", "I6", "Écart", _pct(_ind.get("I6_belief_gap"))],
		["I7_delay_seconds", "I7", "Délai", _secs(_ind.get("I7_delay_seconds"))],
	]
	_ind_boxes.clear()
	var gap := 6.0
	var cell_w := (iw - gap * 3.0) / 4.0
	var cell_h := (deck.size.y - 50.0 - gap) / 2.0
	for idx in range(items.size()):
		var item: Array = items[idx]
		var key := str(item[0])
		var rect := Rect2(
			ix + float(idx % 4) * (cell_w + gap),
			deck.position.y + 40.0 + float(idx / 4) * (cell_h + gap),
			cell_w,
			cell_h,
		)
		var active := str(_trace.get("indicator", "")) == key
		_card(rect, ACCENT_SOFT if active else SURFACE_2, ACCENT if active else LINE, 10)
		_draw_spark(rect, key, tick)
		_text_b(rect.position + Vector2(9, 18), str(item[1]), 12, ACCENT)
		_text(rect.position + Vector2(29, 18), _fit_text(str(item[2]), cell_w - 34.0, 12), 12, MUTED)
		var shown := "—" if gone and key in UNDEFINED_WHEN_EMPTY else str(item[3])
		_text_b(rect.position + Vector2(9, 40), shown, 16, TEXT)
		_ind_boxes.append({"rect": rect, "key": key})

	var keys := Rect2(ix + 3.0 * (cell_w + gap), deck.position.y + 40.0 + cell_h + gap, cell_w, cell_h)
	_text(keys.position + Vector2(4, 18), "Espace : figer", 12, SUBTLE)
	_text(keys.position + Vector2(4, 36), "Flèches : choisir", 12, SUBTLE)


## Le JSON de Godot rend tous les nombres en flottants : « 54.0 personnes ».
func _num(value: Variant) -> String:
	return "—" if value == null else str(int(value))


func _pct(value: Variant) -> String:
	return "—" if value == null else "%.0f %%" % (float(value) * 100.0)


func _dec(value: Variant, unit: String) -> String:
	return "—" if value == null else ("%.2f" % float(value)).replace(".", ",") + unit


func _secs(value: Variant) -> String:
	return "—" if value == null else "%.0f s" % float(value)


func _draw_spark(rect: Rect2, key: String, tick: int) -> void:
	var ticks: Array = _indicators_by_tick.keys()
	ticks.sort()
	var values: Array[float] = []
	for t in ticks:
		if int(t) > tick:
			break
		var frame: Dictionary = _indicators_by_tick[t]
		if key in UNDEFINED_WHEN_EMPTY and int(frame.get("counts", {}).get("remaining", 1)) == 0:
			continue
		if frame.get(key) != null:
			values.append(float(frame[key]))
	if values.size() < 2:
		return
	var top := 0.000001
	for v in values:
		top = maxf(top, v)
	var line := PackedVector2Array()
	for i in range(values.size()):
		var x := rect.position.x + 1.0 + (rect.size.x - 2.0) * float(i) / float(values.size() - 1)
		line.append(Vector2(x, rect.end.y - 3.0 - values[i] / top * 20.0))
	draw_polyline(line, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.34), 1.25, true)


func _draw_timeline(tick: int) -> void:
	var r := _timeline_rect
	if _timeline.is_empty():
		return
	var series := _timeline.duplicate()
	series.sort_custom(func(p, q): return int(p["tick"]) < int(q["tick"]))
	var max_t := 20
	for pt in series:
		max_t = maxi(max_t, int(pt["tick"]))
	for m in _world_markers:
		max_t = maxi(max_t, int(m["tick"]))
	_timeline_max = max_t
	var total := maxi(1, int(series[0].get("total", 60)))

	draw_line(Vector2(r.position.x, r.end.y), r.end, LINE_STRONG, 1.0)
	draw_line(r.position, Vector2(r.end.x, r.position.y), LINE, 1.0)
	_text_right(Vector2(r.position.x - 6.0, r.end.y + 4.0), "0", 12, SUBTLE)
	_text_right(Vector2(r.position.x - 6.0, r.position.y + 4.0), str(total), 12, SUBTLE)
	var step := 5 if max_t <= 25 else (10 if max_t <= 60 else (20 if max_t <= 120 else 50))
	var t := 0
	while t <= max_t:
		_text_center(Vector2(_tl_x(t), r.end.y + 17.0), "t%d" % t, 12, SUBTLE)
		t += step

	var past := PackedVector2Array()
	var ahead := PackedVector2Array()
	for pt in series:
		var p := Vector2(_tl_x(int(pt["tick"])), _tl_y(int(pt["evacuated"]), total))
		if int(pt["tick"]) <= tick:
			past.append(p)
		if int(pt["tick"]) >= tick:
			ahead.append(p)
	var fill := Color(0.506, 0.549, 0.973, 0.42)
	var clear := Color(fill.r, fill.g, fill.b, 0.0)
	for i in range(1, past.size()):
		var a := past[i - 1]
		var b := past[i]
		if a.y < r.end.y - 0.5 or b.y < r.end.y - 0.5:
			draw_polygon(
				PackedVector2Array([a, b, Vector2(b.x, r.end.y), Vector2(a.x, r.end.y)]),
				PackedColorArray([fill, fill, clear, clear]),
			)
	if ahead.size() > 1:
		draw_polyline(ahead, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.3), 1.5, true)
	if past.size() > 1:
		draw_polyline(past, ACCENT, 2.0, true)

	var by_tick := {}
	for m in _world_markers:
		var mt := int(m["tick"])
		if by_tick.has(mt):
			by_tick[mt]["label"] = "%s + %s" % [by_tick[mt]["label"], m["label"]]
		else:
			by_tick[mt] = {"tick": mt, "label": m["label"], "color": m["color"]}
	var order: Array = by_tick.keys()
	order.sort()
	var row_ends := [-INF, -INF]
	for mt in order:
		var m: Dictionary = by_tick[mt]
		var x := _tl_x(mt)
		var col: Color = m["color"]
		draw_dashed_line(Vector2(x, r.position.y - 4.0), Vector2(x, r.end.y), col, 1.25, 3.0)
		var label := "%s · t%d" % [str(m["label"]), mt]
		var w := _font_b.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
		# Rangée la moins encombrée ; le libellé glisse plutôt que de chevaucher.
		var row := 0 if float(row_ends[0]) <= float(row_ends[1]) else 1
		var y := r.position.y - 20.0 + float(row) * 13.0
		var lx := maxf(x + 4.0, float(row_ends[row]))
		if lx + w > r.end.x:
			lx = r.end.x - w
		_text_b(Vector2(lx, y), label, 12, col)
		row_ends[row] = lx + w + 10.0

	var cx := _tl_x(tick)
	draw_line(Vector2(cx, r.position.y - 4.0), Vector2(cx, r.end.y), TEXT, 1.25)
	if not past.is_empty():
		var dot := past[past.size() - 1]
		draw_circle(dot, 6.0, SURFACE, true, -1.0, true)
		draw_circle(dot, 4.5, TEXT, true, -1.0, true)


func _tl_x(tick: int) -> float:
	return _timeline_rect.position.x + float(tick) / float(maxi(_timeline_max, 1)) * _timeline_rect.size.x


func _tl_y(value: int, total: int) -> float:
	return _timeline_rect.end.y - float(value) / float(total) * _timeline_rect.size.y


# ------------------------------------------------------------------
# Colonne droite : chiffres clés, puis fil OU fiche d'une personne
# ------------------------------------------------------------------
func _draw_rail(view: Vector2) -> void:
	var panel := _rail_rect
	var x := panel.position.x
	_card(panel, SURFACE)

	var agent := _agent_by_id(_selected)
	var content_top := panel.position.y + 46.0
	var y := content_top - _rail_scroll
	if agent.is_empty():
		y = _draw_feed(x, y, view)
	else:
		y = _draw_person(agent, x, y, view)
	_rail_content = y + _rail_scroll - content_top
	_rail_scroll = clampf(_rail_scroll, 0.0, maxf(0.0, _rail_content - (panel.size.y - 60.0)))

	# Ce qui remonte sous l'en-tête est recouvert, pas découpé.
	var hero := Rect2(x, TOP_H + GAP, RAIL_W, HERO_H)
	draw_rect(Rect2(x - 1.0, TOP_H, RAIL_W + 2.0, panel.position.y - TOP_H), BG_SHELL)
	_card(Rect2(x, panel.position.y, RAIL_W, 46.0), SURFACE, LINE, RADIUS)
	draw_rect(Rect2(x + 1.0, panel.position.y + 24.0, RAIL_W - 2.0, 22.0), SURFACE)
	draw_line(Vector2(x, panel.position.y + 46.0), Vector2(x + RAIL_W, panel.position.y + 46.0), LINE, 1.0)
	if agent.is_empty():
		_text_b(Vector2(x + 16, panel.position.y + 29.0), "Ce qui se passe", 15, TEXT)
		if _paused and not _snap.is_empty():
			_text_right(Vector2(x + RAIL_W - 16.0, panel.position.y + 29.0), "jusqu'à t%d" % int(_snap.get("tick", 0)), 13, SUBTLE)
	_draw_hero(hero)


func _draw_hero(hero: Rect2) -> void:
	_card(hero, SURFACE)
	var agents: Array = _snap.get("agents", [])
	var total := agents.size()
	var remaining := _active_count(_snap)
	var evacuated := total - remaining
	var has := total > 0
	_text(hero.position + Vector2(16, 26), "Personnes sorties", 13, MUTED)
	var big := str(evacuated) if has else "—"
	_text_b(hero.position + Vector2(16, 78), big, 50, TEXT)
	if has:
		var w := _font_b.get_string_size(big, HORIZONTAL_ALIGNMENT_LEFT, -1, 50).x
		_text(hero.position + Vector2(22.0 + w, 78), "/ %d" % total, 18, SUBTLE)

	var tick := int(_snap.get("tick", 0))
	var alert := "—"
	if has:
		alert = "%d s" % ((tick - _first_danger_tick) * TICK_SECONDS) if _first_danger_tick >= 0 and tick >= _first_danger_tick else "Calme"
	var px := hero.position.x + 170.0
	_text_b(Vector2(px, hero.position.y + 58.0), str(remaining) if has else "—", 20, TEXT)
	_text(Vector2(px, hero.position.y + 77.0), "encore sur place", 13, MUTED)
	_text_b(Vector2(px + 116.0, hero.position.y + 58.0), alert, 20, TEXT)
	_text(Vector2(px + 116.0, hero.position.y + 77.0), "depuis l'alerte", 13, MUTED)

	var bar := Rect2(hero.position.x + 16.0, hero.end.y - 22.0, hero.size.x - 32.0, 6.0)
	_card(bar, SURFACE_3, Color(0, 0, 0, 0), 3)
	if has and evacuated > 0:
		var fill := Rect2(bar.position, Vector2(bar.size.x * float(evacuated) / float(total), bar.size.y))
		draw_texture_rect(_glow, fill.grow(10.0), false, Color(0.506, 0.549, 0.973, 0.35))
		_card(fill, ACCENT, Color(0, 0, 0, 0), 3)


func _draw_feed(x: float, top: float, view: Vector2) -> float:
	var y := top + 6.0
	var width := RAIL_W - 76.0
	var limit := int(_snap.get("tick", 0)) if _paused else 2147483647
	if _feed.is_empty():
		_para(Vector2(x + 16, y + 6), "Le fil se remplit dès que le moteur envoie des événements.", RAIL_W - 32.0, 14, MUTED)
		return y + 40.0
	var first := true
	for item in _feed:
		var tick := int(item.get("tick", 0))
		if tick > limit:
			continue
		var kind := str(item.get("kind", ""))
		var start := y
		y += 9.0
		var tag := str(item.get("tag", ""))
		var ink := MUTED
		var stripe := Color(0, 0, 0, 0)
		var wash := Color(0, 0, 0, 0)
		match kind:
			"danger":
				ink = DANGER
				stripe = DANGER_LINE
				wash = DANGER_SOFT
			"world":
				ink = WARN
				stripe = BELIEF_COLORS["B"]
				wash = WARN_SOFT
			"talk":
				ink = ACCENT
			"end":
				ink = ACCENT
				stripe = ACCENT
				wash = ACCENT_SOFT
		var lines: Array = []
		if item.has("lines"):
			var people: Dictionary = item["people"]
			tag = "%s · %d PERSONNE%s" % [tag, people.size(), "S" if people.size() > 1 else ""]
			var grouped: Dictionary = item["lines"]
			for text in grouped.keys():
				var n := int(grouped[text])
				lines.append("%s  ×%d" % [text, n] if n > 1 else str(text))
		else:
			lines.append(str(item.get("text", "")))

		var height := 9.0 + 16.0 + 9.0
		var strong := kind == "danger" or kind == "world" or kind == "end"
		for line in lines:
			height += _para_height(str(line), width, 14, strong) + 2.0
		if wash.a > 0.0:
			var band := Rect2(x + 1.0, start, RAIL_W - 2.0, height)
			draw_polygon(
				PackedVector2Array([band.position, Vector2(band.end.x - 90.0, band.position.y), Vector2(band.end.x - 90.0, band.end.y), Vector2(band.position.x, band.end.y)]),
				PackedColorArray([wash, Color(wash.r, wash.g, wash.b, 0.0), Color(wash.r, wash.g, wash.b, 0.0), wash]),
			)
			draw_rect(Rect2(x + 1.0, start, 2.0, height), stripe)
		if not first:
			draw_line(Vector2(x + 1.0, start), Vector2(x + RAIL_W - 1.0, start), LINE, 1.0)
		first = false
		_text(Vector2(x + 16, y + 12), "t%d" % tick, 13, SUBTLE)
		_text_b(Vector2(x + 60, y + 12), tag, 12, ink)
		y += 16.0
		for line in lines:
			y = _para(Vector2(x + 60, y), str(line), width, 14, TEXT, strong) + 2.0
		y += 9.0
		if y > view.y + 40.0:
			break
	return y


func _draw_person(agent: Dictionary, x: float, top: float, view: Vector2) -> float:
	var y := top + 14.0
	var width := RAIL_W - 32.0
	var aid := str(agent["id"])
	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
	var tick := int(_snap.get("tick", 0))

	_draw_agent_shape(Vector2(x + 28, y + 8), 10.0, belief, colour)
	_text_b(Vector2(x + 48, y + 8), "%s · %s" % [aid, str(agent.get("label", agent.get("profile", "Personne")))], 18, TEXT)
	y += 18.0
	var mode_lbl := "Décide avec un modèle de langage (LLM)" if str(agent.get("kind", "")) == "llm" else "Décide selon des règles simples"
	_text(Vector2(x + 48, y + 8), mode_lbl, 13, MUTED)
	y += 22.0

	var target: Variant = agent.get("intention_target")
	var ikind := str(agent.get("intention", "—"))
	var summary := "Est sortie de l'esplanade."
	if not bool(agent.get("evacuated", false)):
		summary = "%s%s · croit en la sortie %s (%.0f %%)" % [
			INTENTION_LABELS.get(ikind, ikind),
			" (%s)" % str(target) if target != null else "",
			belief if belief != "" else "aucune",
			float(agent.get("confidence", 0.0)) * 100.0,
		]
	var sum_h := _para_height(summary, width - 24.0, 14, true) + 18.0
	_card(Rect2(x + 16, y, width, sum_h), SURFACE_2, LINE, 10)
	_para(Vector2(x + 28, y + 8), summary, width - 24.0, 14, TEXT, true)
	y += sum_h + 8.0

	if belief != "" and not _is_open(belief) and not bool(agent.get("evacuated", false)):
		_text_b(Vector2(x + 16, y + 12), "Vise une sortie actuellement fermée", 13, DANGER)
		y += 22.0

	# D2 : la dernière décision à l'instant affiché.
	var decision: Variant = agent.get("last_decision")
	for d in _decisions_by_agent.get(aid, []):
		if int(d.get("tick", 0)) <= tick:
			if typeof(decision) != TYPE_DICTIONARY or decision.is_empty():
				decision = d
			break

	y = _section(x, y, "Pourquoi")
	if typeof(decision) == TYPE_DICTIONARY and not decision.is_empty():
		var d: Dictionary = decision
		var quote := "« %s »" % str(d.get("reason", "—"))
		var q_h := _para_height(quote, width - 26.0, 14) + 16.0
		draw_rect(Rect2(x + 16, y, width, q_h), ACCENT_SOFT)
		draw_rect(Rect2(x + 16, y, 2.0, q_h), ACCENT)
		_para(Vector2(x + 30, y + 7), quote, width - 26.0, 14, TEXT)
		y += q_h + 6.0
		var trig := str(d.get("trigger", "—"))
		_text(Vector2(x + 16, y + 12), "À t%s · %s · %s" % [_num(d.get("tick")), d.get("kind", "?"), TRIGGER_LABELS.get(trig, trig)], 13, MUTED)
		y += 20.0
		if d.get("rule") != null and str(d["rule"]) != str(d.get("reason", "")):
			y = _para(Vector2(x + 16, y), "Règle : %s" % str(d["rule"]), width, 13, ACCENT)
		var retrieved: Array = d.get("retrieved", [])
		if not retrieved.is_empty():
			var first_doc: Variant = retrieved[0]
			var doc_txt := str(first_doc.get("doc_id", first_doc.get("id", "source"))) if typeof(first_doc) == TYPE_DICTIONARY else str(first_doc)
			y = _para(Vector2(x + 16, y), "Source RAG : %s" % doc_txt, width, 13, MUTED)
	else:
		y = _para(Vector2(x + 16, y), "Aucune décision enregistrée à cet instant.", width, 14, MUTED)
	y += 6.0

	y = _section(x, y, "Ce qu'elle croit sur les sorties")
	var beliefs_map: Dictionary = agent.get("beliefs", {})
	for ex_id in ["A", "B", "C"]:
		var b_entry: Dictionary = beliefs_map.get(ex_id, {})
		var conf := float(b_entry.get("confidence", agent.get("confidence", 0.0) if belief == ex_id else 0.0))
		_draw_agent_shape(Vector2(x + 23, y + 8), 6.0, ex_id, BELIEF_COLORS.get(ex_id, ACCENT))
		var bar := Rect2(x + 40, y + 4, width - 78.0, 8)
		_card(bar, SURFACE_3, Color(0, 0, 0, 0), 4)
		if conf > 0.0:
			_card(Rect2(bar.position, Vector2(maxf(8.0, bar.size.x * clampf(conf, 0.0, 1.0)), 8)), BELIEF_COLORS.get(ex_id, ACCENT), Color(0, 0, 0, 0), 4)
		_text_right(Vector2(x + 16 + width, y + 13), "%.0f %%" % (conf * 100.0), 13, TEXT, true)
		y += 22.0
	y += 4.0

	y = _section(x, y, "Ce qu'elle a perçu")
	var perceived: Array = agent.get("perceived", [])
	y = _para(Vector2(x + 16, y), "Aucun signal de danger perçu." if perceived.is_empty() else _join_perceived(perceived), width, 14, MUTED if perceived.is_empty() else TEXT) + 6.0

	y = _section(x, y, "Mémoire et messages reçus")
	var memory: Array = agent.get("memory", [])
	var heard: Array = []
	for h in _heard_by_agent.get(aid, []):
		if int(h.get("tick", 0)) <= tick:
			heard.append(h)
	if memory.is_empty() and heard.is_empty():
		y = _para(Vector2(x + 16, y), "Aucun souvenir ni message reçu.", width, 14, MUTED)
	for h in heard.slice(0, 3):
		_text(Vector2(x + 16, y + 12), "%s · de %s" % [_when(int(h.get("tick", 0))), h.get("from", "?")], 13, SUBTLE)
		y += 18.0
		y = _para(Vector2(x + 16, y), "« %s »" % str(h.get("content", "")), width, 14, TEXT) + 4.0
	for episode in memory:
		if typeof(episode) != TYPE_DICTIONARY or y > view.y + 40.0:
			continue
		var e: Dictionary = episode
		_text(Vector2(x + 16, y + 12), "%s · %s" % [_when(int(e.get("tick", 0))), e.get("kind", "?")], 13, SUBTLE)
		y += 18.0
		y = _para(Vector2(x + 16, y), str(e.get("content", "")), width, 14, TEXT) + 4.0
	return y + 12.0


func _join_perceived(items: Array) -> String:
	var labels := {"smoke": "Voit la fumée", "announcement": "A entendu l'annonce", "missing_kin": "Proche hors de vue"}
	var out := PackedStringArray()
	for item in items:
		var key := str(item)
		if key.begins_with("closed:"):
			out.append("Sait que la sortie %s est fermée" % key.substr(7))
		else:
			out.append(str(labels.get(key, key)))
	return " · ".join(out)


func _section(x: float, y: float, title: String) -> float:
	draw_line(Vector2(x + 16, y + 4), Vector2(x + RAIL_W - 16, y + 4), LINE, 1.0)
	_text_b(Vector2(x + 16, y + 24), title, 13, MUTED)
	return y + 34.0


func _para_height(text: String, width: float, font_size: int, strong: bool = false) -> float:
	var font := _font_b if strong else _font
	return font.get_multiline_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, width, font_size).y


func _para(position: Vector2, text: String, width: float, font_size: int = 14, colour: Color = TEXT, strong: bool = false) -> float:
	var font := _font_b if strong else _font
	draw_multiline_string(
		font,
		position + Vector2(0, font_size),
		text,
		HORIZONTAL_ALIGNMENT_LEFT,
		width,
		font_size,
		-1,
		colour,
	)
	return position.y + _para_height(text, width, font_size, strong) + 2.0


func _when(tick: int) -> String:
	if tick < 0:
		return "J-%d" % int(round(-float(tick) / 8640.0))
	return "t%d" % tick


func _viewport() -> Vector2:
	return get_viewport_rect().size


func _fit() -> void:
	var points: Array = _plan.get("walkable", [])
	if points.size() >= 3:
		var b := Rect2(_vec(points[0]), Vector2.ZERO)
		for p in points:
			b = b.expand(_vec(p))
		_bounds = b
	else:
		_bounds = Rect2(0, 0, float(_plan.get("width", 60.0)), float(_plan.get("height", 40.0)))
	var pad_x := 92.0
	var pad_top := 62.0
	var pad_bottom := 58.0
	var avail := _map_rect.size - Vector2(pad_x * 2.0, pad_top + pad_bottom)
	_px = maxf(minf(avail.x / _bounds.size.x, avail.y / _bounds.size.y), 3.0)
	var height := float(_plan.get("height", 40.0))
	var center := Vector2(_map_rect.get_center().x, _map_rect.position.y + pad_top + avail.y * 0.5)
	_off = Vector2(
		center.x - (_bounds.position.x + _bounds.size.x * 0.5) * _px,
		center.y - (height - _bounds.position.y - _bounds.size.y * 0.5) * _px,
	)


func _to_screen(point: Variant) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(
		_off.x + float(point[0]) * _px,
		_off.y + (height - float(point[1])) * _px,
	)


func _to_screen_v(point: Vector2) -> Vector2:
	return _to_screen([point.x, point.y])


func _to_world(click: Vector2) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(
		(click.x - _off.x) / _px,
		height - (click.y - _off.y) / _px,
	)


func _is_open(exit_id: String) -> bool:
	var open: Array = _snap.get("exits_open", [])
	if open.is_empty():
		return true
	return exit_id in open


func _request_trace(click: Vector2) -> bool:
	if _close_trace_rect.has_point(click) and not _trace.is_empty():
		_trace = {}
		return true
	for box in _ind_boxes:
		var rect: Rect2 = box["rect"]
		if rect.has_point(click):
			var key := str(box["key"])
			_trace = {"indicator": key, "found": false, "reason": "Interrogation du journal…"}
			if _ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
				_send({"type": "trace", "indicator": key})
			elif _ws_url != "ws://127.0.0.1:1":
				_trace_pending_key = key
				_trace_ws.close()
				_trace_ws = WebSocketPeer.new()
				_trace_ws.inbound_buffer_size = 2 * 1024 * 1024
				_trace_ws.connect_to_url(_ws_url)
			return true
	return false


func _poll_trace_ws() -> void:
	if _trace_pending_key.is_empty() and _trace_ws.get_ready_state() == WebSocketPeer.STATE_CLOSED:
		return
	_trace_ws.poll()
	if _trace_ws.get_ready_state() == WebSocketPeer.STATE_OPEN and not _trace_pending_key.is_empty():
		_trace_ws.send_text(JSON.stringify({"type": "trace", "indicator": _trace_pending_key}))
		_trace_pending_key = ""
	while _trace_ws.get_available_packet_count() > 0:
		var parsed: Variant = JSON.parse_string(_trace_ws.get_packet().get_string_from_utf8())
		if typeof(parsed) == TYPE_DICTIONARY and str(parsed.get("type", "")) == "trace":
			_trace = parsed
			_trace_ws.close()
			return


func _draw_trace(view: Vector2) -> void:
	if _trace.is_empty():
		_close_trace_rect = Rect2()
		return
	draw_rect(Rect2(Vector2.ZERO, view), Color(0.024, 0.027, 0.039, 0.68))
	var width: float = minf(680.0, view.x - 48.0)
	var lines: Array[String] = []
	var title := str(_trace.get("indicator", "?"))
	if not bool(_trace.get("found", false)):
		lines.append(str(_trace.get("reason", "Aucune variation significative enregistrée.")))
	else:
		lines.append("Plus forte variation à t%s : %s → %s (%s)." % [
			_num(_trace.get("tick")),
			str(_trace.get("from")),
			str(_trace.get("to")),
			str(_trace.get("delta")),
		])
		for step in _trace.get("events", []):
			lines.append("t%s  #%s  %s" % [_num(step.get("tick")), _num(step.get("seq")), str(step.get("label"))])
			if lines.size() >= 12:
				break
	var height := 74.0
	for line in lines:
		height += _para_height(line, width - 40.0, 14) + 8.0
	var card := Rect2((view - Vector2(width, height)) * 0.5, Vector2(width, height))
	_card(card, SURFACE, LINE_STRONG, 16, 30)
	_text_b(card.position + Vector2(20, 34), "D'où vient ce chiffre ?", 17, TEXT)
	_text(card.position + Vector2(20, 54), title, 13, ACCENT)
	_close_trace_rect = Rect2(card.end.x - 92.0, card.position.y + 12.0, 80.0, 36.0)
	_card(_close_trace_rect, SURFACE_2, LINE_STRONG, 10)
	_text_center(_close_trace_rect.get_center() + Vector2(0, 5), "Fermer", 14, TEXT)
	var y := card.position.y + 68.0
	for i in range(lines.size()):
		y = _para(Vector2(card.position.x + 20.0, y), lines[i], width - 40.0, 14, ACCENT if i == 0 else TEXT, i == 0) + 6.0


func _agent_by_id(agent_id: String) -> Dictionary:
	if agent_id.is_empty():
		return {}
	for agent in _snap.get("agents", []):
		if str(agent["id"]) == agent_id:
			return agent
	return {}


func _text(position: Vector2, text: String, font_size: int = 14, colour: Color = TEXT) -> void:
	draw_string(_font, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _text_b(position: Vector2, text: String, font_size: int = 14, colour: Color = TEXT) -> void:
	draw_string(_font_b, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _text_center(position: Vector2, text: String, font_size: int, colour: Color, strong: bool = false) -> void:
	var font := _font_b if strong else _font
	var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	draw_string(font, position - Vector2(w * 0.5, 0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _text_right(position: Vector2, text: String, font_size: int, colour: Color, strong: bool = false) -> void:
	var font := _font_b if strong else _font
	var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	draw_string(font, position - Vector2(w, 0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP or event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			if _rail_rect.has_point(event.position):
				_rail_scroll = maxf(0.0, _rail_scroll + (48.0 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -48.0))
			return
		if event.button_index == MOUSE_BUTTON_LEFT:
			if not _trace.is_empty():
				if _close_trace_rect.has_point(event.position):
					_trace = {}
				return
			if _scrub_timeline(event.position):
				return
			_last_click_m = _to_world(event.position)
			_select_at(event.position)
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_SPACE:
			_toggle_pause()
		elif event.keycode == KEY_ESCAPE:
			if not _trace.is_empty():
				_trace = {}
			else:
				_selected = ""
		elif event.keycode in [KEY_RIGHT, KEY_DOWN, KEY_LEFT, KEY_UP]:
			var forward: bool = event.keycode in [KEY_RIGHT, KEY_DOWN]
			if event.shift_pressed:
				_scrub_to(int(_snap.get("tick", 0)) + (1 if forward else -1))
			else:
				_cycle_agent(1 if forward else -1)


func _scrub_timeline(click: Vector2) -> bool:
	if not _timeline_rect.grow(8.0).has_point(click) or _snapshots_by_tick.is_empty():
		return false
	var ratio := clampf((click.x - _timeline_rect.position.x) / maxf(1.0, _timeline_rect.size.x), 0.0, 1.0)
	_scrub_to(int(round(ratio * float(_timeline_max))))
	return true


func _scrub_to(target_t: int) -> void:
	var best_t := -1
	var best_diff := 999999
	for k in _snapshots_by_tick.keys():
		var d := absi(int(k) - target_t)
		if d < best_diff:
			best_diff = d
			best_t = int(k)
	if best_t < 0:
		return
	_paused = true
	_toast = ""
	if _pause_btn != null:
		_pause_btn.text = "Reprendre"
	_show(_snapshots_by_tick[best_t], false)


func _cycle_agent(step: int) -> void:
	var active: Array[String] = []
	for a in _snap.get("agents", []):
		if not bool(a.get("evacuated", false)):
			active.append(str(a["id"]))
	if active.is_empty():
		return
	var cur := active.find(_selected)
	var next_i: int = (maxi(0, cur) + step + active.size()) % active.size()
	_selected = active[next_i]
	_rail_scroll = 0.0


func _select_at(click: Vector2) -> void:
	if _request_trace(click):
		return
	if not _map_rect.has_point(click):
		return
	var best := ""
	var best_distance := maxf(0.9 * _px, 16.0)
	var now_s := _now()
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var distance := _to_screen_v(_display_pos(agent, now_s)).distance_to(click)
		if distance < best_distance:
			best_distance = distance
			best = str(agent["id"])
	_end_dismissed = true # la carte de fin ne doit pas cacher les personnes piégées
	_selected = best
	_rail_scroll = 0.0
