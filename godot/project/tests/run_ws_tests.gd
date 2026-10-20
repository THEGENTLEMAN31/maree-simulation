extends SceneTree
## Test d'intégration de la chaîne WebSocket Godot <-> serveur Python.
## Nécessite un serveur WS sur SIM_WS_URL (ws://localhost:8765 par défaut).
## Lancer :
##   godot --headless --path /godot/project --script res://tests/run_ws_tests.gd
## Code de sortie 0 si tout passe, 1 sinon.

var _ok: int = 0
var _fail: int = 0
var _frame: int = 0
var _setup_done: bool = false
var _sent: bool = false
var _wait: int = 0

var _root_node: Node
var _world: Node
var _agents: Node
var _chart: Node
var _panel: Node

func _process(_delta: float) -> bool:
	_frame += 1
	if not _setup_done:
		_setup()
		_setup_done = true
		return false

	if not _sent:
		if _world.is_open():
			print("[test-ws] connexion ouverte -> envoi inspect + command")
			_world.request_inspect("a1")
			_world.send_command("announcement", {"text": "test chaine"})
			_sent = true
			_wait = 0
		elif _frame > 300:
			_check(false, "connexion WS ouverte (< 5 s)")
			return _finish()
		return false

	_wait += 1
	if _wait < 90:
		return false

	var counts: Dictionary = _world.received_counts()
	_check(int(counts.get("state", 0)) >= 1, "reçu et routé type=state")
	_check(int(counts.get("indicators", 0)) >= 1, "reçu et routé type=indicators")
	_check(int(counts.get("inspection", 0)) >= 1, "reçu type=inspection (réponse au inspect)")
	_check(_agents._points.size() == 4, "state appliqué à agent_view (4 agents)")
	_check(_chart._history[0].size() >= 1, "indicators appliqués au graphe")
	_check(_panel.visible, "inspection appliquée au panneau")
	_check(_panel.get_text().find("a1") >= 0, "panneau affiche l'agent inspecté")
	return _finish()

func _setup() -> void:
	print("=== Test chaîne WebSocket Godot ===")
	var packed: PackedScene = load("res://scenes/main.tscn")
	_check(packed != null, "main.tscn se charge")
	_root_node = packed.instantiate()
	get_root().add_child(_root_node)
	_world = _root_node.get_node("World")
	_agents = _root_node.get_node("World/AgentsLayer/AgentContainer")
	_chart = _root_node.get_node("World/IndicatorChart")
	_panel = _root_node.get_node("World/InspectPanel")
	print("[test-ws] URL = ", _world.sim_ws_url)

func _check(cond: bool, name: String) -> void:
	if cond:
		_ok += 1
		print("  OK   - ", name)
	else:
		_fail += 1
		print("  FAIL - ", name)

func _finish() -> bool:
	print("\n=== RESULTAT WS: %d OK, %d ECHEC ===" % [_ok, _fail])
	quit(1 if _fail > 0 else 0)
	return true
