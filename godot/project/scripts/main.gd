extends Node2D
## Observatoire Godot 4 de MARÉE (données réelles via WebSocket).
##
## Cohérent avec l'observatoire web :
##   * coque claire neutre (zinc) + carte sombre (#111113), un seul accent indigo ;
##   * aucune palette verte : sorties codées par couleur Okabe-Ito ET par forme
##     (● Sortie A bleu, ■ Sortie B ambre, ▲ Sortie C mauve, ◆ incertain gris) ;
##   * hiérarchie lisible : barre d'état + 3 chiffres clés en haut, légende des
##     sorties + carte centrale + courbe « Déroulé » (cliquable) + bandeau I1–I7,
##     et à droite soit le fil « Ce qui se passe », soit la fiche complète de la
##     personne sélectionnée (au clic ou aux flèches du clavier).

const MARGIN := 16.0
const PANEL_W := 380.0
const HUD_H := 116.0
const BOTTOM_H := 148.0
const BANNER_MS := 9000.0

# --- Palette : coque claire + carte sombre, zéro vert -----------------
const BG_SHELL := Color("#f4f4f5")
const SURFACE := Color("#ffffff")
const SURFACE_2 := Color("#f4f4f5")
const LINE := Color("#e4e4e7")
const LINE_STRONG := Color("#d4d4d8")
const TEXT := Color("#18181b")
const MUTED := Color("#52525b")
const SUBTLE := Color("#63636b")
const ACCENT := Color("#4338ca")
const ACCENT_SOFT := Color("#eef2ff")
const DANGER := Color("#b91c1c")
const DANGER_SOFT := Color("#fef2f2")

const MAP_OUTER := Color("#111113")
const MAP_FLOOR := Color("#18181b")
const MAP_OBSTACLE := Color("#27272a")
const MAP_BORDER := Color("#3f3f46")

# Compatibilité avec les constantes existantes
const BELIEF_COLORS := {
	"A": Color("#56b4e9"), # ● Grand Quai (bleu Okabe-Ito)
	"B": Color("#e69f00"), # ■ Ruelle des Cordiers (ambre Okabe-Ito)
	"C": Color("#cc79a7"), # ▲ Passage des Halles (mauve Okabe-Ito)
}
const EXIT_SYMBOLS := {
	"A": "●",
	"B": "■",
	"C": "▲",
}
const UNKNOWN := Color("#a1a1aa")
const INK := Color("#18181b")
const DIM := Color("#52525b")
const WARN := Color("#b45309")

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
var _ind: Dictionary = {}
var _snapshots_by_tick: Dictionary = {}
var _indicators_by_tick: Dictionary = {}
var _decisions_by_agent: Dictionary = {}
var _heard_by_agent: Dictionary = {}
var _trails: Dictionary = {}
var _packets: Array = []
var _timeline: Array = []
var _world_markers: Array = []
var _feed: Array = []
var _narratives: Array[String] = []
var _selected := ""
var _status := "connexion…"
var _paused := false
var _first_danger_tick := -1
var _font: Font
var _px := 11.0
var _off := Vector2.ZERO
var _map_rect := Rect2()
var _timeline_rect := Rect2()

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
var _preselect := ""
var _debug := false
var _debug_at := -1.0

# --- F6 : zones cliquables des indicateurs I1–I7 ----------------------
var _ind_boxes: Array = []
var _trace: Dictionary = {}
var _close_trace_rect := Rect2()


func _ready() -> void:
	_font = ThemeDB.fallback_font
	_build_inject_ui()
	_screenshot_path = OS.get_environment("MAREE_SCREENSHOT")
	_preselect = OS.get_environment("MAREE_SELECT")
	_debug = OS.get_environment("MAREE_DEBUG") == "1"
	_ws.inbound_buffer_size = 8 * 1024 * 1024
	_ws.outbound_buffer_size = 1 * 1024 * 1024
	_trace_ws.inbound_buffer_size = 2 * 1024 * 1024
	var url := OS.get_environment("MAREE_WS_URL")
	if not url.is_empty():
		_ws_url = url
	_connect_ws()


func _connect_ws(reset_state: bool = false) -> void:
	if reset_state:
		_snap = {}
		_ind = {}
		_snapshots_by_tick.clear()
		_indicators_by_tick.clear()
		_decisions_by_agent.clear()
		_heard_by_agent.clear()
		_trails.clear()
		_packets.clear()
		_timeline.clear()
		_world_markers.clear()
		_feed.clear()
		_paused = false
		if _pause_btn != null:
			_pause_btn.text = "⏸ Figer"
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
	var now_s := Time.get_ticks_msec() / 1000.0
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
		_clear_sel_btn.visible = _selected != ""
	_packets = _packets.filter(func(p): return now_s - float(p.get("t", 0.0)) < 1.8)
	if _debug and now_s > _debug_at:
		_debug_at = now_s + 2.0
		print("debug : %s · tick %s · plan %d · agents %d · fumée %s" % [
			_status, str(_snap.get("tick", "?")), _plan.size(),
			_snap.get("agents", []).size(), str(_snap.get("smoke_active", false)),
		])
	_maybe_screenshot()
	queue_redraw()


