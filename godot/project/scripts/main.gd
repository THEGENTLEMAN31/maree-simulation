extends Node2D
## Client de visualisation MARÉE.
##
## Il ne simule rien et ne décide rien : il ouvre un WebSocket sur
## `maree live` (ou `maree serve`), reçoit le plan puis les trames, et
## dessine. Toute la topologie vient du message `hello` : il n'y a pas de
## deuxième source de vérité en GDScript.
##
## Ce qui se lit à l'écran :
##   * chaque point est un agent, coloré par la SORTIE QU'IL CROIT bonne
##     (pas par sa position) — c'est le sujet du projet ;
##   * les points gris n'ont aucune croyance : ils ne savent pas où aller ;
##   * un contour blanc signale l'agent sélectionné ;
##   * la nappe grise est la fumée, les cellules rouges sont les goulots ;
##   * le panneau de droite montre, pour l'agent sélectionné, sa mémoire,
##     sa dernière décision et la règle qu'il a appliquée (D2) ;
##   * le panneau de gauche permet d'injecter une annonce, une fumée ou la
##     fermeture d'une sortie (D3). Il est désactivé en rejeu : le serveur
##     refuse alors l'injection, et le client le dit au lieu de mentir.

const MARGIN := 16.0
const PANEL_W := 320.0
const HUD_H := 112.0
const BOTTOM_H := 112.0
const BANNER_MS := 9000.0

const BELIEF_COLORS := {
	"A": Color(0.30, 0.58, 1.00),   # Grand Quai
	"B": Color(0.30, 0.85, 0.45),   # Ruelle des Cordiers
	"C": Color(1.00, 0.66, 0.20),   # Passage des Halles
}
const UNKNOWN := Color(0.52, 0.54, 0.58)
const INK := Color(0.88, 0.90, 0.93)
const DIM := Color(0.55, 0.58, 0.62)
const WARN := Color(1.00, 0.72, 0.30)

var _ws := WebSocketPeer.new()
var _plan: Dictionary = {}
var _snap: Dictionary = {}
var _ind: Dictionary = {}
var _narratives: Array[String] = []
var _selected := ""
var _status := "connexion…"
var _font: Font
#: Échelle et origine du plan en pixels, recalculées à chaque dessin : le
#: client doit rester lisible de 800×480 à 1920×1080 sans réglage.
var _px := 11.0
var _off := Vector2.ZERO

# --- D3 : état d'injection -----------------------------------------
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
var _last_note := ""
#: Capture de documentation : `MAREE_SCREENSHOT=/chemin.png` enregistre
#: l'écran une fois le monde peuplé, puis quitte. Sert aux captures du
#: rapport, sans outil externe (Xvfb, xwd).
var _screenshot_path := ""
var _screenshot_at := -1.0
var _screenshot_done := false
#: `MAREE_SELECT=A13` présélectionne un agent : utile pour une capture ou
#: une démonstration sans clic.
var _preselect := ""
var _debug := false
var _debug_at := -1.0


func _ready() -> void:
	_font = ThemeDB.fallback_font
	_build_inject_ui()
	_screenshot_path = OS.get_environment("MAREE_SCREENSHOT")
	_preselect = OS.get_environment("MAREE_SELECT")
	_debug = OS.get_environment("MAREE_DEBUG") == "1"
	# Un instantané de 60 agents pèse ~70 Ko (mémoire, croyances, décision).
	# Le tampon par défaut de WebSocketPeer fait 64 Kio : le client se
	# déconnectait au milieu du run, à la première trame trop grosse.
	_ws.inbound_buffer_size = 8 * 1024 * 1024
	_ws.outbound_buffer_size = 1 * 1024 * 1024
	var url := OS.get_environment("MAREE_WS_URL")
	if url.is_empty():
		url = "ws://127.0.0.1:8765"
	var err := _ws.connect_to_url(url)
	if err != OK:
		_status = "connexion impossible : %s" % url


