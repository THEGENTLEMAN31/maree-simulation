extends Control
## Inspecteur d'agent (D2) : mémoire, dernière décision, justification,
## passages RAG et règle appliquée. Panneau flottant au-dessus de la carte.
##
## Toutes les données viennent du message `inspection` (aucun calcul ici).

const UI = preload("res://scripts/ui_theme.gd")

var _text: RichTextLabel
var _close: Button


func _ready() -> void:
	position = Vector2(48, 112)
	size = Vector2(460, 540)
	visible = false
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 20

	_close = Button.new()
	_close.text = "✕"
	_close.position = Vector2(422, 10)
	_close.size = Vector2(26, 26)
	_close.flat = true
	_close.add_theme_font_size_override("font_size", 16)
	_close.add_theme_color_override("font_color", UI.MUTED)
	_close.add_theme_color_override("font_hover_color", UI.TEXT)
	_close.pressed.connect(close_panel)
	add_child(_close)

	_text = RichTextLabel.new()
	_text.name = "Text"
	_text.position = Vector2(16, 44)
	_text.size = Vector2(428, 452)
	_text.bbcode_enabled = true
	_text.scroll_active = true
	_text.fit_content = false
	_text.add_theme_font_size_override("normal_font_size", 12)
	_text.add_theme_font_size_override("bold_font_size", 12)
	_text.add_theme_color_override("default_color", UI.TEXT)
	_text.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(_text)

	set_process_unhandled_input(true)


func close_panel() -> void:
	visible = false


func get_text() -> String:
	if _text == null:
		return ""
	if _text.has_method("get_parsed_text"):
		return _text.get_parsed_text()
	return _text.text


func show_inspection(data: Dictionary) -> void:
	if data.has("error"):
		_text.text = "[color=#ef4444]Agent inconnu du moteur.[/color]\n\n%s" % _safe(
			str(data.get("agent_id", ""))
		)
		visible = true
		queue_redraw()
		return

	var agent_id := str(data.get("agent_id", "?"))
	var kind := str(data.get("kind", "rules"))
	var profile := str(data.get("profile", "?"))
	var zone := str(data.get("zone", "?"))
	var belief: Variant = data.get("belief", null)
	var evacuated := bool(data.get("evacuated", false))
	var trapped := bool(data.get("trapped", false))
	var last_action := str(data.get("last_action", ""))
	if last_action == "":
		last_action = "—"
	var last_exit := str(data.get("last_exit", ""))
	var explanation: Variant = data.get("explanation", null)
	var intention: Variant = data.get("intention", null)

	var b := ""
	b += "[font_size=19][b]Agent %s[/b][/font_size]  %s\n" % [
		_safe(agent_id),
		"[color=#a78bfa]LLM[/color]" if kind == "llm" else "[color=#93a2ba]règles[/color]",
	]
	b += "[color=#93a2ba]Profil[/color] %s   [color=#93a2ba]Zone[/color] %s\n" % [
		_safe(profile), _safe(zone)
	]
	b += "[color=#93a2ba]Croyance[/color] [color=%s]%s[/color]   [color=#93a2ba]État[/color] %s\n" % [
		_color_hex(belief),
		_safe(_belief_label(belief)),
		"évacué par %s" % last_exit if evacuated else ("piégé" if trapped else "sur place"),
	]

	b += "\n[color=#a78bfa]DERNIÈRE DÉCISION[/color]\n"
	b += "[b]%s[/b]" % _safe(_action_label(last_action))
	if intention is Dictionary:
		var target := str(intention.get("target_zone", ""))
		var exit_code := str(intention.get("exit_code", ""))
		if target != "":
			b += " → zone %s" % _safe(target)
		if exit_code != "":
			b += " · sortie %s" % _safe(exit_code)
	if last_exit != "":
		b += "  [color=#93a2ba](dernière sortie : %s)[/color]" % _safe(last_exit)
	b += "\n"

	if explanation is Dictionary:
		if explanation.get("kind", "") == "llm":
			var reasoning := str(explanation.get("reasoning", "")).strip_edges()
			if reasoning == "":
				b += "[i][color=#5f6c82]Pas de justification enregistrée pour cette décision.[/color][/i]\n"
			else:
				b += "[i][color=#cbd5e1]« %s »[/color][/i]\n" % _safe(_truncate(reasoning, 420))
		else:
			b += "[color=#93a2ba]Règle appliquée :[/color] %s\n" % _safe(
				_rule_text(explanation)
			)
	else:
		b += "[i][color=#5f6c82]Aucune décision enregistrée pour l'instant.[/color][/i]\n"

	var memory: Array = data.get("memory", [])
	b += "\n[color=#a78bfa]MÉMOIRE (%d)[/color]\n" % memory.size()
	if memory.is_empty():
		b += "[color=#5f6c82]— mémoire vide —[/color]\n"
	else:
		for entry in memory.slice(0, 5):
			if entry is Dictionary:
				b += "· [color=#93a2ba]t=%s · %s[/color] %s\n" % [
					str(entry.get("tick", "?")),
					_safe(str(entry.get("kind", ""))),
					_safe(_truncate(str(entry.get("text", "")), 110)),
				]

	var rag: Variant = data.get("last_rag", null)
	b += "\n[color=#a78bfa]PASSAGES RAG[/color]\n"
	if rag is Array and not rag.is_empty():
		for p in rag.slice(0, 3):
			if p is Dictionary:
				b += "· [color=#7dd3fc]%s[/color]  [color=#93a2ba]score %s[/color]\n" % [
					_safe(str(p.get("doc_id", "?"))),
					_fmt(float(p.get("score", 0.0))),
				]
	else:
		b += "[color=#5f6c82]— aucun passage (agent à règles ou RAG désactivé) —[/color]\n"

	var drifts: Array = data.get("drifts", [])
	b += "\n[color=#93a2ba]Dérives (A4) :[/color] %d · " % drifts.size()
	b += "[color=#93a2ba]Décisions :[/color] %s" % str(data.get("decisions", 0))

	_text.text = b
	visible = true
	queue_redraw()