func _maybe_screenshot() -> void:
	if _screenshot_path.is_empty() or _screenshot_done:
		return
	if _snap.get("agents", []).is_empty() or not bool(_snap.get("smoke_active", false)):
		return
	if _screenshot_at < 0.0:
		_screenshot_at = Time.get_ticks_msec() / 1000.0 + 1.0
		return
	if Time.get_ticks_msec() / 1000.0 < _screenshot_at:
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
			_run_id = str(message.get("run_id", ""))
			_plan = message.get("plan", {})
			_live = bool(message.get("live", false))
			if _plan.has("smoke") and typeof(_plan["smoke"]) == TYPE_DICTIONARY:
				_world_smoke = _plan["smoke"]
			_apply_live_state()
		"snapshot":
			if not _paused or _snap.is_empty():
				_snap = message
			var t := int(message.get("tick", 0))
			_snapshots_by_tick[t] = message
			_record_trails(message.get("agents", []))
			_record_timeline(message)
			if _preselect != "" and _selected == "" and not _agent_by_id(_preselect).is_empty():
				_selected = _preselect
		"indicators":
			if not _paused or _ind.is_empty():
				_ind = message
			_indicators_by_tick[int(message.get("tick", 0))] = message
		"decision":
			var aid := str(message.get("agent_id", ""))
			if aid != "":
				var arr: Array = _decisions_by_agent.get(aid, [])
				arr.push_front(message)
				if arr.size() > 10:
					arr.resize(10)
				_decisions_by_agent[aid] = arr
				var trig := str(message.get("trigger", ""))
				if trig != "" and trig != "periodique" and trig != "premiere_decision":
					var intent: Dictionary = message.get("intention", {})
					var ikind := str(intent.get("kind", ""))
					var itarget := str(intent.get("target", "")) if intent.get("target") != null else ""
					_push_feed(
						int(message.get("tick", 0)),
						"DÉCISION",
						"%s : %s%s — « %s »" % [
							aid,
							INTENTION_LABELS.get(ikind, ikind),
							" (%s)" % itarget if itarget != "" else "",
							str(message.get("reason", "")),
						]
					)
		"message":
			var sender := str(message.get("from", ""))
			var recipients: Array = message.get("to", [])
			var now_s := Time.get_ticks_msec() / 1000.0
			for r in recipients:
				_packets.append({"from": sender, "to": str(r), "t": now_s})
			_push_feed(
				int(message.get("tick", 0)),
				"PAROLE",
				"%s dit à %d pers. : « %s »" % [sender, recipients.size(), str(message.get("content", ""))]
			)
		"heard":
			var listener := str(message.get("agent_id", ""))
			if listener != "":
				var harr: Array = _heard_by_agent.get(listener, [])
				harr.push_front(message)
				if harr.size() > 8:
					harr.resize(8)
				_heard_by_agent[listener] = harr
		"trace":
			_trace = message
		"world":
			_handle_world(message)
		"injection":
			_note("injecté : %s" % str(message.get("kind", "?")))
		"ack":
			_note("✔ %s en file" % str(message.get("kind", "?")))
		"error":
			_note("✖ %s" % str(message.get("reason", "erreur")))
		"incident":
			var iaid := str(message.get("agent_id", "?"))
			var icause := str(message.get("cause", "?"))
			_note("incident %s : %s" % [iaid, icause])
			_push_feed(int(message.get("tick", 0)), "INCIDENT", "%s : repli règles (%s)" % [iaid, icause])
		"narrative":
			var nline := "t%s — %s" % [message.get("tick"), message.get("text")]
			_narratives.append(nline)
			if _narratives.size() > 3:
				_narratives.pop_front()
			_push_feed(int(message.get("tick", 0)), "RÉCIT", str(message.get("text", "")))
		"end":
			_status = "terminé"
			_push_feed(
				int(message.get("tick", 0)),
				"FIN",
				"Run terminé : %s/%s évacués en %s ticks" % [
					str(message.get("evacuated", "—")),
					str(message.get("total", "—")),
					str(message.get("ticks", "—")),
				]
			)
			# Si tout le monde est sorti au dernier tick en rejeu, positionner
			# l'affichage sur le moment fort (après l'alerte) pour que la carte
			# reste informative, tout en gardant la courbe cliquable.
			if not _live and _active_count(_snap) == 0 and not _snapshots_by_tick.is_empty():
				var pivot := _first_danger_tick + 3 if _first_danger_tick >= 0 else 13
				if _snapshots_by_tick.has(pivot):
					_snap = _snapshots_by_tick[pivot]
					if _indicators_by_tick.has(pivot):
						_ind = _indicators_by_tick[pivot]


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
			_world_markers.append({"tick": t, "label": "Fumée", "color": MUTED})
			_note("fumée visible (t%s)" % t)
			_push_feed(t, "ALERTE", "De la fumée apparaît près de la scène.")
		"announcement":
			_announcement = str(message.get("text", ""))
			_announcement_at = Time.get_ticks_msec()
			_world_markers.append({"tick": t, "label": "Annonce", "color": WARN})
			_note("annonce diffusée")
			_push_feed(t, "ANNONCE", "Haut-parleurs : « %s »" % _announcement)
		"exit_closed":
			var ex := str(message.get("exit", "?"))
			_world_markers.append({"tick": t, "label": "Sortie %s fermée" % ex, "color": DANGER})
			_note("sortie %s fermée" % ex)
			_push_feed(t, "DANGER", "La sortie %s vient de fermer." % ex)


func _record_trails(agents: Array) -> void:
	for a in agents:
		if bool(a.get("evacuated", false)):
			continue
		var pos: Array = a.get("pos", [])
		if pos.size() < 2:
			continue
		var id := str(a.get("id", ""))
		var trail: Array = _trails.get(id, [])
		var pt := Vector2(float(pos[0]), float(pos[1]))
		if trail.is_empty() or (trail.back() as Vector2).distance_to(pt) > 0.05:
			trail.append(pt)
			if trail.size() > 36:
				trail.pop_front()
			_trails[id] = trail


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