func _process(_delta: float) -> void:
	_ws.poll()
	# Les trames déjà reçues doivent être lues même si la connexion vient de
	# se fermer : le serveur envoie « end » puis ferme. En ne lisant qu'en
	# STATE_OPEN, le client perdait ce dernier message et affichait
	# « déconnecté » sur une diffusion pourtant terminée.
	while _ws.get_available_packet_count() > 0:
		_handle(_ws.get_packet().get_string_from_utf8())
	match _ws.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			# Ne pas écraser « terminé » : la socket reste ouverte quelques
			# instants après la trame `end`, et cette branche remettait le
			# statut à « connecté », puis « déconnecté » à la fermeture.
			if _status != "connecté" and _status != "terminé":
				_status = "connecté"
		WebSocketPeer.STATE_CLOSED:
			if _status != "terminé":
				_status = "déconnecté"
	if _debug and Time.get_ticks_msec() / 1000.0 > _debug_at:
		_debug_at = Time.get_ticks_msec() / 1000.0 + 2.0
		print("debug : %s · tick %s · plan %d · agents %d · fumée %s" % [
			_status, str(_snap.get("tick", "?")), _plan.size(),
			_snap.get("agents", []).size(), str(_snap.get("smoke_active", false)),
		])
	_maybe_screenshot()
	queue_redraw()


## Capture de documentation. Elle attend que le monde soit peuplé et que la
## fumée soit visible : sinon la capture ne montre que du vide.
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
			_plan = message.get("plan", {})
			_live = bool(message.get("live", false))
			_apply_live_state()
		"snapshot":
			_snap = message
			if _preselect != "" and _selected == "" and _agent_by_id(_preselect):
				_selected = _preselect
		"indicators":
			_ind = message
		"world":
			_handle_world(message)
		"injection":
			_note("injecté : %s" % str(message.get("kind", "?")))
		"ack":
			_note("✔ %s en file" % str(message.get("kind", "?")))
		"error":
			_note("✖ %s" % str(message.get("reason", "erreur")))
		"incident":
			_note("incident %s : %s" % [
				str(message.get("agent_id", "?")),
				str(message.get("cause", "?")),
			])
		"narrative":
			_narratives.append("t%s — %s" % [message.get("tick"), message.get("text")])
			if _narratives.size() > 3:
				_narratives.pop_front()
		"end":
			_status = "terminé"


## Une trame `world` dit qu'un événement du monde vient d'avoir lieu.
## Sans elle, une annonce injectée ne s'afficherait nulle part : c'est le
## trou qui rendait D3 inobservable.
func _handle_world(message: Dictionary) -> void:
	match str(message.get("kind", "")):
		"smoke":
			_world_smoke = {
				"position": message.get("position", []),
				"radius": float(message.get("radius", 0.0)),
				"tick": int(message.get("tick", 0)),
			}
			_note("fumée visible (t%s)" % message.get("tick"))
		"announcement":
			_announcement = str(message.get("text", ""))
			_announcement_at = Time.get_ticks_msec()
			_note("annonce diffusée")
		"exit_closed":
			_note("sortie %s fermée" % message.get("exit", "?"))