func _fmt(v: float) -> String:
	return ("%.3f" % v).replace(".", ",")


func _truncate(s: String, n: int) -> String:
	return s if s.length() <= n else s.substr(0, n - 1) + "…"


func _safe(s: String) -> String:
	return s.replace("[", "(").replace("]", ")")


func _belief_label(belief: Variant) -> String:
	match str(belief):
		"A", "B", "C":
			return "sortie %s" % str(belief)
		_:
			return "aucune info"


func _color_hex(belief: Variant) -> String:
	match str(belief):
		"A":
			return "#56b4e9"
		"B":
			return "#e69f00"
		"C":
			return "#009e73"
		_:
			return "#8c97a8"


func _action_label(action: String) -> String:
	match action:
		"evacuate":
			return "Évacuer"
		"move":
			return "Se déplacer"
		"stay":
			return "Rester"
		_:
			return "—"


func _rule_text(explanation: Dictionary) -> String:
	var parts: Array[String] = []
	for key in ["zone", "exit_pref", "chosen"]:
		if explanation.has(key):
			parts.append("%s = %s" % [key, str(explanation[key])])
	var weights: Variant = explanation.get("weights", null)
	if weights is Dictionary:
		var w: Array[String] = []
		for k in weights:
			w.append("%s %.1f" % [str(k), float(weights[k])])
		if not w.is_empty():
			parts.append("poids : " + ", ".join(w))
	return " · ".join(parts) if not parts.is_empty() else "règle déterministe"


func _draw() -> void:
	UI.panel(self, Rect2(Vector2.ZERO, size), Color(0.055, 0.078, 0.12, 0.98), UI.ACCENT, 14, 1)
	UI.text(self, Vector2(16, 26), "INSPECTION", 11, UI.MUTED)
	UI.text(
		self, Vector2(16, 524),
		"Données du moteur · Échap pour fermer", 9, UI.FAINT
	)


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		close_panel()
		get_viewport().set_input_as_handled()