func _push_feed(tick: int, tag: String, text: String) -> void:
	_feed.push_front({"tick": tick, "tag": tag, "text": text})
	if _feed.size() > 24:
		_feed.resize(24)


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

	var btn_style := StyleBoxFlat.new()
	btn_style.bg_color = ACCENT
	btn_style.corner_radius_top_left = 8
	btn_style.corner_radius_top_right = 8
	btn_style.corner_radius_bottom_left = 8
	btn_style.corner_radius_bottom_right = 8
	btn_style.content_margin_left = 12
	btn_style.content_margin_right = 12

	var ghost_style := StyleBoxFlat.new()
	ghost_style.bg_color = SURFACE
	ghost_style.border_color = LINE_STRONG
	ghost_style.border_width_left = 1
	ghost_style.border_width_top = 1
	ghost_style.border_width_right = 1
	ghost_style.border_width_bottom = 1
	ghost_style.corner_radius_top_left = 8
	ghost_style.corner_radius_top_right = 8
	ghost_style.corner_radius_bottom_left = 8
	ghost_style.corner_radius_bottom_right = 8
	ghost_style.content_margin_left = 10
	ghost_style.content_margin_right = 10

	_pause_btn = Button.new()
	_pause_btn.text = "⏸ Figer"
	_pause_btn.position = Vector2(MARGIN + 460.0, 14.0)
	_pause_btn.custom_minimum_size = Vector2(96, 36)
	_pause_btn.add_theme_stylebox_override("normal", ghost_style)
	_pause_btn.add_theme_color_override("font_color", TEXT)
	_pause_btn.pressed.connect(_toggle_pause)
	layer.add_child(_pause_btn)

	_replay_btn = Button.new()
	_replay_btn.text = "↻ Rejouer"
	_replay_btn.position = Vector2(MARGIN + 562.0, 14.0)
	_replay_btn.custom_minimum_size = Vector2(96, 36)
	_replay_btn.add_theme_stylebox_override("normal", ghost_style)
	_replay_btn.add_theme_color_override("font_color", TEXT)
	_replay_btn.pressed.connect(func(): _connect_ws(true))
	layer.add_child(_replay_btn)

	_toggle = Button.new()
	_toggle.text = "⚡ Intervenir ▾"
	_toggle.position = Vector2(MARGIN + 664.0, 14.0)
	_toggle.custom_minimum_size = Vector2(138, 36)
	_toggle.add_theme_stylebox_override("normal", btn_style)
	_toggle.add_theme_color_override("font_color", Color.WHITE)
	_toggle.pressed.connect(_toggle_panel)
	layer.add_child(_toggle)

	_clear_sel_btn = Button.new()
	_clear_sel_btn.text = "← Retour au fil"
	_clear_sel_btn.position = Vector2(MARGIN + 820.0, 14.0)
	_clear_sel_btn.custom_minimum_size = Vector2(130, 36)
	_clear_sel_btn.add_theme_stylebox_override("normal", ghost_style)
	_clear_sel_btn.add_theme_color_override("font_color", ACCENT)
	_clear_sel_btn.visible = false
	_clear_sel_btn.pressed.connect(func(): _selected = "")
	layer.add_child(_clear_sel_btn)

	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = SURFACE
	panel_style.border_color = LINE_STRONG
	panel_style.border_width_left = 1
	panel_style.border_width_top = 1
	panel_style.border_width_right = 1
	panel_style.border_width_bottom = 1
	panel_style.corner_radius_top_left = 10
	panel_style.corner_radius_top_right = 10
	panel_style.corner_radius_bottom_left = 10
	panel_style.corner_radius_bottom_right = 10
	panel_style.content_margin_left = 14
	panel_style.content_margin_right = 14
	panel_style.content_margin_top = 12
	panel_style.content_margin_bottom = 12

	_panel = PanelContainer.new()
	_panel.position = Vector2(MARGIN + 520.0, 56.0)
	_panel.custom_minimum_size = Vector2(320, 0)
	_panel.add_theme_stylebox_override("panel", panel_style)
	_panel.visible = false
	layer.add_child(_panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	_panel.add_child(box)

	var title := Label.new()
	title.text = "Intervenir dans la simulation"
	title.add_theme_font_size_override("font_size", 14)
	title.add_theme_color_override("font_color", TEXT)
	box.add_child(title)

	_announce_edit = LineEdit.new()
	_announce_edit.text = "Évacuation immédiate, sortie B"
	_announce_edit.tooltip_text = "Texte de l'annonce diffusée aux agents"
	box.add_child(_announce_edit)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	box.add_child(row)
	var announce := Button.new()
	announce.text = "Annoncer"
	announce.pressed.connect(_inject_announcement)
	row.add_child(announce)
	_buttons.append(announce)

	_exit_pick = OptionButton.new()
	for exit_id in ["A", "B", "C"]:
		_exit_pick.add_item(exit_id)
	row.add_child(_exit_pick)
	_buttons.append(_exit_pick)

	var close := Button.new()
	close.text = "Fermer"
	close.pressed.connect(_inject_exit_closed)
	row.add_child(close)
	_buttons.append(close)

	var smoke := Button.new()
	smoke.text = "Fumée ici (après clic sur la carte)"
	smoke.pressed.connect(_inject_smoke)
	box.add_child(smoke)
	_buttons.append(smoke)

	_hint = Label.new()
	_hint.text = "connexion…"
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint.custom_minimum_size = Vector2(292, 0)
	_hint.add_theme_font_size_override("font_size", 12)
	_hint.add_theme_color_override("font_color", MUTED)
	box.add_child(_hint)


func _toggle_panel() -> void:
	_panel.visible = not _panel.visible
	_toggle.text = "⚡ Fermer ▴" if _panel.visible else "⚡ Intervenir ▾"


func _toggle_pause() -> void:
	_paused = not _paused
	if _pause_btn != null:
		_pause_btn.text = "▶ Reprendre" if _paused else "⏸ Figer"


func _apply_live_state() -> void:
	for button in _buttons:
		button.disabled = not _live
	if _live:
		_hint.text = "mode direct : cliquez la carte puis « Fumée ici »"
		_hint.add_theme_color_override("font_color", MUTED)
	else:
		_hint.text = "rejeu : aucune injection possible (lancez maree live)"
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
# Dessin principal : coque claire + carte sombre + déroulé + panneau
# ------------------------------------------------------------------
func _draw() -> void:
	var view := _viewport()
	draw_rect(Rect2(Vector2.ZERO, view), BG_SHELL)
	_layout_buttons(view)
	_draw_topbar(view)

	if _plan.is_empty():
		_draw_empty_state(view)
		return

	_fit(view)
	_draw_legend_strip()
	_draw_world()
	_draw_density()
	_draw_smoke()
	_draw_selected_trail()
	_draw_packets()
	_draw_agents()
	_draw_announcement()
	_draw_bottom_deck(view)
	_draw_inspector(view)
	_draw_trace(view)


func _layout_buttons(view: Vector2) -> void:
	var right_edge := view.x - PANEL_W - MARGIN
	if _toggle != null:
		_toggle.position = Vector2(right_edge - 138.0, 14.0)
	if _replay_btn != null:
		_replay_btn.position = Vector2(right_edge - 240.0, 14.0)
	if _pause_btn != null:
		_pause_btn.position = Vector2(right_edge - 342.0, 14.0)
	if _panel != null:
		_panel.position = Vector2(max(MARGIN, right_edge - 320.0), 58.0)
	if _clear_sel_btn != null:
		_clear_sel_btn.position = Vector2(view.x - 146.0, 14.0)


func _draw_topbar(view: Vector2) -> void:
	draw_rect(Rect2(0, 0, view.x, 62), SURFACE)
	draw_line(Vector2(0, 62), Vector2(view.x, 62), LINE, 1.0)

	# Marque
	draw_rect(Rect2(MARGIN, 14, 34, 34), TEXT)
	_text(Vector2(MARGIN + 8, 36), "≈", 20, Color.WHITE)
	_text(Vector2(MARGIN + 44, 29), "MARÉE", 16, TEXT)
	var subtitle := "Port-Aubel · run « %s »" % _run_id if _run_id != "" else "Observatoire d'évacuation de Port-Aubel"
	_text(Vector2(MARGIN + 44, 46), subtitle, 12, MUTED)

	# Pastille d'état + Horloge + 3 KPIs
	var mode_txt := "Simulation en direct" if _live else ("Run terminé" if _status == "terminé" else ("Rejeu d'un run" if not _plan.is_empty() else _status))
	var pill_col := DANGER_SOFT if _live else ACCENT_SOFT
	var pill_ink := DANGER if _live else ACCENT
	var pill_w := _font.get_string_size(mode_txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 20.0
	var pill_x := 256.0
	draw_rect(Rect2(pill_x, 18, pill_w, 26), pill_col)
	_text(Vector2(pill_x + 10, 36), mode_txt, 12, pill_ink)

	var tick := int(_snap.get("tick", 0))
	var sim_time := str(_snap.get("sim_time", "0:00"))
	var agents: Array = _snap.get("agents", [])
	var total := agents.size()
	var remaining := _active_count(_snap)
	var evacuated := total - remaining
	var delay_s := float(_ind.get("I7_delay_seconds", 0.0))

	var kx := pill_x + pill_w + 16.0
	_text(Vector2(kx, 26), "TEMPS SIMULÉ", 10, SUBTLE)
	_text(Vector2(kx, 45), "%s · t%d" % [sim_time, tick], 14, TEXT)

	var kpi2_x := kx + 102.0
	_text(Vector2(kpi2_x, 26), "SORTIES", 10, SUBTLE)
	_text(Vector2(kpi2_x, 45), "%d / %d" % [evacuated, total] if total > 0 else "—", 14, ACCENT)

	var kpi3_x := kpi2_x + 84.0
	_text(Vector2(kpi3_x, 26), "SUR PLACE", 10, SUBTLE)
	_text(Vector2(kpi3_x, 45), "%d" % remaining if total > 0 else "—", 14, TEXT)

	var kpi4_x := kpi3_x + 76.0
	if kpi4_x + 74.0 < view.x - PANEL_W - 350.0:
		_text(Vector2(kpi4_x, 26), "ALERTE", 10, SUBTLE)
		_text(Vector2(kpi4_x, 45), ("+%.0f s" % delay_s) if delay_s > 0.0 else "Calme", 14, TEXT)


func _draw_empty_state(view: Vector2) -> void:
	var card := Rect2(MARGIN, 78, view.x - PANEL_W - MARGIN * 2.0, view.y - 94)
	_draw_card(card, MAP_OUTER)
	var box := Rect2(card.position.x + card.size.x * 0.5 - 230, card.position.y + card.size.y * 0.5 - 80, 460, 160)
	_draw_card(box, SURFACE)
	_text(box.position + Vector2(24, 38), "En attente d'une simulation (%s)" % _status, 16, TEXT)
	_para(
		box.position + Vector2(24, 62),
		"Ce client n'invente aucune donnée. Lancez dans un terminal :\n• uv run maree serve --run-id demo_replay\n• ou uv run maree live",
		box.size.x - 48.0,
		13,
		MUTED,
	)


func _draw_legend_strip() -> void:
	var strip := Rect2(_map_rect.position.x, 72, _map_rect.size.x, 38)
	_draw_card(strip, SURFACE)
	_text(strip.position + Vector2(14, 24), "Qui va où ?", 14, TEXT)

	var counts := {"A": 0, "B": 0, "C": 0, "": 0}
	for a in _snap.get("agents", []):
		if bool(a.get("evacuated", false)):
			continue
		var b := str(a.get("belief", ""))
		counts[b if counts.has(b) else ""] += 1

	var items := [
		["A", "Sortie A · Grand Quai", BELIEF_COLORS["A"]],
		["B", "Sortie B · Ruelle", BELIEF_COLORS["B"]],
		["C", "Sortie C · Halles", BELIEF_COLORS["C"]],
		["", "Sans sortie choisie", UNKNOWN],
	]
	var ix := strip.position.x + 125.0
	var step_w := (strip.size.x - 135.0) / 4.0
	for item in items:
		var key := str(item[0])
		var label := str(item[1])
		var col: Color = item[2]
		_draw_agent_shape(Vector2(ix + 10, strip.position.y + 19), 6.0, key, col)
		var open_tag := "" if (key == "" or _is_open(key)) else " (FERMÉE)"
		_text(Vector2(ix + 24, strip.position.y + 24), "%s%s : %d" % [label, open_tag, counts.get(key, 0)], 12, DANGER if open_tag != "" else TEXT)
		ix += step_w


func _draw_world() -> void:
	_draw_card(_map_rect, MAP_OUTER)
	var walkable := PackedVector2Array()
	for point in _plan.get("walkable", []):
		walkable.append(_to_screen(point))
	if walkable.size() >= 3:
		draw_colored_polygon(walkable, MAP_FLOOR)
		for i in range(walkable.size()):
			draw_line(walkable[i], walkable[(i + 1) % walkable.size()], MAP_BORDER, 1.5)

	# Grille 10 m
	var w_m := float(_plan.get("width", 60.0))
	var h_m := float(_plan.get("height", 40.0))
	for x in range(10, int(w_m), 10):
		draw_line(_to_screen([x, 0]), _to_screen([x, h_m]), Color(1, 1, 1, 0.04), 1.0)
	for y in range(10, int(h_m), 10):
		draw_line(_to_screen([0, y]), _to_screen([w_m, y]), Color(1, 1, 1, 0.04), 1.0)

	# Zones nommées
	for z in _plan.get("zones", []):
		if bool(z.get("hidden", false)):
			continue
		var zpts: Array = z.get("polygon", [])
		if zpts.size() < 3:
			continue
		var center := Vector2.ZERO
		for pt in zpts:
			center += _to_screen(pt)
		center /= float(zpts.size())
		_text(center - Vector2(28, 0), str(z.get("label", z.get("id", ""))), 11, Color(0.85, 0.85, 0.88, 0.34))

	# Obstacles
	for obstacle in _plan.get("obstacles", []):
		var polygon := PackedVector2Array()
		var center := Vector2.ZERO
		for point in obstacle.get("polygon", []):
			var sp := _to_screen(point)
			polygon.append(sp)
			center += sp
		if polygon.size() >= 3:
			center /= float(polygon.size())
			draw_colored_polygon(polygon, MAP_OBSTACLE)
			for i in range(polygon.size()):
				draw_line(polygon[i], polygon[(i + 1) % polygon.size()], Color("#52525b"), 1.0)
			var kind := str(obstacle.get("kind", ""))
			if kind in ["scene", "tour", "fontaine"]:
				_text(center - Vector2(20, -4), str(obstacle.get("id", kind)).to_upper(), 10, Color("#d4d4d8"))

	# Sorties (couleur Okabe-Ito de la sortie, ou rouge si fermée — zéro vert)
	for exit in _plan.get("exits", []):
		var eid := str(exit["id"])
		var a := _to_screen(exit["a"])
		var b := _to_screen(exit["b"])
		var open := _is_open(eid)
		var col: Color = BELIEF_COLORS.get(eid, Color.WHITE) if open else Color("#ef4444")
		draw_line(a, b, col, 8.0)
		var mid := (a + b) * 0.5
		var sym := str(EXIT_SYMBOLS.get(eid, ""))
		var lbl := "%s Sortie %s%s" % [sym, eid, "" if open else " (FERMÉE)"]
		var lw := _font.get_string_size(lbl, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 14.0
		var lx := clampf(mid.x - lw * 0.5, _map_rect.position.x + 8.0, _map_rect.end.x - lw - 8.0)
		var ly := mid.y - 26.0 if mid.y < _map_rect.position.y + _map_rect.size.y * 0.5 else mid.y + 8.0
		draw_rect(Rect2(lx, ly, lw, 20), Color(0.09, 0.09, 0.11, 0.92))
		draw_rect(Rect2(lx, ly, lw, 20), col, false, 1.2)
		_text(Vector2(lx + 7, ly + 14), lbl, 12, Color("#fafafa"))


func _draw_density() -> void:
	for cell in _snap.get("density_grid", []):
		var n := int(cell.get("n", 0))
		if n < 2:
			continue
		var origin := _to_screen([float(cell["x"]), float(cell["y"]) + 1.0])
		var alpha: float = min(0.12 * float(n), 0.45)
		draw_rect(Rect2(origin, Vector2(_px, _px)), Color(0.98, 0.57, 0.24, alpha))


func _draw_selected_trail() -> void:
	if _selected == "" or not _trails.has(_selected):
		return
	var trail: Array = _trails[_selected]
	if trail.size() < 2:
		return
	for i in range(1, trail.size()):
		var p0 := _to_screen([trail[i - 1].x, trail[i - 1].y])
		var p1 := _to_screen([trail[i].x, trail[i].y])
		draw_line(p0, p1, Color("#a5b4fc"), 2.0)


func _draw_packets() -> void:
	var now_s := Time.get_ticks_msec() / 1000.0
	for pkt in _packets:
		var a := _agent_by_id(str(pkt.get("from", "")))
		var b := _agent_by_id(str(pkt.get("to", "")))
		if a.is_empty() or b.is_empty() or bool(a.get("evacuated", false)) or bool(b.get("evacuated", false)):
			continue
		var pa := _to_screen(a["pos"])
		var pb := _to_screen(b["pos"])
		var phase := clampf((now_s - float(pkt.get("t", 0.0))) / 1.8, 0.0, 1.0)
		draw_line(pa, pb, Color(0.65, 0.71, 0.99, 0.48), 1.2)
		draw_circle(pa.lerp(pb, phase), 3.0, Color("#e0e7ff"))


func _draw_agents() -> void:
	var radius := clampf(0.36 * _px, 5.0, 8.0)
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var position := _to_screen(agent["pos"])
		var belief := str(agent.get("belief", ""))
		var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
		var aid := str(agent["id"])
		if _selected != "" and aid != _selected:
			colour = Color(colour.r, colour.g, colour.b, 0.38)
		_draw_agent_shape(position, radius, belief, colour)
		if belief != "" and not _is_open(belief):
			draw_arc(position, radius + 3.5, 0.0, TAU, 20, Color("#ef4444"), 1.8)
		if aid == _selected:
			draw_arc(position, radius + 6.0, 0.0, TAU, 24, Color.WHITE, 2.2)
			_text(position + Vector2(radius + 7.0, 4.0), aid, 12, Color.WHITE)


func _draw_agent_shape(center: Vector2, r: float, belief: String, col: Color) -> void:
	if belief == "B":
		draw_rect(Rect2(center - Vector2(r * 0.85, r * 0.85), Vector2(r * 1.7, r * 1.7)), col)
	elif belief == "C":
		var tri := PackedVector2Array([
			center + Vector2(0, -r * 1.1),
			center + Vector2(r * 1.05, r * 0.9),
			center + Vector2(-r * 1.05, r * 0.9),
		])
		draw_colored_polygon(tri, col)
	elif belief == "":
		var dia := PackedVector2Array([
			center + Vector2(0, -r * 1.05),
			center + Vector2(r * 1.05, 0),
			center + Vector2(0, r * 1.05),
			center + Vector2(-r * 1.05, 0),
		])
		draw_colored_polygon(dia, col)
	else:
		draw_circle(center, r, col)


func _draw_smoke() -> void:
	var smoke: Dictionary = _snap.get("smoke", {})
	if smoke.is_empty() or not bool(_snap.get("smoke_active", false)):
		if not bool(_snap.get("smoke_active", false)):
			return
		smoke = _world_smoke
	if smoke.is_empty():
		return
	var position = smoke.get("position", [])
	if typeof(position) != TYPE_ARRAY or position.size() < 2:
		return
	var centre := _to_screen(position)
	var radius_m := float(smoke.get("radius", 0.0))
	if radius_m <= 0.0:
		return
	var radius := radius_m * _px
	draw_circle(centre, radius, Color(0.82, 0.82, 0.86, 0.22))
	for ring in [0.5, 0.78, 1.0]:
		draw_arc(centre, radius * float(ring), 0.0, TAU, 48, Color(0.92, 0.92, 0.95, 0.28), 1.2)
	_text(centre + Vector2(-22, 4), "FUMÉE", 12, Color("#fafafa"))


func _draw_announcement() -> void:
	var txt := _announcement
	if txt.is_empty() and _snap.get("announcement") != null:
		txt = str(_snap.get("announcement", ""))
	if txt.is_empty():
		return
	var box := Rect2(_map_rect.position.x + 12.0, _map_rect.end.y - 42.0, min(_map_rect.size.x - 24.0, 460.0), 32.0)
	draw_rect(box, Color(0.09, 0.09, 0.11, 0.94))
	draw_rect(Rect2(box.position, Vector2(4.0, box.size.y)), Color("#fbbf24"))
	_text(box.position + Vector2(12, 20), "Annonce : %s" % txt, 13, Color("#fafafa"))


# ------------------------------------------------------------------
# Bandeau bas : Courbe « Déroulé » (cliquable) + Indicateurs I1–I7
# ------------------------------------------------------------------
func _draw_bottom_deck(view: Vector2) -> void:
	var deck := Rect2(MARGIN, view.y - BOTTOM_H - MARGIN * 0.5, view.x - PANEL_W - MARGIN * 2.0, BOTTOM_H)
	_draw_card(deck, SURFACE)

	# Partie gauche : courbe Déroulé
	var chart_w := maxf(220.0, deck.size.x * 0.46)
	_text(deck.position + Vector2(14, 22), "Déroulé (cliquez pour revoir un tick)", 13, TEXT)
	_timeline_rect = Rect2(deck.position.x + 36.0, deck.position.y + 32.0, chart_w - 50.0, deck.size.y - 52.0)
	draw_line(_timeline_rect.position + Vector2(0, _timeline_rect.size.y), _timeline_rect.end, LINE_STRONG, 1.0)
	draw_line(_timeline_rect.position, _timeline_rect.position + Vector2(0, _timeline_rect.size.y), LINE_STRONG, 1.0)

	if not _timeline.is_empty():
		var max_t := 20
		for pt in _timeline:
			max_t = maxi(max_t, int(pt["tick"]))
		var total := maxi(1, int(_timeline[0].get("total", 60)))
		var prev := Vector2.ZERO
		for i in range(_timeline.size()):
			var pt: Dictionary = _timeline[i]
			var px := _timeline_rect.position.x + (float(pt["tick"]) / float(max_t)) * _timeline_rect.size.x
			var py := _timeline_rect.end.y - (float(pt["evacuated"]) / float(total)) * _timeline_rect.size.y
			var cur := Vector2(px, py)
			if i > 0:
				draw_line(prev, cur, ACCENT, 2.2)
			prev = cur
		var cur_t := int(_snap.get("tick", 0))
		var cx := _timeline_rect.position.x + (float(cur_t) / float(max_t)) * _timeline_rect.size.x
		draw_line(Vector2(cx, _timeline_rect.position.y), Vector2(cx, _timeline_rect.end.y), TEXT, 1.2)
		_text(Vector2(_timeline_rect.position.x, _timeline_rect.end.y + 14.0), "t0", 11, SUBTLE)
		_text(Vector2(_timeline_rect.end.x - 20.0, _timeline_rect.end.y + 14.0), "t%d" % max_t, 11, SUBTLE)

	# Partie droite : les 7 indicateurs scientifiques I1 à I7 (cliquables)
	var ind_x := deck.position.x + chart_w + 10.0
	var ind_w := deck.size.x - chart_w - 22.0
	draw_line(Vector2(ind_x - 8.0, deck.position.y + 10.0), Vector2(ind_x - 8.0, deck.end.y - 10.0), LINE, 1.0)
	_text(Vector2(ind_x, deck.position.y + 22.0), "Indicateurs scientifiques (cliquez un chiffre pour voir sa trace)", 13, TEXT)

	_ind_boxes.clear()
	var items := [
		["I1_consensus", "I1 Accord", "%.0f %%" % (float(_ind.get("I1_consensus", 0.0)) * 100.0)],
		["I2_entropy", "I2 Hésitation", "%.2f" % float(_ind.get("I2_entropy", 0.0))],
		["I3_evacuated", "I3 Évacués", "%.0f %%" % (float(_ind.get("I3_evacuated", 0.0)) * 100.0)],
		["I4_seconds", "I4 Horloge", "%.0f s" % float(_ind.get("I4_seconds", 0.0))],
		["I5_max_density", "I5 Densité", "%.2f/m²" % float(_ind.get("I5_max_density", 0.0))],
		["I6_belief_gap", "I6 Écart", "%.0f %%" % (float(_ind.get("I6_belief_gap", 0.0)) * 100.0)],
		["I7_delay_seconds", "I7 Délai", "%.0f s" % float(_ind.get("I7_delay_seconds", 0.0))],
	]
	var cols := 4
	var cell_w := maxf(82.0, ind_w / float(cols))
	var cell_h := 46.0
	for idx in range(items.size()):
		var item: Array = items[idx]
		var col_i := idx % cols
		var row_i := int(idx / cols)
		var bx := ind_x + float(col_i) * cell_w
		var by := deck.position.y + 32.0 + float(row_i) * (cell_h + 6.0)
		var rect := Rect2(bx, by, cell_w - 6.0, cell_h)
		var active := str(_trace.get("indicator", "")) == str(item[0])
		draw_rect(rect, ACCENT_SOFT if active else SURFACE_2)
		draw_rect(rect, ACCENT if active else LINE, false, 1.0)
		_text(rect.position + Vector2(8, 17), str(item[1]), 11, ACCENT if active else MUTED)
		_text(rect.position + Vector2(8, 36), str(item[2]), 14, TEXT)
		_ind_boxes.append({"rect": rect, "key": str(item[0])})


# ------------------------------------------------------------------
# Panneau latéral droit : Fil des événements OU Fiche d'une personne
# ------------------------------------------------------------------
func _draw_inspector(view: Vector2) -> void:
	var x := view.x - PANEL_W
	var panel_rect := Rect2(x, 62, PANEL_W, view.y - 62)
	draw_rect(panel_rect, SURFACE)
	draw_line(Vector2(x, 62), Vector2(x, view.y), LINE, 1.0)

	var width := PANEL_W - 32.0
	var agent := _agent_by_id(_selected)
	if agent.is_empty():
		var fy := 92.0
		_text(Vector2(x + 16, fy), "Ce qui se passe", 16, TEXT)
		fy += 20.0
		_para(
			Vector2(x + 16, fy),
			"Cliquez sur une personne sur la carte (ou utilisez les flèches ◀ ▶ du clavier) pour ouvrir son raisonnement.",
			width,
			12,
			MUTED,
		)
		fy += 42.0
		draw_line(Vector2(x + 16, fy), Vector2(x + PANEL_W - 16, fy), LINE, 1.0)
		fy += 14.0
		if _feed.is_empty():
			_text(Vector2(x + 16, fy + 14), "Aucun événement reçu pour l'instant.", 12, SUBTLE)
			return
		for item in _feed:
			if fy > view.y - 36.0:
				break
			var tag_line := "t%d · %s" % [int(item.get("tick", 0)), str(item.get("tag", ""))]
			_text(Vector2(x + 16, fy + 12), tag_line, 11, ACCENT)
			fy += 16.0
			fy = _para(Vector2(x + 16, fy), str(item.get("text", "")), width, 12, TEXT)
			fy += 8.0
		return

	# --- Fiche de la personne sélectionnée --------------------------
	var y := 90.0
	var aid := str(agent["id"])
	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)

	_draw_agent_shape(Vector2(x + 26, y - 5), 9.0, belief, colour)
	_text(Vector2(x + 42, y), "%s · %s" % [aid, str(agent.get("label", agent.get("profile", "Personne")))], 16, TEXT)
	y += 20.0
	var mode_lbl := "Modèle de langage (LLM)" if str(agent.get("kind", "")) == "llm" else "Règles simples"
	_text(Vector2(x + 16, y), "Profil %s · %s" % [str(agent.get("profile", "?")), mode_lbl], 12, MUTED)
	y += 22.0

	# Résumé de l'intention et de la croyance
	var target: Variant = agent.get("intention_target")
	var ikind := str(agent.get("intention", "—"))
	var summary := "%s%s · croit en la sortie %s (%.0f %%)" % [
		INTENTION_LABELS.get(ikind, ikind),
		" (%s)" % str(target) if target != null else "",
		belief if belief != "" else "aucune",
		float(agent.get("confidence", 0.0)) * 100.0,
	]
	draw_rect(Rect2(x + 16, y - 4, width, 42), SURFACE_2)
	y = _para(Vector2(x + 24, y + 2), summary, width - 16.0, 12, TEXT) + 12.0

	if belief != "" and not _is_open(belief):
		_text(Vector2(x + 16, y), "⚠ Vise une sortie actuellement fermée", 12, DANGER)
		y += 18.0

	# Barres de confiance par sortie (A, B, C)
	y = _section(x, y, "Carte mentale des sorties")
	var beliefs_map: Dictionary = agent.get("beliefs", {})
	for ex_id in ["A", "B", "C"]:
		var b_entry: Dictionary = beliefs_map.get(ex_id, {})
		var conf := float(b_entry.get("confidence", agent.get("confidence", 0.0) if belief == ex_id else 0.0))
		_text(Vector2(x + 16, y + 11), "Sortie %s" % ex_id, 12, MUTED)
		var bar_bg := Rect2(x + 82, y + 2, width - 118.0, 10)
		draw_rect(bar_bg, SURFACE_2)
		draw_rect(Rect2(bar_bg.position, Vector2(bar_bg.size.x * clampf(conf, 0.0, 1.0), 10)), BELIEF_COLORS.get(ex_id, ACCENT))
		_text(Vector2(x + width - 22, y + 11), "%.0f%%" % (conf * 100.0), 12, TEXT)
		y += 18.0
	y += 6.0

	# Signaux perçus
	var perceived: Array = agent.get("perceived", [])
	_text(Vector2(x + 16, y + 10), "Perçu : %s" % ("aucun signal" if perceived.is_empty() else _join(perceived)), 12, MUTED)
	y += 24.0

	# D2 : Dernière décision (depuis l'instantané OU le flux `decision`)
	var decision: Variant = agent.get("last_decision")
	if (typeof(decision) != TYPE_DICTIONARY or decision.is_empty()) and _decisions_by_agent.has(aid):
		var dlist: Array = _decisions_by_agent[aid]
		if not dlist.is_empty():
			decision = dlist[0]

	y = _section(x, y, "Pourquoi cette décision")
	if typeof(decision) == TYPE_DICTIONARY and not decision.is_empty():
		var d: Dictionary = decision
		var trig := str(d.get("trigger", "—"))
		_text(
			Vector2(x + 16, y + 10),
			"t%s · %s · %s" % [d.get("tick", "?"), d.get("kind", "?"), TRIGGER_LABELS.get(trig, trig)],
			11,
			SUBTLE,
		)
		y += 18.0
		y = _para(Vector2(x + 16, y), "« %s »" % str(d.get("reason", "—")), width, 12, TEXT)
		if d.get("rule") != null:
			y = _para(Vector2(x + 16, y), "Règle : %s" % str(d["rule"]), width, 11, ACCENT)
		var retrieved: Array = d.get("retrieved", [])
		if not retrieved.is_empty():
			var first_doc: Variant = retrieved[0]
			var doc_txt := str(first_doc.get("doc_id", first_doc.get("id", "source"))) if typeof(first_doc) == TYPE_DICTIONARY else str(first_doc)
			y = _para(Vector2(x + 16, y), "Source RAG : %s" % doc_txt, width, 11, MUTED)
	else:
		y = _para(Vector2(x + 16, y), "Aucune décision enregistrée pour l'instant.", width, 12, SUBTLE)
	y += 8.0

	# Paroles entendues ou Mémoire (D2)
	y = _section(x, y, "Mémoire & messages reçus")
	var memory: Array = agent.get("memory", [])
	var heard: Array = _heard_by_agent.get(aid, [])
	if memory.is_empty() and heard.is_empty():
		y = _para(Vector2(x + 16, y), "Aucun souvenir ni message reçu.", width, 12, SUBTLE)
	for h in heard.slice(0, 2):
		if y > view.y - 36.0:
			break
		y = _para(Vector2(x + 16, y), "t%s de %s : « %s »" % [h.get("tick", "?"), h.get("from", "?"), h.get("content", "")], width, 12, TEXT)
	for episode in memory:
		if typeof(episode) != TYPE_DICTIONARY or y > view.y - 36.0:
			continue
		var e: Dictionary = episode
		var when := _when(int(e.get("tick", 0)))
		_text(Vector2(x + 16, y + 10), "%s · %s (%s)" % [when, e.get("kind", "?"), e.get("source", "?")], 11, SUBTLE)
		y += 14.0
		y = _para(Vector2(x + 16, y), "« %s »" % str(e.get("content", "")), width, 12, TEXT)


func _draw_card(rect: Rect2, fill: Color) -> void:
	draw_rect(rect, fill)
	draw_rect(rect, LINE if fill == SURFACE else MAP_BORDER, false, 1.0)


func _section(x: float, y: float, title: String) -> float:
	draw_line(Vector2(x + 16, y), Vector2(x + PANEL_W - 16, y), LINE, 1.0)
	_text(Vector2(x + 16, y + 16), title, 12, ACCENT)
	return y + 22.0


func _para(position: Vector2, text: String, width: float, font_size: int = 12, colour: Color = TEXT) -> float:
	var sized := _font.get_multiline_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, width, font_size)
	draw_multiline_string(
		_font,
		position + Vector2(0, font_size),
		text,
		HORIZONTAL_ALIGNMENT_LEFT,
		width,
		font_size,
		-1,
		colour,
	)
	return position.y + sized.y + 4.0


func _join(items: Array) -> String:
	var out := PackedStringArray()
	for item in items:
		out.append(str(item))
	return ", ".join(out)


func _when(tick: int) -> String:
	if tick < 0:
		return "J-%d" % int(round(-float(tick) / 8640.0))
	return "t%d" % tick


func _viewport() -> Vector2:
	return get_viewport_rect().size


func _fit(view: Vector2) -> void:
	var width := float(_plan.get("width", 60.0))
	var height := float(_plan.get("height", 40.0))
	var avail_w: float = max(view.x - PANEL_W - 2.0 * MARGIN, 160.0)
	var avail_h: float = max(view.y - HUD_H - BOTTOM_H - MARGIN, 160.0)
	_map_rect = Rect2(MARGIN, HUD_H, avail_w, avail_h)
	var pad := 26.0
	_px = min((avail_w - pad * 2.0) / width, (avail_h - pad * 2.0) / height)
	_off = Vector2(
		_map_rect.position.x + (avail_w - width * _px) * 0.5,
		_map_rect.position.y + (avail_h - height * _px) * 0.5,
	)


func _to_screen(point: Variant) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(
		_off.x + float(point[0]) * _px,
		_off.y + (height - float(point[1])) * _px,
	)


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
	var width: float = min(640.0, view.x - PANEL_W - 2.0 * MARGIN)
	var lines: Array[String] = []
	if not bool(_trace.get("found", false)):
		lines.append("%s : %s" % [
			str(_trace.get("indicator", "?")),
			str(_trace.get("reason", "aucune variation")),
		])
	else:
		lines.append("D'où vient ce chiffre · %s : %s → %s (tick t%s, variation %s)" % [
			str(_trace.get("indicator", "?")),
			str(_trace.get("from")),
			str(_trace.get("to")),
			str(_trace.get("tick")),
			str(_trace.get("delta")),
		])
		for step in _trace.get("events", []):
			lines.append("• t%s #%s — %s" % [
				str(step.get("tick")), str(step.get("seq")), str(step.get("label")),
			])
			if lines.size() >= 10:
				break
	var height := 28.0
	for line in lines:
		height += _font.get_multiline_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, width - 24.0, 12).y + 4.0
	var top: float = max(view.y - BOTTOM_H - height - 24.0, HUD_H + 12.0)
	var card := Rect2(MARGIN + 12.0, top, width, height)
	draw_rect(card, SURFACE)
	draw_rect(card, ACCENT, false, 1.5)
	_close_trace_rect = Rect2(card.end.x - 76.0, card.position.y + 6.0, 68.0, 22.0)
	draw_rect(_close_trace_rect, SURFACE_2)
	_text(_close_trace_rect.position + Vector2(8, 15), "Fermer ×", 11, TEXT)

	var y := top + 12.0
	for i in range(lines.size()):
		y = _para(Vector2(card.position.x + 12.0, y), lines[i], width - 90.0 if i == 0 else width - 24.0, 12, ACCENT if i == 0 else TEXT)


