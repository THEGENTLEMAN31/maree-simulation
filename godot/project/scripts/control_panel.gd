extends Control
## Panneau de contrôle (D3) : injection d'événements depuis Godot.
##
## Quatre événements : annonce claire, annonce neutre (contrôle B3), fausse
## info, fermeture de la sortie A (destructive → double confirmation).
## Aucune logique de simulation : on envoie une commande, python-sim décide
## et accuse réception (`control_ack`). L'injection est journalisée côté
## moteur (topic `control.commands`, F4).

const UI = preload("res://scripts/ui_theme.gd")
const CONFIRM_DELAY := 3.0

var _status: Label
var _armed_button: Button = null
var _armed_timer: float = 0.0


func _ready() -> void:
	position = Vector2(872, 438)
	size = Vector2(384, 250)
	mouse_filter = Control.MOUSE_FILTER_STOP

	var box := VBoxContainer.new()
	box.name = "Box"
	box.position = Vector2(14, 46)
	box.size = Vector2(356, 160)
	box.add_theme_constant_override("separation", 6)
	add_child(box)

	_add_button(box, "Annonce claire", "announcement", {
		"text": "Évacuation par la sortie C, sans danger.",
	})
	_add_button(box, "Annonce neutre", "neutral_announcement", {
		"text": "Nous vous informons qu'une annonce est en cours.",
	})
	_add_button(box, "Fausse info", "false_info", {
		"text": "La sortie A est la plus rapide.",
	})
	_add_button(box, "Fermer sortie A", "close_exit", {"exit": "A"}, true)

	_status = Label.new()
	_status.name = "Status"
	_status.position = Vector2(14, 214)
	_status.size = Vector2(356, 20)
	_status.add_theme_font_size_override("font_size", 11)
	_status.add_theme_color_override("font_color", UI.MUTED)
	_status.text = "Aucune commande envoyée."
	add_child(_status)


func _add_button(
	parent: Node, label: String, command: String, extra: Dictionary,
	danger: bool = false
) -> void:
	var b := Button.new()
	b.name = "Btn_%s_%d" % [command, label.hash()]
	b.text = label
	b.set_meta("base_label", label)
	b.custom_minimum_size = Vector2(0, 34)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.add_theme_font_size_override("font_size", 13)
	var fg := Color("#fca5a5") if danger else UI.TEXT
	b.add_theme_color_override("font_color", fg)
	b.add_theme_color_override("font_hover_color", Color.WHITE)
	b.add_theme_color_override("font_pressed_color", Color.WHITE)
	b.add_theme_stylebox_override("normal", _style(UI.PANEL_2, UI.BORDER))
	b.add_theme_stylebox_override("hover", _style(Color("#1e2a3e"), Color("#3b4a63")))
	b.add_theme_stylebox_override("pressed", _style(Color("#0f1a2b"), UI.ACCENT))
	b.add_theme_stylebox_override("focus", _style(Color(0, 0, 0, 0), UI.ACCENT, 1))
	b.pressed.connect(_on_pressed.bind(b, command, extra, danger))
	parent.add_child(b)


func _style(bg: Color, border: Color, border_w: int = 1) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border
	sb.set_border_width_all(border_w)
	sb.set_corner_radius_all(6)
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb


func _on_pressed(
	button: Button, command: String, extra: Dictionary, danger: bool
) -> void:
	# Fermeture irréversible : deux clics, avec retour automatique.
	if danger and _armed_button == null:
		_armed_button = button
		_armed_timer = CONFIRM_DELAY
		button.text = "Confirmer la fermeture ? (%ds)" % int(CONFIRM_DELAY)
		_set_status("Fermeture irréversible : confirmez en recliquant.", UI.BELIEF_B)
		return
	_armed_button = null
	_armed_timer = 0.0
	button.text = str(button.get_meta("base_label", button.text))
	_send(command, extra)


func _send(command: String, extra: Dictionary) -> void:
	var ws := get_tree().get_first_node_in_group("ws_client")
	if ws == null or not ws.has_method("send_command"):
		_set_status("Hors ligne — commande non envoyée.", UI.DANGER)
		return
	if ws.send_command(command, extra):
		var label := str(extra.get("text", extra.get("exit", "")))
		_set_status("→ %s envoyée%s · en attente d'accusé" % [
			command, (" (« %s »)" % label) if label != "" else "",
		], UI.MUTED)
	else:
		_set_status("Hors ligne — commande non envoyée.", UI.DANGER)


func on_ack(data: Dictionary) -> void:
	if bool(data.get("ok", false)):
		_set_status(
			"✓ commande appliquée · tick %s" % str(data.get("tick", "?")),
			UI.BELIEF_C
		)
	else:
		_set_status("✗ commande refusée par le moteur.", UI.DANGER)


func _set_status(text: String, color: Color) -> void:
	if _status != null:
		_status.text = text
		_status.add_theme_color_override("font_color", color)


func _process(delta: float) -> void:
	if _armed_button != null:
		_armed_timer -= delta
		if _armed_timer <= 0.0:
			_armed_button.text = str(_armed_button.get_meta("base_label", ""))
			_armed_button = null


func _draw() -> void:
	UI.panel(self, Rect2(Vector2.ZERO, size), UI.PANEL, UI.BORDER, 16, 1)
	UI.text(self, Vector2(14, 24), "CONTRÔLES", 11, UI.MUTED)
	UI.chip(self, Vector2(96, 10), "D3", UI.ACCENT, 10)
	UI.text(self, Vector2(14, 40), "injection d'événements · double clic pour fermer A", 9, UI.FAINT)
	UI.text(self, Vector2(14, 240), "Journalisé côté moteur · topic control.commands (F4)", 9, UI.FAINT)


## Appelé par les tests : déclenche un bouton par son libellé d'origine.
func press_button(label: String) -> bool:
	for child in get_node("Box").get_children():
		if child is Button and str(child.get_meta("base_label", child.text)) == label:
			child.emit_signal("pressed")
			return true
	return false
