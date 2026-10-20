extends Control
## Courbes des indicateurs I1–I5 en temps réel (B2) :
##   I1 consensus, I2 écart croyance/réalité, I4 suivi de meneur.
## La scène affiche les indicateurs SYNCHRONISÉS avec la simulation.

var _history: Array = []          # listes de floats
var _labels: Array = ["I1 consensus", "I2 écart croyance/réalité", "I4 suivi meneur"]
var _keys: Array = ["I1_consensus", "I2_belief_gap", "I4_leader_follow"]
var _colors: Array = [
	Color(0.88, 0.55, 0.15, 1.0),
	Color(0.2, 0.4, 0.8, 1.0),
	Color(0.2, 0.7, 0.3, 1.0),
]
var _max_points: int = 300
var _latest: Dictionary = {}

func _ready() -> void:
	set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	offset_left = 10
	offset_top = -250
	offset_right = 430
	offset_bottom = -10
	for i in _labels.size():
		_history.append([])

func push_indicators(data: Dictionary) -> void:
	_latest = data
	for i in _keys.size():
		_append(i, float(data.get(_keys[i], 0.0)))
	queue_redraw()

func _append(idx: int, v: float) -> void:
	var series: Array = _history[idx]
	series.append(v)
	if series.size() > _max_points:
		series.pop_front()

func _draw() -> void:
	draw_rect(Rect2(Vector2(0, 0), Vector2(420, 232)), Color(0.08, 0.09, 0.12, 0.85))
	var font: Font = ThemeDB.fallback_font
	draw_string(
		font, Vector2(8, 18),
		"Indicateurs (émergence) — tick %s" % str(_latest.get("tick", "?")),
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.9, 0.9, 0.9, 1)
	)
	for i in _labels.size():
		var y0: float = 44.0 + i * 64.0
		var series: Array = _history[i]
		var val: float = float(series[series.size() - 1]) if series.size() > 0 else 0.0
		draw_string(
			font, Vector2(8, y0 - 6),
			"%s : %.2f" % [_labels[i], val],
			HORIZONTAL_ALIGNMENT_LEFT, -1, 13, _colors[i]
		)
		if series.size() < 2:
			continue
		var n: int = series.size()
		var prev: Vector2 = Vector2(8, y0 + 40.0 - float(series[0]) * 40.0)
		for j in n:
			var x: float = 8.0 + j * (400.0 / float(_max_points))
			var y: float = y0 + 40.0 - float(series[j]) * 40.0
			if j > 0:
				draw_line(prev, Vector2(x, y), _colors[i], 1.5)
			prev = Vector2(x, y)
