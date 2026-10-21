extends SceneTree
## Capture d'écran du rendu réel (banc de revue visuelle).
## Lancer sous Xvfb :
##   DISPLAY=:99 godot --path /godot/project --script res://tests/screenshot.gd
## Écrit /out/shot.png (vue principale) et /out/shot_inspect.png (D2).

const OUT := "/out/shot.png"
const OUT_INSPECT := "/out/shot_inspect.png"
const WARMUP_FRAMES := 150

var _frames := 0
var _busy := false
var _scene: Node = null

const INSPECTION := {
	"type": "inspection",
	"agent_id": "agent_03",
	"profile": "habitué",
	"kind": "llm",
	"zone": "scene",
	"belief": "A",
	"evacuated": false,
	"trapped": false,
	"last_action": "evacuate",
	"last_exit": "A",
	"decisions": 4,
	"explanation": {
		"kind": "llm",
		"reasoning": "L'annonce du haut-parleur indique la sortie C, mais la fumée monte au sud : je rejoins A par le parvis est, plus dégagé.",
	},
	"intention": {"action": "evacuate", "exit_code": "A", "target_zone": "sortie_a"},
	"memory": [
		{"tick": 0, "kind": "échange", "text": "Édition précédente : la passerelle était saturée, nous sommes passés par l'allée ouest."},
		{"tick": 4, "kind": "annonce", "text": "Annonce : évacuation par la sortie C."},
		{"tick": 8, "kind": "observation", "text": "Fumée visible côté sud-est."},
	],
	"last_rag": [
		{"doc_id": "souvenirs/edition_2019_passerelle", "score": 0.82},
		{"doc_id": "plan/acces_sortie_a", "score": 0.78},
		{"doc_id": "consignes/securite_foule", "score": 0.71},
	],
	"drifts": [],
}


func _init() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	_scene = packed.instantiate()
	root.add_child(_scene)


func _process(_delta: float) -> bool:
	if _busy:
		return false
	_frames += 1
	if _frames >= WARMUP_FRAMES:
		_busy = true
		_sequence()
	return false


func _capture(path: String) -> void:
	await RenderingServer.frame_post_draw
	var img: Image = root.get_texture().get_image()
	var err := img.save_png(path)
	print("[screenshot] ", path, " err=", err, " taille=", img.get_size())


func _sequence() -> void:
	await _capture(OUT)
	var world := _scene.get_node_or_null("World")
	if world != null:
		world._handle_message(JSON.stringify(INSPECTION))
	for i in 12:
		await process_frame
	await _capture(OUT_INSPECT)
	quit()
