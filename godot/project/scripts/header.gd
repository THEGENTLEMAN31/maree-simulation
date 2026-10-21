extends Control
## Bandeau supérieur : identité de la scène, temps simulé, compteurs, état
## de connexion. Consommateur pur : tout vient du message `state`.

const UI = preload("res://scripts/ui_theme.gd")

var _tick: int = 0
var _smoke: float = 0.0
var _counts: Dictionary = {}
var _announcements: Array = []
var _false_infos: Array = []
var _ws: Node = null
var _clock: float = 0.0


func _ready() -> void:
	position = Vector2.ZERO
	size = Vector2(1280, 88)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func update_state(data: Dictionary) -> void:
	_tick = int(data.get("tick", _tick))
	_smoke = float(data.get("smoke_level", 0.0))
	_counts = data.get("counts", {})
	_announcements = data.get("announcements", [])
	_false_infos = data.get("false_infos", [])
	queue_redraw()


func _process(delta: float) -> void:
	_clock += delta
	if _ws == null:
		_ws = get_tree().get_first_node_in_group("ws_client")
	if _clock >= 0.25:
		_clock = 0.0
		queue_redraw()


func _draw() -> void:
	UI.panel(self, Rect2(Vector2.ZERO, size), UI.PANEL, UI.BORDER, 0, 1)
	draw_line(Vector2(0, size.y - 1), Vector2(size.x, size.y - 1), UI.ACCENT, 2.0)

	# Titre + sous-titre.
	draw_circle(Vector2(34, 30), 7.0, UI.ACCENT)
	UI.text(self, Vector2(50, 40), "MARÉE", 26, UI.TEXT)
	UI.text(
		self, Vector2(50, 66),
		"Port-Aubel · Fête des Lanternes",
		12, UI.MUTED
	)

	# Temps simulé.
	UI.text(self, Vector2(430, 38), "T+ %s" % UI.hhmmss(_tick), 24, UI.TEXT)
	UI.text(self, Vector2(430, 62), "tick %d · 1 tick = 1 s" % _tick, 11, UI.MUTED)

	# Compteurs (état du monde, calculé côté Python).
	var x := 600.0
	var ev := int(_counts.get("evacuated", 0))
	var tr := int(_counts.get("trapped", 0))
	var re := int(_counts.get("remaining", 0))
	var total := int(_counts.get("total", ev + tr + re))
	x += UI.chip(self, Vector2(x, 14), "Évacués %d" % ev, UI.OK, 13) + 8.0
	x += UI.chip(self, Vector2(x, 14), "Piégés %d" % tr, UI.DANGER, 13) + 8.0
	x += UI.chip(self, Vector2(x, 14), "Restants %d / %d" % [re, total], UI.MUTED, 13) + 8.0
	if _smoke > 0.0:
		UI.chip(self, Vector2(x, 14), "Fumée %d %%" % int(_smoke * 100.0), UI.SMOKE, 13)

	var x2 := 600.0
	x2 += UI.chip(
		self, Vector2(x2, 48),
		"Annonces %d" % _announcements.size(), UI.ACCENT, 11
	) + 8.0
	if _false_infos.size() > 0:
		x2 += UI.chip(
			self, Vector2(x2, 48),
			"Fausses infos %d" % _false_infos.size(), UI.BELIEF_B, 11
		) + 8.0

	# État de connexion + modèles.
	var connected: bool = _ws != null and _ws.has_method("is_open") and _ws.is_open()
	var status := "connecté" if connected else "hors ligne"
	var color := UI.OK if connected else UI.DANGER
	var w := UI.text_width(status, 12) + 26.0
	UI.panel(
		self, Rect2(Vector2(1256 - w, 14), Vector2(w, 24)),
		Color(color, 0.12), Color(color, 0.5), 8
	)
	draw_circle(Vector2(1256 - w + 12, 26), 4.0, color)
	UI.text(self, Vector2(1256 - w + 21, 31), status, 12, color)
	UI.text_right(self, 1256, 58, "Gemma 4 E2B · bge-m3", 11, UI.FAINT)
	UI.text_right(self, 1256, 74, "Godot = consommateur pur du flux", 10, UI.FAINT)
