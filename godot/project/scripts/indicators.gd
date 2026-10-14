extends Control
## Courbes des indicateurs I1–I5 en temps réel (B2) :
##   I1 consensus, I2 écart croyance/réalité, I4 suivi de meneur.
## La scène affiche les indicateurs SYNCHRONISÉS avec la simulation.

var _history: Array = []          # listes de floats
var _labels: Array = ["I1 consensus", "I2 écart croyance/réalité", "I4 suivi meneur"]
var _colors: Array = [
	Color(0.88, 0.55, 0.15, 1.0),
	Color(0.2, 0.4, 0.8, 1.0),
	Color(0.2, 0.7, 0.3, 1.0),
]
var _max_points: int = 300

func _ready() -> void:
	set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	offset_left = 10
	offset_top = -220
	offset_right = 420
	offset_bottom = -10
	for i in _labels.size():
		_history.append([])

func push_indicators(data: Dictionary) -> void:
	_append(0, float(data.get("I1_consensus", 0.0)))
	_append(1, float(data.get("I2_belief_gap", 0.0)))
	_append(2, float(data.get("I4_leader_follow", 0.0)))
	queue_redraw()

func _append(idx: int, v: float) -> void:
	var series: Array = _history[idx]
	series.append(v)
	if series.size() > _max_points:
		series.pop_front()

func _draw() -> void:
	draw_rect(Rect2(Vector2(0, 0), Vector2(410, 210)), Color(0.08, 0.09, 0.12, 0.85))
	# titre
	draw_string(Vector2(8, 16), "Indicateurs (émergence)", Color(0.9, 0.9, 0.9, 1))
	for i in _labels.size():
		var y0: float = 40.0 + i * 68.0
		draw_string(Vector2(8, y0 - 6), _labels[i], _colors[i])
		var series: Array = _history[i]
		if series.size() < 2:
			continue
		var prev: Vector2 = Vector2(8, y0)
		var n: int = series.size()
		for j in n:
			var v: float = series[j]
			var x: float = 8.0 + j * (400.0 / float(_max_points))
			var y: float = y0 + 56.0 - v * 56.0
			if j > 0:
				draw_line(prev, Vector2(x, y), _colors[i], 1.5)
			prev = Vector2(x, y)