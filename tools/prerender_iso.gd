extends SceneTree
## Pré-rendu isométrique des modèles 3D en sprites PNG (M-06).
##
## Godot sait rendre en OpenGL réel sans écran (`--rendering-driver opengl3`,
## DISPLAY peut être absent — un SubViewport hors écran suffit). On charge
## chaque `.glb`/`.gltf` livré par M-04, on le place sous une caméra
## **orthographique isométrique** (lacet 45°, inclinaison 35,264° — le vrai
## isométrique 2:1), on l'éclaire de façon neutre, et on sauvegarde un PNG à
## fond transparent dans `res://assets/sprites_iso/`.
##
## C'est du **vrai asset** : aucun modèle d'image n'intervient, on ne fait que
## photographier la géométrie téléchargée. Le runtime n'a plus qu'à charger le
## PNG (coût nul) au lieu de rendre la 3D.
##
## Usage (depuis la racine du dépôt) :
##   godot --path godot/project --rendering-driver opengl3 \
##         --script "$PWD/tools/prerender_iso.gd"
##
## Variables d'environnement :
##   ISO_SPRITE_SIZE   côté du PNG carré (défaut 256)
##   ISO_FRAMES        frames de rendu par modèle (défaut 8)
##   ISO_ONLY          ne rendre qu'un modèle dont le nom contient ce texte

const OUT_DIR := "res://assets/sprites_iso"

## Modèles à pré-rendre : les intérieurs pertinents (M-04), pas les décors
## extérieurs rangés dans `_hors-sujet-exterieur/`.
const MODELS := [
	"res://assets/models/kenney/building-kit/stairs-open.glb",
	"res://assets/models/kenney/building-kit/stairs-sides.glb",
	"res://assets/models/kenney/building-kit/wall-low.glb",
	"res://assets/models/kenney/modular-buildings/door-white-glass.glb",
	"res://assets/models/kenney/modular-buildings/window-white-large.glb",
	"res://assets/models/kenney/modular-buildings/building-window-large.glb",
	"res://assets/models/kenney/platformer-kit/platform-ramp.glb",
	"res://assets/models/kenney/platformer-kit/sign.glb",
	"res://assets/models/poly_haven/painted_wooden_bench_1k/painted_wooden_bench_1k.gltf",
	"res://assets/models/poly_haven/planter_box_02_1k/planter_box_02_1k.gltf",
	"res://assets/models/poly_haven/metal_trash_can_1k/metal_trash_can_1k.gltf",
	"res://assets/models/poly_haven/wooden_display_shelves_01_1k/wooden_display_shelves_01_1k.gltf",
	"res://assets/models/poly_haven/modern_ceiling_lamp_01_1k/modern_ceiling_lamp_01_1k.gltf",
]

var _size := 256
var _frames := 8
var _only := ""
var _queue: Array[String] = []
var _index := 0
var _frame := 0
var _viewport: SubViewport
var _stage: Node3D
var _camera: Camera3D
var _done := false
var _started := false
var _written := 0


func _initialize() -> void:
	_size = _env_int("ISO_SPRITE_SIZE", 256)
	_frames = _env_int("ISO_FRAMES", 8)
	_only = OS.get_environment("ISO_ONLY")
	for path in MODELS:
		if _only.is_empty() or path.contains(_only):
			_queue.append(path)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))
	print("pré-rendu iso : %d modèle(s) -> %s (%dpx, %d frames)" % [
		_queue.size(), OUT_DIR, _size, _frames,
	])
	if _queue.is_empty():
		_done = true
		quit(0)
		return
	# Le viewport et le premier modèle sont construits au premier `_process`,
	# quand l'arbre est prêt : `get_global_transform()` y est fiable (il
	# renvoyait une matrice nulle pendant `_initialize`, d'où un PNG vide).
	_started = false


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(_size, _size)
	_viewport.transparent_bg = true
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.msaa_3d = Viewport.MSAA_4X
	root.add_child(_viewport)

	_stage = Node3D.new()
	_viewport.add_child(_stage)

	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.rotation_degrees = Vector3(-35.264, 45.0, 0.0)
	_stage.add_child(_camera)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, -38.0, 0.0)
	sun.light_energy = 1.15
	sun.light_color = Color(1.0, 0.98, 0.95)
	sun.shadow_enabled = false
	_stage.add_child(sun)

	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20.0, 140.0, 0.0)
	fill.light_energy = 0.45
	fill.light_color = Color(0.85, 0.90, 1.0)
	fill.shadow_enabled = false
	_stage.add_child(fill)

	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.background_color = Color(0.0, 0.0, 0.0, 0.0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.62, 0.64, 0.70)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	_stage.add_child(we)


func _load_next() -> void:
	# On retire le modèle précédent (nommé "Model") sans toucher aux lumières
	# ni à la caméra, qui restent en place d'un modèle à l'autre.
	var previous := _stage.get_node_or_null("Model")
	if previous != null:
		_stage.remove_child(previous)
		previous.free()

	var path := _queue[_index]
	var packed: PackedScene = load(path) as PackedScene
	if packed == null:
		push_error("pré-rendu : chargement impossible : %s" % path)
		_next()
		return
	var model := packed.instantiate()
	model.name = "Model"
	_stage.add_child(model)
	_frame = 0
	_frame_camera(model)


func _frame_camera(model: Node) -> void:
	var box := _aabb_of(model)
	if box.size.length() < 0.0001:
		box = AABB(Vector3(-1, -1, -1), Vector3(2, 2, 2))
	var centre := box.get_center()
	var radius: float = max(box.size.x, max(box.size.y, box.size.z))
	_camera.size = radius * 1.35
	var back := _camera.global_transform.basis.z.normalized()
	var eye := centre + back * (radius * 3.0 + 4.0)
	_camera.look_at_from_position(eye, centre, Vector3.UP)


func _aabb_of(node: Node) -> AABB:
	var result := AABB()
	var first := true
	var stack: Array[Node] = [node]
	while not stack.is_empty():
		var current: Node = stack.pop_back()
		for child in current.get_children():
			stack.append(child)
		if current is MeshInstance3D and current.mesh != null:
			var box: AABB = current.global_transform * current.get_aabb()
			if first:
				result = box
				first = false
			else:
				result = result.merge(box)
	return result


func _process(_delta: float) -> bool:
	if _done:
		return true
	if not _started:
		_started = true
		_build_viewport()
		_load_next()
		return false
	_frame += 1
	if _frame < _frames:
		return false
	var image := _viewport.get_texture().get_image()
	if image == null or image.is_empty():
		push_error("pré-rendu : image vide pour %s" % _queue[_index])
		_next()
		return false
	var name := _sprite_name(_queue[_index])
	var out := OUT_DIR.path_join(name)
	var err := image.save_png(out)
	if err != OK:
		push_error("pré-rendu : save_png a échoué (%s, code %d)" % [out, err])
	else:
		_written += 1
		var bytes := FileAccess.get_file_as_bytes(out).size()
		print("  sprite : %s (%dx%d, %d o)" % [
			name, image.get_width(), image.get_height(), bytes,
		])
	_next()
	return false


func _next() -> void:
	_index += 1
	if _index >= _queue.size():
		_done = true
		print("pré-rendu iso : %d sprite(s) écrit(s)" % _written)
		quit(0)
		return
	_load_next()


func _sprite_name(path: String) -> String:
	var base := path.get_file().get_basename()
	return base + ".png"


func _env_int(name: String, fallback: int) -> int:
	var raw := OS.get_environment(name)
	if raw.is_empty():
		return fallback
	var value := raw.to_int()
	return value if value > 0 else fallback