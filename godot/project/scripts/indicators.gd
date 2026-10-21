extends Control
## Courbes des indicateurs (B2) : small multiples, axe = ticks simulés.
##
## Chaque indicateur a sa propre ligne, sa valeur courante et son échelle
## fixe 0..1. On ne relie pas les points entre deux mesures (segments droits),
## et l'abscisse est le tick réel : une courbe qui ne bouge pas reste plate.
## I5 (violations temporelles) n'est pas une proportion : affiché comme un
## compteur, pas comme une courbe.

const UI = preload("res://scripts/ui_theme.gd")

const LABELS := [
	"I1 consensus",
	"I2 écart croyance / réalité",
	"I4 suivi de meneur",
	"I3 évacués",
]
const COLORS := [
	Color("#7dd3fc"),
	Color("#fbbf24"),
	Color("#34d399"),
	Color("#cbd5e1"),
]
const HORIZON_DEFAULT := 60

var _history: Array = [[], [], [], []]
var _ticks: Array = []
var _values: Array = [0.0, 0.0, 0.0, 0.0]
var _i5: int = 0
var _horizon: int = HORIZON_DEFAULT


func _ready() -> void:
	position = Vector2(872, 96)
	size = Vector2(384, 330)
	mouse_filter = Control.MOUSE_FILTER_STOP


func set_horizon(max_ticks: int) -> void:
	if max_ticks > 0 and max_ticks != _horizon:
		_horizon = max_ticks
		queue_redraw()


func push_indicators(data: Dictionary) -> void:
	_ticks.append(int(data.get("tick", _ticks.size())))
	_history[0].append(float(data.get("I1_consensus", 0.0)))
	_history[1].append(float(data.get("I2_belief_gap", 0.0)))
	_history[2].append(float(data.get("I4_leader_follow", 0.0)))

	var ratio: Variant = data.get("I3_evacuated_ratio", null)
	if ratio == null:
		var i3: Dictionary = data.get("I3_evacuation", {})
		var ev := float(i3.get("evacuated", 0))
		var total := ev + float(i3.get("trapped", 0)) + float(i3.get("remaining", 0))
		ratio = ev / max(1.0, total)
	_history[3].append(clampf(float(ratio), 0.0, 1.0))

	for i in 4:
		_values[i] = float(_history[i][-1])
	_i5 = int(data.get("I5_temporal_violations", 0))
	var horizon := int(data.get("max_ticks", 0))
	if horizon > 0:
		_horizon = horizon
	queue_redraw()


func _fmt(v: float) -> String:
	return ("%.2f" % v).replace(".", ",")


func _draw() -> void:
	UI.panel(self, Rect2(Vector2.ZERO, size), UI.PANEL, UI.BORDER, 16, 1)
	UI.text(self, Vector2(18, 24), "INDICATEURS", 11, UI.MUTED)
	UI.chip(self, Vector2(112, 10), "B2", UI.ACCENT, 10)
	UI.text_right(self, 366, 24, "tick %d" % (_ticks[-1] if _ticks.size() else 0), 11, UI.FAINT)
	UI.text(self, Vector2(18, 40), "échelle fixe 0 → 1 · axe = ticks simulés", 9, UI.FAINT)

	if _history[0].is_empty():
		UI.text(
			self, Vector2(0, 170),
			"En attente du flux…", 12, UI.FAINT,
			HORIZONTAL_ALIGNMENT_CENTER, size.x
		)
	else:
		for i in 4:
			_draw_row(i)
		_draw_i5()

	# Pied : rappel de lecture.
	UI.text(
		self, Vector2(18, 320),
		"Chaque point = une mesure publiée (tous les 10 ticks).", 9, UI.FAINT
	)


func _draw_row(i: int) -> void:
	var y := 52.0 + float(i) * 56.0
	var color: Color = COLORS[i]
	UI.text(self, Vector2(18, y + 10), LABELS[i], 12, UI.TEXT)
	var value_text := _fmt(_values[i])
	if i == 3:
		value_text = "%d %%" % int(round(_values[i] * 100.0))
	UI.text_right(self, 366, y + 10, value_text, 13, color)

	var x0 := 18.0
	var x1 := 366.0
	var w := x1 - x0
	var t0 := x0
	var t1 := y + 20.0
	var h := 26.0

	# Grille 0 / 0,5 / 1.
	draw_line(Vector2(t0, t1 + h), Vector2(x1, t1 + h), Color(1, 1, 1, 0.06), 1.0)
	draw_dashed_line(
		Vector2(t0, t1 + h * 0.5), Vector2(x1, t1 + h * 0.5),
		Color(1, 1, 1, 0.06), 1.0, 3.0
	)
	draw_line(Vector2(t0, t1), Vector2(x1, t1), Color(1, 1, 1, 0.04), 1.0)

	# Segments droits entre mesures (pas d'interpolation mensongère).
	if _history[i].size() >= 2:
		for j in range(1, _history[i].size()):
			var tick_a := float(_ticks[j - 1])
			var tick_b := float(_ticks[j])
			var xa := x0 + clampf(tick_a / float(max(1, _horizon)), 0.0, 1.0) * w
			var xb := x0 + clampf(tick_b / float(max(1, _horizon)), 0.0, 1.0) * w
			var ya := t1 + h - clampf(float(_history[i][j - 1]), 0.0, 1.0) * h
			var yb := t1 + h - clampf(float(_history[i][j]), 0.0, 1.0) * h
			draw_line(Vector2(xa, ya), Vector2(xb, yb), Color(color, 0.9), 1.5)

	# Point courant.
	var last_tick := float(_ticks[-1])
	var lx := x0 + clampf(last_tick / float(max(1, _horizon)), 0.0, 1.0) * w
	var ly := t1 + h - clampf(_values[i], 0.0, 1.0) * h
	draw_circle(Vector2(lx, ly), 3.0, color)


func _draw_i5() -> void:
	var y := 288.0
	UI.text(self, Vector2(18, y), "I5 violations temporelles", 12, UI.MUTED)
	var ok := _i5 == 0
	var color := UI.OK if ok else UI.DANGER
	var label := "0 · cohérent" if ok else "%d · à vérifier" % _i5
	UI.text_right(self, 366, y, label, 12, color)
