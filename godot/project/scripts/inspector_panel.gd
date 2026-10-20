extends Control
## Panneau d'inspection d'un agent (D2) : mémoire, justification de la
## dernière décision, passages RAG retrouvés (ou règle appliquée).

var _agent_id: String = ""
var _text: RichTextLabel

func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	offset_left = -360
	offset_top = 260
	offset_right = -10
	offset_bottom = 700
	visible = false
	_text = RichTextLabel.new()
	_text.name = "Text"
	_text.bbcode_enabled = true
	_text.scroll_active = true
	_text.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_text)

func show_inspection(data: Dictionary) -> void:
	_agent_id = data.get("agent_id", "")
	visible = true
	var text := ""
	text += "[b]Agent %s[/b]\n" % _agent_id
	text += "Zone : %s\n" % data.get("zone", "?")
	text += "Croyance : sortie %s\n" % str(data.get("belief", "?"))
	text += "Évacué : %s\n" % str(data.get("evacuated", false))
	if data.has("explanation"):
		text += "\n[b]Règle appliquée :[/b]\n%s\n" % JSON.stringify(data["explanation"])
	if data.has("memory"):
		text += "\n[b]Mémoire (derniers) :[/b]\n"
		for entry in data["memory"]:
			text += "- @t%s [%s] %s\n" % [entry.get("tick"), entry.get("kind"), entry.get("text")]
	if data.has("last_rag") and data["last_rag"] != null:
		text += "\n[b]Passages RAG retrouvés :[/b]\n"
		for r in data["last_rag"]:
			text += "- %s (score %s)\n" % [r.get("doc_id"), r.get("score")]
	if data.has("drifts"):
		text += "\n[b]Dérives (A4) :[/b] %d\n" % data["drifts"].size()
	if _text != null:
		_text.text = text

func get_text() -> String:
	return _text.text if _text != null else ""

func close() -> void:
	visible = false

func _input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_RIGHT:
			close()
