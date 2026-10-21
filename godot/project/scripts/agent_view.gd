extends Control
## Carte de l'esplanade (D1) : zones, sorties, fumée, agents.
##
## Godot ne calcule rien : il dessine l'instantané reçu (positions par zone,
## croyances, compteurs, état des sorties). Les cercles sont colorés par
## croyance ; un anneau blanc distingue les agents LLM des agents à règles.
## Clic sur un agent = demande d'inspection (D2).

const UI = preload("res://scripts/ui_theme.gd")

## Géométrie de la scène (unités logiques 0..100, y vers le bas).
const ZONES := {
	"scene": {"p": Vector2(48, 46), "s": Vector2(30, 22), "label": "Esplanade"},
	"nord": {"p": Vector2(48, 14), "s": Vector2(24, 12), "label": "Parvis nord"},
	"passerelle": {"p": Vector2(72, 24), "s": Vector2(10, 18), "label": "Passerelle"},
	"stand1": {"p": Vector2(82, 46), "s": Vector2(14, 12), "label": "Stands est"},
	"stand2": {"p": Vector2(16, 38), "s": Vector2(14, 12), "label": "Stands ouest"},
	"ouest": {"p": Vector2(12, 62), "s": Vector2(12, 12), "label": "Allée ouest"},
	"sud_est": {"p": Vector2(74, 74), "s": Vector2(15, 12), "label": "Parvis sud-est"},
	"sud_ouest": {"p": Vector2(26, 76), "s": Vector2(15, 12), "label": "Parvis sud-ouest"},
	"sortie_a": {"p": Vector2(92, 90), "s": Vector2(10, 8), "label": "A", "exit": "A"},
	"sortie_b": {"p": Vector2(60, 92), "s": Vector2(10, 8), "label": "B", "exit": "B"},
	"sortie_c": {"p": Vector2(6, 88), "s": Vector2(10, 8), "label": "C", "exit": "C"},
}

const EDGES := [
	["scene", "nord"], ["scene", "stand1"], ["scene", "stand2"],
	["scene", "ouest"], ["scene", "sud_est"], ["scene", "sud_ouest"],
	["nord", "passerelle"], ["passerelle", "sortie_b"],
	["sud_est", "sortie_a"], ["sud_ouest", "sortie_c"], ["ouest", "sortie_c"],
	["stand1", "sud_est"], ["stand2", "sud_ouest"],
]

const MAP_ORIGIN := Vector2(142, 54)
const MAP_SCALE := 5.4

var _points: PackedVector2Array = PackedVector2Array()
var _colors: PackedColorArray = PackedColorArray()
var _agent_ids: Array = []
var _meta: Dictionary = {}
var _target: Dictionary = {}
var _display: Dictionary = {}
var _exits: Dictionary = {}
var _counts: Dictionary = {}
var _smoke: float = 0.0
var _hover_id: String = ""
var _hover_pos: Vector2 = Vector2.ZERO


func _ready() -> void:
	position = Vector2(24, 96)
	size = Vector2(824, 600)
	mouse_filter = Control.MOUSE_FILTER_STOP


func _to_screen(p: Vector2) -> Vector2:
	return MAP_ORIGIN + p * MAP_SCALE


func _zone_rect(zone: String) -> Rect2:
	var z: Dictionary = ZONES[zone]
	var half: Vector2 = z["s"] * 0.5
	return Rect2(_to_screen(z["p"] - half), z["s"] * MAP_SCALE)


func update_state(data: Dictionary) -> void:
	_exits = data.get("exits", {})
	_counts = data.get("counts", {})
	_smoke = float(data.get("smoke_level", 0.0))

	var agents: Array = data.get("agents", [])
	var by_zone: Dictionary = {}
	for agent in agents:
		if bool(agent.get("evacuated", false)):
			continue
		var zone: String = str(agent.get("zone", "scene"))
		if not by_zone.has(zone):
			by_zone[zone] = []
		by_zone[zone].append(agent)

	_target.clear()
	_meta.clear()
	for zone in by_zone:
		var group: Array = by_zone[zone]
		var center: Vector2 = ZONES.get(zone, {"p": Vector2(48, 46)})["p"]
		var radius_max: float = 3.4
		for i in group.size():
			var agent: Dictionary = group[i]
			var angle := float(i) * 2.399963229728653
			var r: float = 1.15 * sqrt(float(i) + 0.35)
			r = min(r, radius_max)
			var offset := Vector2(cos(angle), sin(angle)) * r
			var id := str(agent.get("id", "?"))
			_target[id] = center + offset
			_meta[id] = agent

	_rebuild_points()
	queue_redraw()


