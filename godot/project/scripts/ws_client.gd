extends Node2D
## Client WebSocket vers python-sim (décision 9 : Godot est un consommateur
## pur — aucune logique de simulation ici).
## Reçoit : {type:"state", tick, smoke_level, agents:[{id,zone,belief,kind}]}
##          {type:"indicators", tick, I1_consensus, I2_belief_gap, ...}
## Envoie : {type:"command", command:"announcement"|"false_info"|"close_exit", ...}
##          {type:"inspect", agent_id}

@export var sim_ws_url: String = "ws://localhost:8765"
@export var auto_reconnect: bool = true

var _ws: WebSocketPeer
var _connected: bool = false
var _reconnect_timer: float = 0.0
var _last_state: Dictionary = {}
var _agents: Array = []

func _ready() -> void:
	_ws = WebSocketPeer.new()
	_connect()

func _process(delta: float) -> void:
	if not _connected:
		_reconnect_timer += delta
		if _reconnect_timer > 3.0 and auto_reconnect:
			_reconnect_timer = 0.0
			_connect()
		return
	_ws.poll()
	while _ws.get_available_packet_count() > 0:
		var packet: PackedByteArray = _ws.get_packet().to_byte_array()
		var text: String = packet.get_string_from_utf8()
		_handle_message(text)

func _connect() -> void:
	_connected = false
	_ws.connect_to_url(sim_ws_url)
	# premières tentatives : état texte (relaxe le timeout par défaut)
	_ws.send_text("{\"type\":\"ping\"}")

func _handle_message(text: String) -> void:
	if text.begins_with("{"):
		var data: Dictionary = JSON.parse_string(text)
		if data.is_empty():
			return
		var kind: String = data["type"]
		match kind:
			"state":
				_last_state = data
				_agents = data["agents"]
				# propagation aux rendus
				var agents_view := get_node("/root/AgentsLayer/AgentContainer")
				if is_instance_valid(agents_view):
					agents_view.update_state(data)
			"indicators":
				var chart := get_node("/root/IndicatorChart")
				if is_instance_valid(chart):
					chart.push_indicators(data)
			"inspection":
				var panel := get_node("/root/InspectPanel")
				if is_instance_valid(panel):
					panel.show_inspection(data)
			_:
				pass

## Appelé par l'UI (boutons d'injection D3).
func send_command(command: String, extra: Dictionary = {}) -> void:
	var payload: Dictionary = {"type": "command", "command": command}
	payload.merge(extra)
	_ws.send_text(JSON.stringify(payload))

## Appelé par le clic sur un agent (D2).
func request_inspect(agent_id: String) -> void:
	_ws.send_text(JSON.stringify({"type": "inspect", "agent_id": agent_id}))

func get_agents() -> Array:
	return _agents

func is_connected() -> bool:
	return _connected