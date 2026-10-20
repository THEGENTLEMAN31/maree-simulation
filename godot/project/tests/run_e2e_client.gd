extends SceneTree
## Test de BOUT EN BOUT : Godot consomme un run RÉEL de python-sim
## (vrai modèle via llama.cpp, vrai Redpanda, vrai journal).
##
## Vérifie :
##   - la connexion WebSocket ;
##   - la réception et le routage de `state` -> agent_view (D1) ;
##   - la réception de `indicators` -> courbes (B2) ;
##   - l'envoi d'un `inspect` -> réponse `inspection` -> panneau (D2) ;
##   - l'envoi des commandes D3 (announcement, false_info).
##
## Lancer :
##   godot --headless --path /godot/project --script res://tests/run_e2e_client.gd
## Code de sortie 0 si tout passe, 1 sinon.

var _ok: int = 0
var _fail: int = 0
var _frames: int = 0
var _connected: bool = false
var _state_seen: bool = false
var _indicators_seen: bool = false
var _inspect_sent: bool = false
var _inspect_seen: bool = false
var _commands_sent: bool = false
var _target_agent: String = ""
var _deadline_frames: int = 60 * 240  # filet de sécurité : 4 min

var _root_node: Node
var _world: Node
var _agents: Node
var _chart: Node
var _panel: Node
var _control: Node

func _process(_delta: float) -> bool:
	_frames += 1
	if _root_node == null:
		_setup()
		return false

	if _frames > _deadline_frames:
		_check(false, "délai global dépassé (240 s)")
		return _finish()

	if not _world.is_open():
		return false

	if not _connected:
		_connected = true
		print("[e2e] WS connecté à ", _world.sim_ws_url)

	var counts: Dictionary = _world.received_counts()

	if int(counts.get("state", 0)) > 0 and not _state_seen:
		_state_seen = true
		var n: int = _agents._points.size()
		print("[e2e] premier state reçu : tick=%s, %d agents rendus" % [
			str(_world._last_state.get("tick", "?")), n
		])
		for a in _world.get_agents():
			if a.get("kind", "") == "llm":
				_target_agent = a.get("id", "")
				break
			if _target_agent == "":
				_target_agent = a.get("id", "")
		print("[e2e] agent cible pour l'inspection : ", _target_agent)

	if int(counts.get("indicators", 0)) > 0:
		_indicators_seen = true

	if _state_seen and not _inspect_sent and _target_agent != "":
		_inspect_sent = _world.request_inspect(_target_agent)
		print("[e2e] inspect envoyé pour ", _target_agent, " (envoyé=", _inspect_sent, ")")

	if int(counts.get("inspection", 0)) > 0:
		_inspect_seen = true

	if _state_seen and not _commands_sent:
		var a: bool = _world.send_command(
			"announcement", {"text": "Test e2e Godot : évacuez calmement par la sortie la plus proche."}
		)
		var b: bool = _world.send_command("false_info", {"text": "La sortie C est fermée."})
		var c: bool = _world.send_command("close_exit", {"exit": "A"})
		_commands_sent = a and b and c
		print(
			"[e2e] commandes D3 envoyées (announcement=", a,
			", false_info=", b, ", close_exit=", c, ")"
		)

	if _inspect_seen and _commands_sent and _indicators_seen:
		_check(_agents._points.size() > 0, "agent_view : agents réels positionnés (D1)")
		_check(_chart._history[0].size() > 0, "indicators : courbe alimentée (B2)")
		_check(_panel.visible, "inspecteur : panneau visible (D2)")
		_check(
			_panel.get_text().find(_target_agent) >= 0,
			"inspecteur : affiche bien l'agent inspecté"
		)
		_check(
			_panel.get_text().find("Croyance") >= 0,
			"inspecteur : croyance présente dans le panneau"
		)
		_check(_control.get_node_or_null("Box") != null, "HUD D3 présent")
		return _finish()

	return false

func _setup() -> void:
	print("=== Test de bout en bout Godot <-> stack réelle ===")
	var packed: PackedScene = load("res://scenes/main.tscn")
	if packed == null:
		_check(false, "main.tscn se charge")
		_finish()
		return
	_root_node = packed.instantiate()
	get_root().add_child(_root_node)
	_world = _root_node.get_node("World")
	_agents = _root_node.get_node("World/AgentsLayer/AgentContainer")
	_chart = _root_node.get_node("World/IndicatorChart")
	_panel = _root_node.get_node("World/InspectPanel")
	_control = _root_node.get_node("World/ControlPanel")
	print("[e2e] URL = ", _world.sim_ws_url)

func _check(cond: bool, name: String) -> void:
	if cond:
		_ok += 1
		print("  OK   - ", name)
	else:
		_fail += 1
		print("  FAIL - ", name)

func _finish() -> bool:
	print("\n=== RESULTAT E2E: %d OK, %d ECHEC ===" % [_ok, _fail])
	if _world != null:
		_world.close_connection()
	quit(1 if _fail > 0 else 0)
	return true