func _rebuild_points() -> void:
	_points = PackedVector2Array()
	_colors = PackedColorArray()
	_agent_ids.clear()
	for id in _meta:
		var logical: Vector2 = _target[id]
		_points.push_back(_to_screen(logical))
		_colors.push_back(UI.belief_color(_meta[id].get("belief", null)))
		_agent_ids.push_back(id)


func _process(delta: float) -> void:
	var moved := false
	for id in _target:
		if not _display.has(id):
			_display[id] = _target[id]
			moved = true
			continue
		var next: Vector2 = (_display[id] as Vector2).lerp(
			_target[id], 1.0 - exp(-10.0 * delta)
		)
		if next.distance_to(_display[id]) > 0.01:
			moved = true
		_display[id] = next
	if moved:
		_points = PackedVector2Array()
		for id in _meta:
			_points.push_back(_to_screen(_display.get(id, _target[id])))
		queue_redraw()


func _draw() -> void:
	UI.panel(self, Rect2(Vector2.ZERO, size), UI.PANEL, UI.BORDER, 16, 1)

	# Titre de la carte + légende.
	UI.text(self, Vector2(22, 30), "Esplanade de Port-Aubel", 18, UI.TEXT)
	UI.text(
		self, Vector2(22, 50),
		"vue par zones · clic sur un agent = inspecter (D2)", 11, UI.MUTED
	)
	_draw_legend(Vector2(548, 14))

	# Grille discrète (repère spatial).
	for i in range(0, 101, 10):
		var p1 := _to_screen(Vector2(i, 0))
		var p2 := _to_screen(Vector2(i, 100))
		draw_line(p1, p2, Color(1, 1, 1, 0.025), 1.0)
		var q1 := _to_screen(Vector2(0, i))
		var q2 := _to_screen(Vector2(100, i))
		draw_line(q1, q2, Color(1, 1, 1, 0.025), 1.0)

	# Liens entre zones (topologie du graphe).
	for edge in EDGES:
		var a: Vector2 = ZONES[edge[0]]["p"]
		var b: Vector2 = ZONES[edge[1]]["p"]
		draw_line(_to_screen(a), _to_screen(b), Color(0.35, 0.42, 0.55, 0.35), 2.0)

	# Zones.
	for zone in ZONES:
		var z: Dictionary = ZONES[zone]
		var rect := _zone_rect(zone)
		if z.has("exit"):
			continue
		UI.panel(self, rect, UI.PANEL_2, UI.BORDER, 10, 1)
		UI.text(self, rect.position + Vector2(8, 16), str(z["label"]), 10, UI.MUTED)
		var n := 0
		for id in _meta:
			if str(_meta[id].get("zone", "")) == zone:
				n += 1
		if n > 0:
			UI.text_right(
				self, rect.position.x + rect.size.x - 7, rect.position.y + 16,
				str(n), 10, UI.FAINT
			)

	# Fumée (au sud : parvis et sorties basses).
	if _smoke > 0.01:
		for zone in ["sud_est", "sud_ouest", "passerelle", "sortie_a", "sortie_b"]:
			var rect := _zone_rect(zone)
			draw_rect(rect.grow(6), Color(UI.SMOKE, 0.07 + 0.16 * _smoke))
		var label := "fumée %d %%" % int(_smoke * 100.0)
		var pos := _to_screen(Vector2(82, 63))
		UI.chip(self, pos, label, UI.SMOKE, 10)

	# Sorties.
	for zone in ["sortie_a", "sortie_b", "sortie_c"]:
		_draw_exit(zone)

	# Agents (cercles colorés par croyance, anneau = LLM).
	for i in _agent_ids.size():
		var id: String = _agent_ids[i]
		var agent: Dictionary = _meta[id]
		var center := _to_screen(_display.get(id, _target[id]))
		var is_llm := str(agent.get("kind", "rules")) == "llm"
		var radius := 6.0 if is_llm else 4.8
		_draw_marker(center, radius, agent.get("belief", null))
		if is_llm:
			draw_arc(center, radius + 2.2, 0, TAU, 24, Color(1, 1, 1, 0.85), 1.4)
		if id == _hover_id:
			draw_arc(center, radius + 5.0, 0, TAU, 24, UI.ACCENT, 2.0)

	if _hover_id != "" and _meta.has(_hover_id):
		_draw_tooltip(_hover_id)


