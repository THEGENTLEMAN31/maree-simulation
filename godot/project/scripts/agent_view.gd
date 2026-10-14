extends Control
## Rendu des agents : cercles colorés positionnés selon leur zone (D1).
## Chaque agent reçoit une couleur selon sa croyance (B2) :
##   - gris : n'a rien entendu / pas d'info
##   - bleu : croit que A est sûr
##   - amber : croit que B est sûr
##   - vert  : croit que C est sûr
## Clic = envoie une demande d'inspection (D2).

var _points: PackedVector2Array = PackedVector2Array()
var _colors: PackedColorArray = PackedColorArray()
var _tooltips: Array = []

# Position approximative des zones (coordonnées logiques 0..100)
const ZONES := {
	"scene": Vector2(50, 45),
	"nord": Vector2(55, 80),
	"ouest": Vector2(12, 40),
	"stand1": Vector2(80, 62),
	"stand2": Vector2(20, 25),
	"passerelle": Vector2(62, 90),
	"sud_est": Vector2(72, 15),
	"sud_ouest": Vector2(25, 12),
	"sortie_a": Vector2(95, 8),
	"sortie_b": Vector2(66, 99),
	"sortie_c": Vector2(5, 8),
}

func update_state(data: Dictionary) -> void:
	var agents: Array = data["agents"]
	_points = PackedVector2Array()
	_colors = PackedColorArray()
	_tooltips.clear()
	for agent in agents:
		var zone: String = agent["zone"]
		var pos: Vector2 = ZONES.get(zone, Vector2(50, 45)) as Vector2
		_points.push_back(pos)
		_colors.push_back(_color_for(agent))
		_tooltips.push_back("%s (%s)".format([agent["id"], agent["belief"]]))
	queue_redraw()

func _color_for(agent: Dictionary) -> Color:
	var belief: Variant = agent.get("belief", null)
	if belief == null or belief == "":
		return Color(0.45, 0.45, 0.45, 1.0)  # gris : aucune info
	match belief:
		"A": return Color(0.18, 0.27, 0.79, 1.0)   # bleu
		"B": return Color(0.83, 0.52, 0.10, 1.0)   # amber
		"C": return Color(0.13, 0.55, 0.21, 1.0)   # vert
		_: return Color(0.45, 0.45, 0.45, 1.0)

func _draw() -> void:
	# fond de l'esplanade
	draw_rect(Rect2(Vector2(4, 4), Vector2(122, 116)), Color(0.08, 0.09, 0.12, 1))
	draw_rect(Rect2(Vector2(4, 4), Vector2(122, 116)), Color(0.10, 0.11, 0.15, 1))
	# sorties (petits rectangles)
	draw_rect(Rect2(Vector2(88, 2), Vector2(16, 4)), Color(0.9, 0.1, 0.1, 1))  # A
	draw_rect(Rect2(Vector2(60, 113), Vector2(5, 4)), Color(0.2, 0.8, 0.2, 1))  # B
	draw_rect(Rect2(Vector2(2, 2), Vector2(4, 4)), Color(0.2, 0.5, 0.9, 1))     # C
	# agents
	for i in _points.size():
		var p: Vector2 = _points[i]
		var c: Color = _colors[i]
		draw_circle(p, 2.6, c)
		draw_arc(p, 2.6, 0.0, TAU, c, 2.2, 120)

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed:
			var mpos: Vector2 = mb.position
			for i in _points.size():
				if mpos.distance_to(_points[i]) < 3.0:
					var agent_id: String = _tooltips[i]
					var ws := get_node("/root/World")
					if is_instance_valid(ws):
						ws.request_inspect(agent_id)
					break