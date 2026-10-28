extends Node2D
## Client de visualisation MARÉE.
##
## Il ne simule rien. Il ouvre un WebSocket sur `maree serve`, reçoit le
## plan puis les instantanés, et dessine. Toute la topologie vient du
## message `hello` : il n'y a pas de deuxième source de vérité en
## GDScript.
##
## Ce qui se lit à l'écran :
##   * chaque point est un agent, coloré par la SORTIE QU'IL CROIT bonne
##     (pas par sa position) — c'est le sujet du projet ;
##   * les points gris n'ont aucune croyance : ils ne savent pas où aller ;
##   * un contour blanc signale l'agent sélectionné ;
##   * le panneau de droite montre ses croyances chiffrées.

const PX_PER_M := 11.0
const MARGIN := 16.0
const PANEL_W := 300.0

const BELIEF_COLORS := {
	"A": Color(0.30, 0.58, 1.00),   # Grand Quai
	"B": Color(0.30, 0.85, 0.45),   # Ruelle des Cordiers
	"C": Color(1.00, 0.66, 0.20),   # Passage des Halles
}
const UNKNOWN := Color(0.52, 0.54, 0.58)
const INK := Color(0.88, 0.90, 0.93)
const DIM := Color(0.55, 0.58, 0.62)

var _ws := WebSocketPeer.new()
var _plan: Dictionary = {}
var _snap: Dictionary = {}
var _ind: Dictionary = {}
var _narratives: Array[String] = []
var _selected := ""
var _status := "connexion…"
var _font: Font


func _ready() -> void:
	_font = ThemeDB.fallback_font
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
	queue_redraw()


func _handle(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var message: Dictionary = parsed
	match str(message.get("type", "")):
		"hello":
			_plan = message.get("plan", {})
		"snapshot":
			_snap = message
		"indicators":
			_ind = message
		"narrative":
			_narratives.append("t%s — %s" % [message.get("tick"), message.get("text")])
			if _narratives.size() > 4:
				_narratives.pop_front()
		"end":
			_status = "terminé"


# ------------------------------------------------------------------
# Dessin
# ------------------------------------------------------------------
func _draw() -> void:
	var view := _viewport()
	draw_rect(Rect2(Vector2.ZERO, view), Color(0.05, 0.06, 0.08))
	if _plan.is_empty():
		_text(Vector2(MARGIN, 40), "En attente du plan… (%s)" % _status, 16)
		return

	_draw_world()
	_draw_agents()
	_draw_hud()
	_draw_inspector()


func _draw_world() -> void:
	var walkable := PackedVector2Array()
	for point in _plan.get("walkable", []):
		walkable.append(_to_screen(point))
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


func _draw_agents() -> void:
	var radius := 0.34 * PX_PER_M
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var position := _to_screen(agent["pos"])
		var colour: Color = BELIEF_COLORS.get(str(agent.get("belief")), UNKNOWN)
		draw_circle(position, radius, colour)
		if str(agent["id"]) == _selected:
			draw_arc(position, radius + 5.0, 0.0, TAU, 24, Color.WHITE, 2.0)


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
		Vector2(MARGIN, 46),
		"t%s   %s   évacués %d/%d   I1 %.2f   I5 %.1f pers/m²" % [
			tick,
			sim_time,
			evacuated,
			agents.size(),
			float(_ind.get("I1_consensus", 0.0)),
			float(_ind.get("I5_max_density", 0.0)),
		],
		13,
		DIM,
	)
	_text(Vector2(view.x - PANEL_W - 210, 26), _status, 13, DIM)

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
		return

	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
	_text(Vector2(x + 16, 30), str(agent["id"]), 18, INK)
	_text(Vector2(x + 16, 52), "profil : %s" % agent.get("profile", "?"), 13, DIM)
	_text(Vector2(x + 16, 74), "intention : %s" % str(agent.get("intention", "—")), 13, DIM)
	draw_circle(Vector2(x + 24, 102), 7.0, colour)
	_text(
		Vector2(x + 40, 107),
		"croit en %s (%.0f %%)" % [belief if belief != "" else "rien", float(agent.get("confidence", 0.0)) * 100.0],
		13,
		INK,
	)
	_text(Vector2(x + 16, 140), "position : %.1f, %.1f m" % [float(agent["pos"][0]), float(agent["pos"][1])], 13, DIM)
	if bool(agent.get("evacuated", false)):
		_text(Vector2(x + 16, 162), "sorti de l'esplanade", 13, Color(0.30, 0.85, 0.45))


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------
func _viewport() -> Vector2:
	# Node2D n'a pas de `size` : c'est une propriété de Control.
	return get_viewport_rect().size


func _to_screen(point: Variant) -> Vector2:
	var height := float(_plan.get("height", 40.0))
	return Vector2(float(point[0]) * PX_PER_M, (height - float(point[1])) * PX_PER_M)


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
		_select_at(event.position)


func _select_at(click: Vector2) -> void:
	var best := ""
	var best_distance := 0.8 * PX_PER_M
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var distance := _to_screen(agent["pos"]).distance_to(click)
		if distance < best_distance:
			best_distance = distance
			best = str(agent["id"])
	_selected = best