func _agent_by_id(agent_id: String) -> Dictionary:
	if agent_id.is_empty():
		return {}
	for agent in _snap.get("agents", []):
		if str(agent["id"]) == agent_id:
			return agent
	return {}


func _text(position: Vector2, text: String, font_size: int = 13, colour: Color = TEXT) -> void:
	draw_string(_font, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
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
			_cycle_agent(1 if event.keycode in [KEY_RIGHT, KEY_DOWN] else -1)


func _scrub_timeline(click: Vector2) -> bool:
	if not _timeline_rect.has_point(click) or _snapshots_by_tick.is_empty():
		return false
	var max_t := 20
	for pt in _timeline:
		max_t = maxi(max_t, int(pt["tick"]))
	var ratio := clampf((click.x - _timeline_rect.position.x) / maxf(1.0, _timeline_rect.size.x), 0.0, 1.0)
	var target_t := int(round(ratio * float(max_t)))
	var best_t := -1
	var best_diff := 999999
	for k in _snapshots_by_tick.keys():
		var d := absi(int(k) - target_t)
		if d < best_diff:
			best_diff = d
			best_t = int(k)
	if best_t >= 0:
		_paused = true
		if _pause_btn != null:
			_pause_btn.text = "▶ Reprendre"
		_snap = _snapshots_by_tick[best_t]
		if _indicators_by_tick.has(best_t):
			_ind = _indicators_by_tick[best_t]
		return true
	return false


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


func _select_at(click: Vector2) -> void:
	if _request_trace(click):
		return
	if not _map_rect.has_point(click):
		return
	var best := ""
	var best_distance := maxf(0.9 * _px, 16.0)
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var distance := _to_screen(agent["pos"]).distance_to(click)
		if distance < best_distance:
			best_distance = distance
			best = str(agent["id"])
	_selected = best
