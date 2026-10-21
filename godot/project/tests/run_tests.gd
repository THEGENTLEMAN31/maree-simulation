extends SceneTree

const UI = preload("res://scripts/ui_theme.gd")
## Tests headless des composants Godot (D1, D2, B2, D3, client WS).
## Lancer :
##   godot --headless --path /godot/project --script res://tests/run_tests.gd
## Code de sortie 0 si tout passe, 1 sinon.

var _ok: int = 0
var _fail: int = 0

func _process(_delta: float) -> bool:
	_run()
	print("\n=== RESULTAT: %d OK, %d ECHEC ===" % [_ok, _fail])
	quit(1 if _fail > 0 else 0)
	return true

func _check(cond: bool, name: String) -> void:
	if cond:
		_ok += 1
		print("  OK   - ", name)
	else:
		_fail += 1
		print("  FAIL - ", name)

func _run() -> void:
	print("=== Tests composants Godot (headless) ===")

	# --- chargement de la scène principale ---
	var packed: PackedScene = load("res://scenes/main.tscn")
	_check(packed != null, "main.tscn se charge")
	if packed == null:
		return
	var root_node: Node = packed.instantiate()
	get_root().add_child(root_node)

	var world: Node = root_node.get_node_or_null("World")
	_check(world != null, "nœud World présent")
	if world == null:
		return

	var header: Node = root_node.get_node_or_null("World/Header")
	var agents: Node = root_node.get_node_or_null("World/AgentsLayer/AgentContainer")
	var chart: Node = root_node.get_node_or_null("World/IndicatorChart")
	var panel: Node = root_node.get_node_or_null("World/InspectPanel")
	var controls: Node = root_node.get_node_or_null("World/ControlPanel")
	_check(header != null, "Header présent (bandeau)")
	_check(agents != null, "AgentContainer présent (agent_view)")
	_check(chart != null, "IndicatorChart présent (indicators)")
	_check(panel != null, "InspectPanel présent (inspector_panel)")
	_check(controls != null, "ControlPanel présent (D3)")

	# --- enregistrement du client WS ---
	_check(get_first_node_in_group("ws_client") == world, "ws_client enregistré dans le groupe")

	# --- composant agent_view : state -> points/couleurs ---
	var state := {
		"type": "state", "tick": 1, "smoke_level": 0.0,
		"agents": [
			{"id": "a1", "zone": "scene", "belief": "A", "kind": "rules"},
			{"id": "a2", "zone": "sortie_b", "belief": "B", "kind": "llm"},
			{"id": "a3", "zone": "nord", "belief": null, "kind": "rules"},
		],
	}
	world._handle_message(JSON.stringify(state))
	_check(agents._points.size() == 3, "state -> agent_view : 3 agents positionnés")
	_check(agents._colors.size() == 3, "state -> agent_view : 3 couleurs")
	_check(agents._colors[0] != agents._colors[1], "couleurs distinctes selon la croyance")
	_check(agents._colors[0] == UI.BELIEF_A, "croyance A -> bleu Okabe-Ito")
	_check(agents._colors[2] == UI.UNKNOWN, "sans croyance -> gris creux")

	# --- composant indicators : indicators -> historique ---
	var ind := {
		"type": "indicators", "tick": 10,
		"I1_consensus": 0.5, "I2_belief_gap": 0.2, "I4_leader_follow": 0.3,
	}
	world._handle_message(JSON.stringify(ind))
	_check(chart._history[0].size() == 1, "indicators -> chart : 1 point I1")
	_check(is_equal_approx(float(chart._history[0][0]), 0.5), "I1 mémorisé = 0.5")
	_check(is_equal_approx(float(chart._history[1][0]), 0.2), "I2 mémorisé = 0.2")
	_check(is_equal_approx(float(chart._history[2][0]), 0.3), "I4 mémorisé = 0.3")
	world._handle_message(JSON.stringify(ind))
	_check(chart._history[0].size() == 2, "2e message -> 2 points I1")

	# --- composant inspector_panel : inspection -> texte ---
	var insp := {
		"type": "inspection", "agent_id": "a1", "zone": "scene",
		"belief": "A", "evacuated": false,
		"explanation": {"kind": "rules"},
	}
	world._handle_message(JSON.stringify(insp))
	_check(panel.visible, "inspection -> panneau visible")
	_check(panel.get_text().find("Agent a1") >= 0, "inspection -> texte contient l'agent")
	_check(panel.get_text().find("Croyance") >= 0, "inspection -> texte contient la croyance")

	# --- composant control_panel (D3) : les boutons existent ---
	var box := controls.get_node_or_null("Box")
	_check(box != null, "ControlPanel : conteneur Box présent")
	var n_buttons := 0
	if box != null:
		for c in box.get_children():
			if c is Button:
				n_buttons += 1
	_check(n_buttons == 4, "ControlPanel : 4 boutons D3")
	_check(controls.press_button("Fermer sortie A"), "bouton D3 pressable (WS fermé => warning attendu)")

	# --- compteur de messages reçus ---
	var counts: Dictionary = world.received_counts()
	_check(int(counts.get("state", 0)) == 1, "compteur state = 1")
	_check(int(counts.get("indicators", 0)) == 2, "compteur indicators = 2")
	_check(int(counts.get("inspection", 0)) == 1, "compteur inspection = 1")

	root_node.queue_free()
