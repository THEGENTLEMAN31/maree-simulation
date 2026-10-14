extends Control
## Panneau d'inspection d'un agent (D2) : mémoire, justification de la
## dernière décision, passages RAG retrouvés (ou règle appliquée).

var _agent_id: String = ""
var _hidden: bool = true

func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	offset_left = -300
	offset_top = 0
	offset_right = -10
	offset_bottom = 420
	visible = false

func show_inspection(data: Dictionary) -> void:
	_agent_id = data["agent_id"]
	visible = true
	var text := ""
	text += "[b]Agent %s[/b]\n" % _agent_id
	text += "Zone : %s\n" % data["zone"]
	text += "Croyance : sortie %s\n" % data["belief"]
	text += "Évacué : %s\n" % data["evacuated"]
	if data.has("explanation"):
		text += "\n[b]Règle appliquée :[/b]\n%s\n" % JSON.stringify(data["explanation"])
	if data.has("memory"):
		text += "\n[b]Mémoire (5 derniers) :[/b]\n"
		for entry in data["memory"]:
			text += "- @t%d [%s] %s\n" % [entry["tick"], entry["kind"], entry["text"]]
	if data.has("last_rag"):
		text += "\n[b]Passages RAG retrouvés :[/b]\n"
		for r in data["last_rag"]:
			text += "- %s (score %s)\n" % [r["doc_id"], r["score"]]
	if data.has("drifts"):
		text += "\n[b]Dérives (A4) :[/b] %d\n" % data["drifts"].size()
	var label := get_node("Label")
	if is_instance_valid(label):
		label.text = text

func close() -> void:
	visible = false

func _input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_RIGHT:
			close()