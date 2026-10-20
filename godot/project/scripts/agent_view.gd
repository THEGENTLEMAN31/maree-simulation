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
var _agent_ids: Array = []

## Mise à l'échelle pour occuper la fenêtre (les zones sont en 0..100).
@export var map_scale: float = 5.0
@export var map_origin: Vector2 = Vector2(40, 20)

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

func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_LEFT)
	offset_left = 0
	offset_top = 0
	offset_right = 760
	offset_bottom = 620

func _to_screen(p: Vector2) -> Vector2:
	return map_origin + p * map_scale

func update_state(data: Dictionary) -> void:
	var agents: Array = data.get("agents", [])
	_points = PackedVector2Array()
	_colors = PackedColorArray()
	_tooltips.clear()
	_agent_ids.clear()
	for agent in agents:
		var zone: String = agent.get("zone", "scene")
		var pos: Vector2 = ZONES.get(zone, Vector2(50, 45))
		_points.push_back(_to_screen(pos))
		_colors.push_back(_color_for(agent))
		_agent_ids.push_back(agent.get("id", "?"))
		_tooltips.push_back("%s (%s)" % [agent.get("id", "?"), agent.get("belief", "?")])
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
	var rect := Rect2(_to_screen(Vector2(4, 4)), Vector2(122, 116) * map_scale)
	draw_rect(rect, Color(0.10, 0.11, 0.15, 1))
	draw_rect(rect, Color(0.25, 0.27, 0.33, 1), false, 2.0)
	# sorties (petits rectangles)
	draw_rect(Rect2(_to_screen(Vector2(88, 2)), Vector2(16, 4) * map_scale), Color(0.9, 0.1, 0.1, 1))  # A
	draw_rect(Rect2(_to_screen(Vector2(60, 113)), Vector2(5, 4) * map_scale), Color(0.2, 0.8, 0.2, 1))  # B
	draw_rect(Rect2(_to_screen(Vector2(2, 2)), Vector2(4, 4) * map_scale), Color(0.2, 0.5, 0.9, 1))     # C
	# agents
	var radius := 2.6 * map_scale
	for i in _points.size():
		var p: Vector2 = _points[i]
		var c: Color = _colors[i]
		draw_circle(p, radius * 1.8 + 2.0, Color(0, 0, 0, 0.35))
		draw_circle(p, radius, c)

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			var mpos: Vector2 = (mb.position - map_origin) / map_scale
			for i in _points.size():
				var logical: Vector2 = (_points[i] - map_origin) / map_scale
				if mpos.distance_to(logical) < 5.0:
					request_inspect(_agent_ids[i])
					break

## Retrouve le client WS (nœud du groupe "ws_client") sans dépendre du chemin.
func request_inspect(agent_id: String) -> void:
	var ws := get_tree().get_first_node_in_group("ws_client")
	if ws != null and ws.has_method("request_inspect"):
		ws.request_inspect(agent_id)