## Marqueur de croyance : la couleur ne porte jamais l'info seule.
## A = plein · B = point central · C = anneau interne · ? = creux.
func _draw_marker(center: Vector2, radius: float, belief: Variant) -> void:
	draw_circle(center + Vector2(0, 1.5), radius + 1.5, Color(0, 0, 0, 0.45))
	var code := str(belief)
	var color := UI.belief_color(belief)
	if code in ["A", "B", "C"]:
		draw_circle(center, radius, color)
		if code == "B":
			draw_circle(center, radius * 0.32, Color(1, 1, 1, 0.92))
		elif code == "C":
			draw_arc(center, radius * 0.55, 0, TAU, 20, Color(1, 1, 1, 0.92), 1.3)
	else:
		draw_circle(center, radius, UI.PANEL)
		draw_arc(center, radius, 0, TAU, 24, UI.UNKNOWN, 1.6)


func _draw_legend(pos: Vector2) -> void:
	UI.text(self, pos + Vector2(0, 12), "Croyance :", 10, UI.MUTED)
	var x := pos.x + 64.0
	for code in ["A", "B", "C", "?"]:
		_draw_marker(Vector2(x + 4, pos.y + 8), 4.0, code if code != "?" else null)
		UI.text(self, Vector2(x + 11, pos.y + 12), code, 10, UI.TEXT)
		x += 26.0
	draw_arc(Vector2(x + 5, pos.y + 8), 5.0, 0, TAU, 16, Color(1, 1, 1, 0.85), 1.4)
	UI.text(self, Vector2(x + 14, pos.y + 12), "LLM", 10, UI.MUTED)
	UI.text(self, Vector2(pos.x, pos.y + 28), "○ règles", 10, UI.FAINT)


func _draw_exit(zone: String) -> void:
	var z: Dictionary = ZONES[zone]
	var code: String = z["exit"]
	var state: Dictionary = _exits.get(code, {})
	var blocked := bool(state.get("blocked", false))
	var evacuated := int(state.get("evacuated", 0))
	var rect := _zone_rect(zone)
	var fill := Color(UI.DANGER, 0.20) if blocked else Color(UI.OK, 0.16)
	var border := UI.DANGER if blocked else UI.OK
	UI.panel(self, rect, fill, border, 8, 2)
	UI.text(
		self, rect.position + Vector2(rect.size.x * 0.5 - 7, rect.size.y * 0.5 + 7),
		code, 20, border
	)
	if blocked:
		draw_line(
			rect.position + Vector2(8, 8), rect.position + rect.size - Vector2(8, 8),
			UI.DANGER, 2.0
		)
		draw_line(
			rect.position + Vector2(rect.size.x - 8, 8),
			rect.position + Vector2(8, rect.size.y - 8), UI.DANGER, 2.0
		)
		UI.text(
			self, rect.position + Vector2(0, rect.size.y + 12),
			"fermée", 9, UI.DANGER
		)
	else:
		UI.text(
			self, rect.position + Vector2(0, rect.size.y + 12),
			"%d évacués" % evacuated, 9, UI.OK
		)


func _draw_tooltip(id: String) -> void:
	var agent: Dictionary = _meta[id]
	var lines := [
		id,
		"%s · %s" % [
			str(agent.get("profile", "?")),
			"LLM" if str(agent.get("kind", "rules")) == "llm" else "règles",
		],
		"%s · %s" % [
			UI.belief_label(agent.get("belief", null)),
			str(agent.get("zone", "?")),
		],
	]
	var w := 0.0
	for i in lines.size():
		w = max(w, UI.text_width(lines[i], 12 if i > 0 else 13))
	w += 20.0
	var h := 62.0
	var p := _hover_pos + Vector2(16, 12)
	p.x = min(p.x, size.x - w - 8)
	p.y = min(p.y, size.y - h - 8)
	UI.panel(self, Rect2(p, Vector2(w, h)), Color(0.04, 0.06, 0.10, 0.96), UI.ACCENT, 8, 1)
	UI.text(self, p + Vector2(10, 17), lines[0], 13, UI.TEXT)
	UI.text(self, p + Vector2(10, 35), lines[1], 12, UI.MUTED)
	UI.text(self, p + Vector2(10, 52), lines[2], 12, UI.belief_color(agent.get("belief", null)))


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		_hover_pos = mm.position
		var best := ""
		var best_d := 12.0
		for i in _points.size():
			var d := mm.position.distance_to(_points[i])
			if d < best_d:
				best_d = d
				best = str(_agent_ids[i])
		if best != _hover_id:
			_hover_id = best
			queue_redraw()
	elif event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT and _hover_id != "":
			request_inspect(_hover_id)


func _notification(what: int) -> void:
	if what == NOTIFICATION_MOUSE_EXIT and _hover_id != "":
		_hover_id = ""
		queue_redraw()


## Retrouve le client WS (nœud du groupe "ws_client") sans dépendre du chemin.
func request_inspect(agent_id: String) -> void:
	var ws := get_tree().get_first_node_in_group("ws_client")
	if ws != null and ws.has_method("request_inspect"):
		ws.request_inspect(agent_id)