# ------------------------------------------------------------------
# D3 — injection
# ------------------------------------------------------------------
func _build_inject_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	# Le bouton reste visible quand le panneau est replié : D3 doit se
	# voir au premier regard, sans deviner un raccourci clavier.
	_toggle = Button.new()
	_toggle.text = "Masquer l'injection ▴"
	_toggle.position = Vector2(MARGIN, HUD_H)
	_toggle.custom_minimum_size = Vector2(232, 26)
	_toggle.pressed.connect(_toggle_panel)
	layer.add_child(_toggle)

	_panel = PanelContainer.new()
	_panel.position = Vector2(MARGIN, HUD_H + 32.0)
	_panel.custom_minimum_size = Vector2(300, 0)
	_panel.modulate = Color(1, 1, 1, 0.94)
	layer.add_child(_panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	_panel.add_child(box)

	var title := Label.new()
	title.text = "Injecter un événement"
	title.add_theme_font_size_override("font_size", 14)
	box.add_child(title)

	_announce_edit = LineEdit.new()
	_announce_edit.text = "Évacuation immédiate, sortie B"
	_announce_edit.tooltip_text = "Texte de l'annonce diffusée aux agents"
	box.add_child(_announce_edit)

	var row := HBoxContainer.new()
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
	smoke.text = "Fumée ici"
	smoke.tooltip_text = "Cliquez d'abord sur le plan : la fumée naît à cet endroit"
	smoke.pressed.connect(_inject_smoke)
	box.add_child(smoke)
	_buttons.append(smoke)

	_hint = Label.new()
	_hint.text = "connexion…"
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint.custom_minimum_size = Vector2(284, 0)
	_hint.add_theme_font_size_override("font_size", 11)
	_hint.add_theme_color_override("font_color", DIM)
	box.add_child(_hint)


func _toggle_panel() -> void:
	_panel.visible = not _panel.visible
	_toggle.text = "Masquer l'injection ▴" if _panel.visible else "Injecter un événement ▾"


func _apply_live_state() -> void:
	for button in _buttons:
		button.disabled = not _live
	if _live:
		_hint.text = "cliquez le plan, puis « Fumée ici »"
		_hint.add_theme_color_override("font_color", DIM)
	else:
		_hint.text = "rejeu : injection désactivée (le serveur la refuserait)"
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
# Dessin
# ------------------------------------------------------------------
func _draw() -> void:
	var view := _viewport()
	draw_rect(Rect2(Vector2.ZERO, view), Color(0.05, 0.06, 0.08))
	if _plan.is_empty():
		_text(Vector2(MARGIN, 40), "En attente du plan… (%s)" % _status, 16)
		return
	_fit(view)

	_draw_world()
	_draw_density()
	_draw_agents()
	_draw_smoke()
	_draw_announcement()
	_draw_hud()
	_draw_inspector()


func _draw_world() -> void:
	var walkable := PackedVector2Array()
	for point in _plan.get("walkable", []):
		walkable.append(_to_screen(point))
	if walkable.size() >= 3:
		draw_colored_polygon(walkable, Color(0.12, 0.14, 0.17))

	for obstacle in _plan.get("obstacles", []):
		var polygon := PackedVector2Array()
		for point in obstacle.get("polygon", []):
			polygon.append(_to_screen(point))
		draw_colored_polygon(polygon, Color(0.24, 0.21, 0.19))

	for exit in _plan.get("exits", []):
		var a := _to_screen(exit["a"])
		var b := _to_screen(exit["b"])
		var open := _is_open(str(exit["id"]))
		draw_line(a, b, Color(0.25, 0.90, 0.45) if open else Color(0.92, 0.25, 0.25), 9.0)
		_text(a + Vector2(6, -10), "sortie %s" % exit["id"], 13, DIM)


## D1 — les goulots. La grille est envoyée par le moteur depuis le début
## (`density_grid`) ; elle n'était simplement jamais dessinée. Une cellule
## à 2 agents est un passage contraint : c'est là qu'on voit où la foule
## s'étrangle, sans lire un chiffre.
func _draw_density() -> void:
	for cell in _snap.get("density_grid", []):
		var n := int(cell.get("n", 0))
		if n < 2:
			continue
		var origin := _to_screen([float(cell["x"]), float(cell["y"]) + 1.0])
		var alpha: float = min(0.10 * float(n), 0.42)
		draw_rect(
			Rect2(origin, Vector2(_px, _px)),
			Color(0.95, 0.25, 0.20, alpha)
		)


func _draw_agents() -> void:
	var radius := 0.34 * _px
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var position := _to_screen(agent["pos"])
		var belief := str(agent.get("belief", ""))
		var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
		draw_circle(position, radius, colour)
		# D1 — l'écart avec la réalité, agent par agent : s'il croit en une
		# sortie qui n'est plus ouverte, il ne le sait pas. L'anneau orange
		# le dit avant que I6 (agrégé) ne bouge.
		if belief != "" and not _is_open(belief):
			draw_arc(position, radius + 3.5, 0.0, TAU, 20, WARN, 1.5)
		if str(agent["id"]) == _selected:
			draw_arc(position, radius + 6.0, 0.0, TAU, 24, Color.WHITE, 2.0)


func _draw_smoke() -> void:
	# L'instantané fait foi (il survit à une connexion tardive) ; la trame
	# `world` sert d'avance immédiate entre deux instantanés.
	var smoke: Dictionary = _snap.get("smoke", {})
	if smoke.is_empty() or not bool(_snap.get("smoke_active", false)):
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
	draw_circle(centre, radius, Color(0.62, 0.64, 0.68, 0.18))
	for ring in [0.45, 0.72, 1.0]:
		draw_arc(centre, radius * float(ring), 0.0, TAU, 48, Color(0.70, 0.72, 0.76, 0.22), 1.0)
	_text(centre + Vector2(-30, -6), "fumée", 12, Color(0.75, 0.77, 0.80))


func _draw_announcement() -> void:
	if _announcement.is_empty():
		return
	var age_ms := Time.get_ticks_msec() - _announcement_at
	if age_ms > BANNER_MS:
		return
	var view := _viewport()
	var width := view.x - PANEL_W - 2.0 * MARGIN
	var text := "📣  %s" % _announcement
	var sized := _font.get_multiline_string_size(
		text, HORIZONTAL_ALIGNMENT_LEFT, width - 16.0, 14
	)
	# Au milieu du plan : visible sans disputer le HUD, le panneau
	# d'injection (à gauche) ni l'inspecteur (à droite).
	var height := sized.y + 12.0
	var x := MARGIN
	# Juste au-dessus des récits, jamais sur le panneau d'injection ni
	# sur l'inspecteur.
	var y := view.y - BOTTOM_H + 4.0
	draw_rect(Rect2(Vector2(x, y), Vector2(width, height)), Color(0.10, 0.12, 0.15, 0.94))
	draw_rect(
		Rect2(Vector2(x, y), Vector2(width, height)),
		Color(0.35, 0.62, 0.95),
		false,
		1.0
	)
	_para(Vector2(x + 8, y + 4), text, width - 16.0, 14, Color(0.82, 0.88, 0.96))


func _draw_hud() -> void:
	var view := _viewport()
	var tick := int(_snap.get("tick", 0))
	var sim_time := str(_snap.get("sim_time", "0:00"))
	var agents: Array = _snap.get("agents", [])
	var remaining := 0
	for agent in agents:
		if not bool(agent.get("evacuated", false)):
			remaining += 1
	var evacuated := agents.size() - remaining

	_text(Vector2(MARGIN, 26), "MARÉE — Port-Aubel", 18, INK)
	_text(
		Vector2(MARGIN, 48),
		"t%s   %s   évacués %d/%d" % [tick, sim_time, evacuated, agents.size()],
		13,
		DIM,
	)
	# B2 — un indicateur au moins doit être affiché à côté de la scène,
	# synchronisé avec elle. On en affiche six, nommés, pour qu'un
	# observateur qui ne connaît pas le code puisse les lire.
	_text(
		Vector2(MARGIN, 68),
		"I1 %.2f   I2 %.2f   I3 %.2f   I5 %.1f/m²   I6 %.2f   I7 %.0f s" % [
			float(_ind.get("I1_consensus", 0.0)),
			float(_ind.get("I2_entropy", 0.0)),
			float(_ind.get("I3_evacuated", 0.0)),
			float(_ind.get("I5_max_density", 0.0)),
			float(_ind.get("I6_belief_gap", 0.0)),
			float(_ind.get("I7_delay_seconds", 0.0)),
		],
		11,
		DIM,
	)
	_text(
		Vector2(view.x - PANEL_W - 250, 26),
		_status if _live else "%s (rejeu)" % _status,
		13,
		DIM if _live else WARN,
	)
	# Les retours d'injection restent visibles même panneau replié :
	# sinon on appuie sur « Annoncer » sans savoir si c'est parti.
	var note_y := 46.0
	for note in _notes:
		var colour := WARN if note.begins_with("✖") else DIM
		_text(Vector2(view.x - PANEL_W - 250, note_y), note, 11, colour)
		note_y += 15.0
	# La légende est indispensable à D1 (« compréhensible pour un
	# observateur qui ne connaît pas le code ») : un point coloré sans
	# légende ne veut rien dire.
	_para(
		Vector2(MARGIN, 78),
		"point = sortie crue (A bleu, B vert, C orange, gris = aucune croyance) · anneau orange = croit une sortie fermée · cellules rouges = goulots",
		view.x - PANEL_W - 2.0 * MARGIN,
		9,
		Color(0.45, 0.48, 0.52),
	)

	var y := view.y - 16.0 - float(max(_narratives.size() - 1, 0)) * 18.0
	for line in _narratives:
		_text(Vector2(MARGIN, y), line, 13, Color(0.72, 0.76, 0.80))
		y += 18.0


func _draw_inspector() -> void:
	var view := _viewport()
	var x := view.x - PANEL_W
	draw_rect(Rect2(Vector2(x, 0), Vector2(PANEL_W, view.y)), Color(0.08, 0.09, 0.11))
	draw_line(Vector2(x, 0), Vector2(x, view.y), Color(0.18, 0.20, 0.24), 1.0)

	var agent := _agent_by_id(_selected)
	if agent.is_empty():
		_text(Vector2(x + 16, 30), "Cliquez un agent", 14, DIM)
		_text(Vector2(x + 16, 52), "Sa mémoire, sa dernière", 12, DIM)
		_text(Vector2(x + 16, 68), "décision et la règle qu'il", 12, DIM)
		_text(Vector2(x + 16, 84), "a appliquée s'afficheront ici.", 12, DIM)
		return

	var width := PANEL_W - 32.0
	var y := 28.0
	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)

	_text(Vector2(x + 16, y), str(agent["id"]), 18, INK)
	y += 20.0
	_text(Vector2(x + 16, y), str(agent.get("label", agent.get("profile", "?"))), 12, DIM)
	y += 16.0
	_text(
		Vector2(x + 16, y),
		"profil %s (%s)" % [agent.get("profile", "?"), agent.get("kind", "?")],
		12,
		DIM,
	)
	y += 20.0

	var target: Variant = agent.get("intention_target")
	var arrow := ""
	if target != null:
		arrow = " → %s" % str(target)
	_text(
		Vector2(x + 16, y),
		"intention : %s%s" % [str(agent.get("intention", "—")), arrow],
		12,
		INK,
	)
	y += 18.0

	draw_circle(Vector2(x + 24, y - 4), 7.0, colour)
	_text(
		Vector2(x + 40, y),
		"croit en %s (%.0f %%)" % [
			belief if belief != "" else "rien",
			float(agent.get("confidence", 0.0)) * 100.0,
		],
		12,
		INK,
	)
	y += 18.0
	if belief != "" and not _is_open(belief):
		_text(Vector2(x + 16, y), "⚠ croit une sortie fermée", 12, WARN)
		y += 18.0

	var perceived: Array = agent.get("perceived", [])
	_text(
		Vector2(x + 16, y),
		"perçu : %s" % ("—" if perceived.is_empty() else _join(perceived)),
		11,
		DIM,
	)
	y += 18.0

	# --- D2 : la dernière décision, expliquée -----------------------
	var decision: Variant = agent.get("last_decision")
	y = _section(x, y, "dernière décision")
	if typeof(decision) == TYPE_DICTIONARY and not decision.is_empty():
		var d: Dictionary = decision
		_text(
			Vector2(x + 16, y),
			"t%s · %s · déclencheur : %s" % [
				d.get("tick", "?"),
				d.get("kind", "?"),
				d.get("trigger", "—"),
			],
			11,
			DIM,
		)
		y += 16.0
		y = _para(Vector2(x + 16, y), "raison : %s" % str(d.get("reason", "—")), width, 12, INK)
		if d.get("rule") != null:
			# Un agent à règles n'a pas de justification générée : sa
			# règle EST la justification. D2 demande les deux.
			y = _para(Vector2(x + 16, y), "règle appliquée : %s" % str(d["rule"]), width, 11, Color(0.70, 0.78, 0.62))
		var retrieved: Array = d.get("retrieved", [])
		if not retrieved.is_empty():
			y = _para(
				Vector2(x + 16, y),
				"passages retenus : %s" % _join(retrieved),
				width,
				11,
				DIM,
			)
	else:
		y = _para(Vector2(x + 16, y), "aucune décision encore prise", width, 12, DIM)

	# --- D2 : la mémoire --------------------------------------------
	y = _section(x, y, "mémoire (3 plus saillants)")
	var memory: Array = agent.get("memory", [])
	if memory.is_empty():
		y = _para(Vector2(x + 16, y), "rien en mémoire", width, 12, DIM)
	for episode in memory:
		if typeof(episode) != TYPE_DICTIONARY:
			continue
		var e: Dictionary = episode
		var when := _when(int(e.get("tick", 0)))
		_text(
			Vector2(x + 16, y),
			"%s · %s · %s" % [when, e.get("kind", "?"), e.get("source", "?")],
			11,
			DIM,
		)
		y += 14.0
		y = _para(Vector2(x + 16, y), "« %s »" % str(e.get("content", "")), width, 12, INK)
		y += 4.0
	if y > view.y - 20.0:
		_text(Vector2(x + 16, view.y - 12), "…", 12, DIM)


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------
func _section(x: float, y: float, title: String) -> float:
	draw_line(Vector2(x + 16, y - 8), Vector2(x + PANEL_W - 16, y - 8), Color(0.20, 0.22, 0.26), 1.0)
	_text(Vector2(x + 16, y + 6), title, 12, Color(0.60, 0.72, 0.86))
	return y + 24.0


