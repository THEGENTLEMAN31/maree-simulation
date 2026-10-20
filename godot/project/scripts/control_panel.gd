extends Control
## Panneau de contrôle (D3) : injection d'événements depuis Godot.
## Chaque bouton envoie une commande à python-sim via le client WebSocket
## (nœud du groupe "ws_client"). Aucune logique de simulation ici.

func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	offset_left = -360
	offset_top = 40
	offset_right = -20
	offset_bottom = 240

	var box := VBoxContainer.new()
	box.name = "Box"
	box.set_anchors_preset(Control.PRESET_FULL_RECT)
	box.add_theme_constant_override("separation", 6)
	add_child(box)

	var title := Label.new()
	title.text = "Contrôles (D3)"
	box.add_child(title)

	_add_button(box, "Annonce claire", "announcement", {"text": "Évacuation par la sortie C, sans danger."})
	_add_button(box, "Annonce ambiguë", "announcement", {"text": "Il se passe quelque chose au sud…"})
	_add_button(box, "Fausse info", "false_info", {"text": "La sortie A est la plus rapide."})
	_add_button(box, "Fermer sortie A", "close_exit", {"exit": "A"})

func _add_button(parent: Node, label: String, command: String, extra: Dictionary) -> void:
	var b := Button.new()
	b.name = "Btn_%s_%d" % [command, label.hash()]
	b.text = label
	b.pressed.connect(_send.bind(command, extra))
	parent.add_child(b)

func _send(command: String, extra: Dictionary) -> void:
	var ws := get_tree().get_first_node_in_group("ws_client")
	if ws != null and ws.has_method("send_command"):
		if ws.send_command(command, extra):
			print("[control_panel] commande envoyée : ", command, " ", extra)
	else:
		push_warning("[control_panel] aucun client WS disponible")

## Appelé par les tests : déclenche un bouton par son libellé.
func press_button(label: String) -> bool:
	for child in get_node("Box").get_children():
		if child is Button and child.text == label:
			child.emit_signal("pressed")
			return true
	return false
