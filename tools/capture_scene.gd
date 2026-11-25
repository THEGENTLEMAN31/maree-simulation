extends SceneTree
## Capture de `res://scenes/main.tscn` sans écran, en OpenGL réel.
##
## Usage (depuis la racine du dépôt) :
##   godot --path godot/project --rendering-driver opengl3 \
##         --script "$PWD/tools/capture_scene.gd"
##
## `--headless` est exclu : son pilote de rendu factice renvoie une texture
## nulle. Le viewport hors écran est un SubViewport dimensionné par
## l'environnement ; la fenêtre du DisplayServer n'intervient pas dans le PNG.
##
## Variables d'environnement :
##   MAREE_CAPTURE_W / MAREE_CAPTURE_H  résolution du PNG (défaut : projet)
##   MAREE_CAPTURE_PATH                 fichier .png ou dossier de sortie
##                                      (défaut : <dépôt>/captures/)
##   MAREE_CAPTURE_FRAMES               frames à attendre (défaut 30)
##   MAREE_CAPTURE_WAIT_S               secondes à attendre en plus (défaut 0)
##
## Le client lit aussi MAREE_WS_URL et MAREE_SELECT (voir scripts/main.gd).

const DEFAULT_FRAMES := 30
const MAX_FRAMES := 600

var _frames := 0
var _needed := DEFAULT_FRAMES
var _wait_ms := 0
var _start_ms := 0
var _path := ""
var _target: SubViewport
var _done := false


func _initialize() -> void:
	var width := _env_int("MAREE_CAPTURE_W", int(ProjectSettings.get_setting("display/window/size/viewport_width", 1000)))
	var height := _env_int("MAREE_CAPTURE_H", int(ProjectSettings.get_setting("display/window/size/viewport_height", 640)))
	_needed = clampi(_env_int("MAREE_CAPTURE_FRAMES", DEFAULT_FRAMES), 1, MAX_FRAMES)
	_wait_ms = int(OS.get_environment("MAREE_CAPTURE_WAIT_S").to_float() * 1000.0)
	_start_ms = Time.get_ticks_msec()
	_path = _output_path()

	_target = SubViewport.new()
	_target.size = Vector2i(width, height)
	_target.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_target)

	var scene_path := OS.get_environment("MAREE_SCENE")
	if scene_path.is_empty():
		# `--view=top` (ou MAREE_VIEW=top) capture l'ancien rendu 2D.
		if OS.get_environment("MAREE_VIEW") == "top":
			scene_path = "res://scenes/top.tscn"
		else:
			scene_path = "res://scenes/main.tscn"
	var scene: PackedScene = load(scene_path) as PackedScene
	if scene == null:
		push_error("capture : %s introuvable" % scene_path)
		quit(1)
		return
	_target.add_child(scene.instantiate())
	print("capture : %dx%d · %d frames · %s · %s" % [width, height, _needed, scene_path, _path])


func _process(_delta: float) -> bool:
	if _done:
		return true
	_frames += 1
	if _frames < _needed or Time.get_ticks_msec() - _start_ms < _wait_ms:
		return false

	var image: Image = _target.get_texture().get_image()
	if image == null or image.is_empty():
		if _frames >= MAX_FRAMES:
			push_error("capture : texture vide après %d frames" % _frames)
			_done = true
			quit(1)
		return false

	_dir_for(_path)
	var err := image.save_png(_path)
	if err != OK:
		push_error("capture : save_png a échoué pour %s (code %d)" % [_path, err])
		_done = true
		quit(1)
		return true
	# L'état du client est journalisé pour dater la capture sans lire l'image :
	# le tick et la fumée viennent de la dernière trame reçue par main.gd.
	var state: Dictionary = {}
	for child in _target.get_children():
		var candidate: Variant = child.get("_snap")
		if typeof(candidate) == TYPE_DICTIONARY:
			state = candidate
			break
	print("capture : état tick=%s agents=%d fumée=%s" % [
		str(state.get("tick", "?")), (state.get("agents", []) as Array).size(),
		str(state.get("smoke_active", false)),
	])
	var file := FileAccess.open(_path, FileAccess.READ)
	var size := file.get_length() if file != null else -1
	print("capture : écrit %s (%dx%d, %d octets)" % [
		_path, image.get_width(), image.get_height(), size,
	])
	_done = true
	quit(0)
	return true


func _env_int(name: String, fallback: int) -> int:
	var raw := OS.get_environment(name)
	if raw.is_empty():
		return fallback
	var value := raw.to_int()
	return value if value > 0 else fallback


func _output_path() -> String:
	var stamp := Time.get_datetime_string_from_system(true, true)
	stamp = stamp.replace("-", "").replace(":", "").replace(" ", "_")
	stamp += "_%03d" % (Time.get_ticks_msec() % 1000)
	var filename := "main_%s.png" % stamp

	var raw := OS.get_environment("MAREE_CAPTURE_PATH")
	# Les chemins relatifs sont résolus depuis la racine du dépôt, pas depuis
	# godot/project : `capture.sh` peut être appelé depuis n'importe où.
	if raw.is_empty():
		return _repo_root().path_join("captures").path_join(filename)
	if not raw.begins_with("/"):
		raw = _repo_root().path_join(raw)
	if raw.ends_with(".png"):
		return raw
	return raw.path_join(filename)


func _repo_root() -> String:
	# res:// pointe sur <dépôt>/godot/project ; le dépôt est deux niveaux au-dessus.
	var project := ProjectSettings.globalize_path("res://").trim_suffix("/")
	return project.get_base_dir().get_base_dir()


func _dir_for(file_path: String) -> void:
	var dir := file_path.get_base_dir()
	if not dir.is_empty() and not DirAccess.dir_exists_absolute(dir):
		var err := DirAccess.make_dir_recursive_absolute(dir)
		if err != OK:
			push_error("capture : impossible de créer %s (code %d)" % [dir, err])