## Texte replié : renvoie l'ordonnée suivante. Sans cela, une raison de
## 200 caractères sortait du panneau et n'était jamais lue.
func _para(position: Vector2, text: String, width: float, font_size: int = 12, colour: Color = INK) -> float:
	var sized := _font.get_multiline_string_size(
		text, HORIZONTAL_ALIGNMENT_LEFT, width, font_size
	)
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
	# 1 tick = 10 s ; une journée simulée = 8640 ticks. La préhistoire est
	# datée en négatif : « J-3 » se lit mieux que « t-25920 ».
	if tick < 0:
		return "J-%d" % int(round(-float(tick) / 8640.0))
	return "t%d" % tick


func _viewport() -> Vector2:
	# Node2D n'a pas de `size` : c'est une propriété de Control.
	return get_viewport_rect().size


## Ajuste le plan à la surface libre (à gauche de l'inspecteur, sous le
## HUD, au-dessus du bandeau). Une échelle fixe laissait la moitié de
## l'écran vide en 1000×640 et débordait en 800×480.
func _fit(view: Vector2) -> void:
	var width := float(_plan.get("width", 60.0))
	var height := float(_plan.get("height", 40.0))
	var avail_w: float = max(view.x - PANEL_W - 2.0 * MARGIN, 120.0)
	var avail_h: float = max(view.y - HUD_H - BOTTOM_H, 120.0)
	_px = min(avail_w / width, avail_h / height)
	_off = Vector2(
		MARGIN + (avail_w - width * _px) * 0.5,
		HUD_H + (avail_h - height * _px) * 0.5
	)


func _to_screen(point: Variant) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(
		_off.x + float(point[0]) * _px,
		_off.y + (height - float(point[1])) * _px
	)


func _to_world(click: Vector2) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(
		(click.x - _off.x) / _px,
		height - (click.y - _off.y) / _px
	)


func _is_open(exit_id: String) -> bool:
	var open: Array = _snap.get("exits_open", [])
	if open.is_empty():
		return true
	return exit_id in open


func _agent_by_id(agent_id: String) -> Dictionary:
	if agent_id.is_empty():
		return {}
	for agent in _snap.get("agents", []):
		if str(agent["id"]) == agent_id:
			return agent
	return {}


func _text(position: Vector2, text: String, font_size: int = 13, colour: Color = INK) -> void:
	draw_string(_font, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_last_click_m = _to_world(event.position)
		_select_at(event.position)


func _select_at(click: Vector2) -> void:
	var best := ""
	var best_distance := 0.9 * _px
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var distance := _to_screen(agent["pos"]).distance_to(click)
		if distance < best_distance:
			best_distance = distance
			best = str(agent["id"])
	_selected = best
