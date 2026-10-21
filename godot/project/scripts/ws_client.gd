extends Node
## Client WebSocket vers python-sim (décision 9 : Godot est un consommateur
## pur — aucune logique de simulation ici).
##
## Reçoit :
##   {type:"state", tick, smoke_level, agents:[{id,zone,belief,kind}]}
##   {type:"indicators", tick, I1_consensus, I2_belief_gap, ...}
##   {type:"inspection", agent_id, zone, belief, evacuated, ...}
## Envoie :
##   {type:"command", command:"announcement"|"false_info"|"close_exit", ...}
##   {type:"inspect", agent_id}
##
## L'URL cible est résolue dans cet ordre : export `sim_ws_url`, variable
## d'environnement `SIM_WS_URL`, puis `SIMULATION_WS`, puis localhost.

@export var sim_ws_url: String = ""
@export var auto_reconnect: bool = true
@export var reconnect_interval: float = 3.0

var _ws: WebSocketPeer
var _ready_state: int = WebSocketPeer.STATE_CLOSED
var _reconnect_timer: float = 0.0
var _last_state: Dictionary = {}
var _agents: Array = []
var _received_counts: Dictionary = {}

func _ready() -> void:
	add_to_group("ws_client")
	sim_ws_url = _resolve_url()
	print("[ws_client] cible = ", sim_ws_url)
	_open()

func _resolve_url() -> String:
	if sim_ws_url != "":
		return sim_ws_url
	var env_url := OS.get_environment("SIM_WS_URL")
	if env_url == "":
		env_url = OS.get_environment("SIMULATION_WS")
	if env_url == "":
		env_url = "ws://localhost:8765"
	return env_url

func _open() -> void:
	if _ws != null:
		_ws.close()
	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(sim_ws_url)
	if err != OK:
		print("[ws_client] connect_to_url a échoué (", err, "), nouvelle tentative plus tard")

func _process(delta: float) -> void:
	if _ws == null:
		return
	_ws.poll()
	_ready_state = _ws.get_ready_state()
	match _ready_state:
		WebSocketPeer.STATE_OPEN:
			_reconnect_timer = 0.0
			_drain()
		WebSocketPeer.STATE_CLOSED:
			if auto_reconnect:
				_reconnect_timer += delta
				if _reconnect_timer >= reconnect_interval:
					_reconnect_timer = 0.0
					_open()

func _drain() -> void:
	while _ws.get_available_packet_count() > 0:
		var packet: PackedByteArray = _ws.get_packet()
		_handle_message(packet.get_string_from_utf8())

func _handle_message(text: String) -> void:
	var data: Variant = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		return
	var kind: String = data.get("type", "")
	_received_counts[kind] = int(_received_counts.get(kind, 0)) + 1
	match kind:
		"state":
			_last_state = data
			_agents = data.get("agents", [])
			_call_on("Header", "update_state", data)
			_call_on("AgentsLayer/AgentContainer", "update_state", data)
			_call_on("IndicatorChart", "set_horizon", int(data.get("max_ticks", 0)))
		"indicators":
			_call_on("IndicatorChart", "push_indicators", data)
		"inspection":
			_call_on("InspectPanel", "show_inspection", data)
		"control_ack":
			_call_on("ControlPanel", "on_ack", data)
		_:
			pass

func _call_on(relative_path: String, method: String, arg) -> void:
	var node := get_node_or_null(relative_path)
	if node != null and node.has_method(method):
		node.call(method, arg)

## Appelé par l'UI (boutons d'injection D3). Retourne true si envoyé.
func send_command(command: String, extra: Dictionary = {}) -> bool:
	if not is_open():
		push_warning("[ws_client] envoi impossible : WebSocket non ouvert")
		return false
	var payload: Dictionary = {"type": "command", "command": command}
	payload.merge(extra)
	_ws.send_text(JSON.stringify(payload))
	return true

## Appelé par le clic sur un agent (D2). Retourne true si envoyé.
func request_inspect(agent_id: String) -> bool:
	if not is_open():
		push_warning("[ws_client] inspection impossible : WebSocket non ouvert")
		return false
	_ws.send_text(JSON.stringify({"type": "inspect", "agent_id": agent_id}))
	return true

func get_agents() -> Array:
	return _agents

func is_open() -> bool:
	return _ws != null and _ready_state == WebSocketPeer.STATE_OPEN

func received_counts() -> Dictionary:
	return _received_counts

## Ferme proprement la connexion (arrêt volontaire du client) et empêche
## la reconnexion automatique.
func close_connection() -> void:
	auto_reconnect = false
	if _ws != null:
		_ws.close()
	_ready_state = WebSocketPeer.STATE_CLOSED
