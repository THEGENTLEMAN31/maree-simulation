extends SubViewport
## L'esplanade en 3D. Consommateur pur, comme le reste du client : la géométrie
## vient du plan reçu dans `hello`, l'état de l'instantané affiché.
##
## Repère : x monde -> X, y monde -> -Z, le nord s'éloigne de la caméra. Les
## hauteurs sont un choix d'affichage (le moteur est en 2D) : les murs du sud
## restent bas pour que personne ne soit jamais caché.
##
## main.gd dessine cette image dans la carte, puis le HUD par-dessus en
## projetant les points du monde avec `project()`.

const BODY_HEIGHT := 1.75
const OBSTACLE_HEIGHTS := {"tour": 6.0, "scene": 1.1, "stand": 2.3, "fontaine": 0.75}
const SIDE_COLORS := {
	"tour": Color("#5b5c66"),
	"scene": Color("#3a2f28"),
	"stand": Color("#45464f"),
	"fontaine": Color("#7c7e88"),
}
const EXIT_COLORS := {"A": Color("#56b4e9"), "B": Color("#e69f00"), "C": Color("#cc79a7")}
const NONE_COLOR := Color("#a1a1aa")
const CLOSED_COLOR := Color("#ef4444")

var _plan_h := 40.0
var _center := Vector3.ZERO
var _extent := Vector2(50, 30)
var _yaw := 0.0
var _pitch := 54.0
var _zoom := 1.0
var _camera: Camera3D
var _root: Node3D
var _bodies: Dictionary = {}
var _body_mesh: CapsuleMesh
var _head_mesh: SphereMesh
var _gates: Dictionary = {}
var _smoke: CPUParticles3D
var _smoke_ring: MeshInstance3D
var _density: MultiMeshInstance3D
var _assets: Dictionary = {}
var _glow: Texture2D


func setup(assets: Dictionary, glow: Texture2D) -> void:
	_assets = assets
	_glow = glow
	own_world_3d = true
	transparent_bg = false
	msaa_3d = Viewport.MSAA_4X
	render_target_update_mode = SubViewport.UPDATE_ALWAYS
	positional_shadow_atlas_size = 2048

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#10131c")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("#9aa3bd")
	env.ambient_light_energy = 0.34
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_light_color = Color("#141826")
	env.fog_density = 0.0035
	var holder := WorldEnvironment.new()
	holder.environment = env
	add_child(holder)

	var moon := DirectionalLight3D.new()
	moon.rotation_degrees = Vector3(-58, -38, 0)
	moon.light_color = Color("#dfe4ff")
	moon.light_energy = 0.8
	moon.shadow_enabled = true
	moon.directional_shadow_max_distance = 160.0
	moon.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	add_child(moon)

	_camera = Camera3D.new()
	_camera.fov = 30.0
	_camera.far = 400.0
	add_child(_camera)


func build(plan: Dictionary) -> void:
	if not plan.has("walkable"):
		return
	if _root != null:
		_root.queue_free()
	_bodies.clear()
	_gates.clear()
	_root = Node3D.new()
	add_child(_root)
	_plan_h = float(plan.get("height", 40.0))

	var points: Array = plan["walkable"]
	var bounds := Rect2(_v(points[0]), Vector2.ZERO)
	for p in points:
		bounds = bounds.expand(_v(p))
	_extent = bounds.size
	_center = _p3(bounds.get_center())

	_build_ground(bounds)
	_build_walls(bounds, plan.get("exits", []))
	for obstacle in plan.get("obstacles", []):
		_build_obstacle(obstacle)
	for exit in plan.get("exits", []):
		_build_gate(exit, bounds)
	_build_smoke()
	_build_density()
	_body_mesh = CapsuleMesh.new()
	_body_mesh.radius = 0.3
	_body_mesh.height = 1.35
	_head_mesh = SphereMesh.new()
	_head_mesh.radius = 0.17
	_head_mesh.height = 0.34
	frame()


func _v(point: Variant) -> Vector2:
	return Vector2(float(point[0]), float(point[1]))


func _p3(point: Vector2, height: float = 0.0) -> Vector3:
	return Vector3(point.x, height, _plan_h - point.y)


func _matte(color: Color, roughness: float = 0.9) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	return material


func _glowing(color: Color, energy: float = 0.55) -> StandardMaterial3D:
	var material := _matte(color)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = energy
	return material


func _box(size: Vector3, position: Vector3, material: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.position = position
	node.material_override = material
	_root.add_child(node)
	return node


func _build_ground(bounds: Rect2) -> void:
	var outside := PlaneMesh.new()
	outside.size = Vector2(320, 320)
	var far := MeshInstance3D.new()
	far.mesh = outside
	far.position = _center + Vector3(0, -0.06, 0)
	far.material_override = _matte(Color("#14161e"))
	_root.add_child(far)

	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = bounds.size
	var material := _matte(Color("#c9cbd6"), 0.82)
	if _assets.has("paving"):
		material.albedo_texture = _assets["paving"]
		material.uv1_scale = Vector3(bounds.size.x / 12.5, bounds.size.y / 12.5, 1.0)
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	var ground := MeshInstance3D.new()
	ground.mesh = floor_mesh
	ground.position = _center
	ground.material_override = material
	_root.add_child(ground)


## Quatre murs, percés aux sorties. Hauteur décroissante vers la caméra.
func _build_walls(bounds: Rect2, exits: Array) -> void:
	var stone := _matte(Color("#5d5f6c"))
	var sides := [
		[Vector2(bounds.position.x, bounds.end.y), Vector2(bounds.end.x, bounds.end.y), 3.0],
		[bounds.position, Vector2(bounds.end.x, bounds.position.y), 0.45],
		[bounds.position, Vector2(bounds.position.x, bounds.end.y), 1.6],
		[Vector2(bounds.end.x, bounds.position.y), bounds.end, 1.6],
	]
	for side in sides:
		var a: Vector2 = side[0]
		var b: Vector2 = side[1]
		var height: float = side[2]
		var length := a.distance_to(b)
		var dir := (b - a) / length
		var cuts: Array = []
		for exit in exits:
			var ea := _v(exit["a"])
			var eb := _v(exit["b"])
			if absf((ea - a).cross(dir)) < 0.05 and absf((eb - a).cross(dir)) < 0.05:
				var t0 := (ea - a).dot(dir)
				var t1 := (eb - a).dot(dir)
				cuts.append([minf(t0, t1), maxf(t0, t1)])
		cuts.sort_custom(func(p, q): return float(p[0]) < float(q[0]))
		var from := 0.0
		cuts.append([length, length])
		for cut in cuts:
			var to := float(cut[0])
			if to - from > 0.01:
				var mid := a + dir * (from + to) * 0.5
				var horizontal := absf(dir.x) > 0.5
				var size := Vector3(to - from, height, 0.5) if horizontal else Vector3(0.5, height, to - from)
				_box(size, _p3(mid, height * 0.5), stone)
			from = float(cut[1])


func _build_obstacle(obstacle: Dictionary) -> void:
	var polygon: Array = obstacle.get("polygon", [])
	if polygon.size() < 3:
		return
	var kind := str(obstacle.get("kind", ""))
	var height: float = OBSTACLE_HEIGHTS.get(kind, 1.5)
	var box := Rect2(_v(polygon[0]), Vector2.ZERO)
	for point in polygon:
		box = box.expand(_v(point))

	var sides := SurfaceTool.new()
	sides.begin(Mesh.PRIMITIVE_TRIANGLES)
	var top := SurfaceTool.new()
	top.begin(Mesh.PRIMITIVE_TRIANGLES)

	# Orientation : les faces doivent regarder dehors, quel que soit le sens du polygone.
	var area := 0.0
	for i in range(polygon.size()):
		area += _v(polygon[i]).cross(_v(polygon[(i + 1) % polygon.size()]))
	var flip := area > 0.0

	for i in range(polygon.size()):
		var a := _v(polygon[i])
		var b := _v(polygon[(i + 1) % polygon.size()])
		if flip:
			var swap := a
			a = b
			b = swap
		var a0 := _p3(a)
		var b0 := _p3(b)
		var a1 := _p3(a, height)
		var b1 := _p3(b, height)
		for vertex in [a0, a1, b1, a0, b1, b0]:
			sides.add_vertex(vertex)

	var uv := func(p: Vector2) -> Vector2:
		return Vector2((p.x - box.position.x) / box.size.x, 1.0 - (p.y - box.position.y) / box.size.y)
	var first := _v(polygon[0])
	for i in range(1, polygon.size() - 1):
		var fan := [first, _v(polygon[i]), _v(polygon[i + 1])]
		if flip:
			fan = [first, _v(polygon[i + 1]), _v(polygon[i])]
		for p in fan:
			top.set_uv(uv.call(p))
			top.add_vertex(_p3(p, height))

	sides.generate_normals()
	top.generate_normals()
	var side_node := MeshInstance3D.new()
	side_node.mesh = sides.commit()
	side_node.material_override = _matte(SIDE_COLORS.get(kind, Color("#45464f")))
	_root.add_child(side_node)

	var top_material := _matte(Color.WHITE, 0.75)
	if _assets.has(kind):
		top_material.albedo_texture = _assets[kind]
	var top_node := MeshInstance3D.new()
	top_node.mesh = top.commit()
	top_node.material_override = top_material
	_root.add_child(top_node)

	# Lumière chaude de la fête, sur les stands et la scène : du décor, pas un signal.
	if kind == "stand" or kind == "scene":
		var lamp := OmniLight3D.new()
		lamp.position = _p3(box.get_center(), height + 1.6)
		lamp.light_color = Color("#ffdcb8")
		lamp.light_energy = 0.9 if kind == "stand" else 1.4
		lamp.omni_range = 9.0 if kind == "stand" else 13.0
		_root.add_child(lamp)


func _build_gate(exit: Dictionary, bounds: Rect2) -> void:
	var a := _v(exit["a"])
	var b := _v(exit["b"])
	var id := str(exit["id"])
	var color: Color = EXIT_COLORS.get(id, NONE_COLOR)
	var material := _glowing(color)
	var south := absf((a.y + b.y) * 0.5 - bounds.position.y) < 0.5
	var height := 0.5 if south else 3.4
	var nodes: Array = []
	for p in [a, b]:
		nodes.append(_box(Vector3(0.45, height, 0.45), _p3(p, height * 0.5), material))
	var horizontal := absf(a.x - b.x) > absf(a.y - b.y)
	var length := a.distance_to(b)
	var mid := (a + b) * 0.5
	var size := Vector3(length, 0.28, 0.45) if horizontal else Vector3(0.45, 0.28, length)
	nodes.append(_box(size, _p3(mid, height), material))

	var bar_size := Vector3(length, 1.1, 0.16) if horizontal else Vector3(0.16, 1.1, length)
	var bar := _box(bar_size, _p3(mid, 0.55), _glowing(CLOSED_COLOR, 0.9))
	bar.visible = false

	var lamp := OmniLight3D.new()
	lamp.position = _p3(mid, 2.2)
	lamp.light_color = color
	lamp.light_energy = 1.1
	lamp.omni_range = 8.0
	_root.add_child(lamp)
	_gates[id] = {"material": material, "bar": bar, "lamp": lamp, "color": color}


func _build_smoke() -> void:
	_smoke = CPUParticles3D.new()
	_smoke.amount = 280
	_smoke.lifetime = 7.0
	_smoke.preprocess = 7.0
	_smoke.emitting = false
	_smoke.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	_smoke.direction = Vector3.UP
	_smoke.spread = 25.0
	_smoke.gravity = Vector3(0.1, 0.25, 0)
	_smoke.initial_velocity_min = 0.2
	_smoke.initial_velocity_max = 0.7
	_smoke.scale_amount_min = 5.0
	_smoke.scale_amount_max = 10.0
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.5))
	curve.add_point(Vector2(1, 1.3))
	_smoke.scale_amount_curve = curve
	var ramp := Gradient.new()
	ramp.set_color(0, Color(0.72, 0.73, 0.78, 0.0))
	ramp.set_color(1, Color(0.6, 0.61, 0.66, 0.0))
	ramp.add_point(0.2, Color(0.74, 0.75, 0.8, 0.3))
	ramp.add_point(0.7, Color(0.64, 0.65, 0.7, 0.2))
	_smoke.color_ramp = ramp
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.vertex_color_use_as_albedo = true
	material.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	material.albedo_texture = _glow
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	quad.material = material
	_smoke.mesh = quad
	_root.add_child(_smoke)

	var ring := TorusMesh.new()
	_smoke_ring = MeshInstance3D.new()
	_smoke_ring.mesh = ring
	var ring_material := StandardMaterial3D.new()
	ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring_material.albedo_color = Color(0.9, 0.9, 0.92, 0.4)
	_smoke_ring.material_override = ring_material
	_smoke_ring.visible = false
	_root.add_child(_smoke_ring)


func _build_density() -> void:
	var quad := QuadMesh.new()
	quad.size = Vector2(3.8, 3.8)
	quad.orientation = PlaneMesh.FACE_Y
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.vertex_color_use_as_albedo = true
	material.albedo_texture = _glow
	quad.material = material
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.use_colors = true
	multi.mesh = quad
	multi.instance_count = 400
	multi.visible_instance_count = 0
	_density = MultiMeshInstance3D.new()
	_density.multimesh = multi
	_root.add_child(_density)


func _body_for(id: String) -> Dictionary:
	if _bodies.has(id):
		return _bodies[id]
	var node := Node3D.new()
	var material := _matte(NONE_COLOR, 0.55)
	var torso := MeshInstance3D.new()
	torso.mesh = _body_mesh
	torso.position.y = 0.72
	torso.material_override = material
	var head := MeshInstance3D.new()
	head.mesh = _head_mesh
	head.position.y = 1.56
	head.material_override = _matte(Color("#d9c7b4"), 0.6)
	node.add_child(torso)
	node.add_child(head)
	_root.add_child(node)
	var body := {"node": node, "material": material, "head": head.material_override, "last": Vector2.INF}
	_bodies[id] = body
	return body


## Pose les personnes aux positions interpolées (`positions` : id -> Vector2).
func sync_agents(agents: Array, positions: Dictionary, selected: String, now_s: float) -> void:
	if _root == null:
		return
	var seen := {}
	for agent in agents:
		var id := str(agent.get("id", ""))
		if bool(agent.get("evacuated", false)) or not positions.has(id):
			continue
		seen[id] = true
		var body := _body_for(id)
		var node: Node3D = body["node"]
		var pos: Vector2 = positions[id]
		var last: Vector2 = body["last"]
		var moved := 0.0 if last == Vector2.INF else pos.distance_to(last)
		var bob := 0.0
		if moved > 0.002:
			var step := _p3(pos) - _p3(last)
			node.rotation.y = atan2(step.x, step.z)
			bob = absf(sin(now_s * 9.0 + float(id.hash() % 7))) * 0.07
		body["last"] = pos
		node.position = _p3(pos, bob)
		node.visible = true
		var color: Color = EXIT_COLORS.get(str(agent.get("belief", "")), NONE_COLOR)
		var material: StandardMaterial3D = body["material"]
		var dim := selected != "" and id != selected
		material.albedo_color = color.darkened(0.62) if dim else color
		material.emission_enabled = id == selected
		material.emission = color
		material.emission_energy_multiplier = 0.6
	for id in _bodies:
		if not seen.has(id):
			_bodies[id]["node"].visible = false


func sync_world(snap: Dictionary, smoke: Dictionary, show_density: bool) -> void:
	if _root == null:
		return
	var open: Array = snap.get("exits_open", [])
	for id in _gates:
		var gate: Dictionary = _gates[id]
		var is_open: bool = open.is_empty() or id in open
		var color: Color = gate["color"] if is_open else CLOSED_COLOR
		var material: StandardMaterial3D = gate["material"]
		material.albedo_color = color
		material.emission = color
		gate["lamp"].light_color = color
		gate["bar"].visible = not is_open

	var active := not smoke.is_empty()
	if active:
		var centre := _v(smoke["position"])
		var radius := float(smoke["radius"])
		_smoke.position = _p3(centre, 1.2)
		_smoke.emission_box_extents = Vector3(radius * 0.62, 1.2, radius * 0.62)
		_smoke_ring.position = _p3(centre, 0.04)
		var ring: TorusMesh = _smoke_ring.mesh
		ring.outer_radius = radius
		ring.inner_radius = radius - 0.12
	_smoke.emitting = active
	_smoke.visible = active
	_smoke_ring.visible = active

	var multi := _density.multimesh
	var n := 0
	if show_density:
		for cell in snap.get("density_grid", []):
			var count := int(cell.get("n", 0))
			if count < 2 or n >= multi.instance_count:
				continue
			var at := _p3(Vector2(float(cell["x"]) + 0.5, float(cell["y"]) + 0.5), 0.05)
			multi.set_instance_transform(n, Transform3D(Basis.IDENTITY, at))
			multi.set_instance_color(n, Color(0.984, 0.573, 0.235, minf(0.14 * float(count), 0.46)))
			n += 1
	multi.visible_instance_count = n


## Cadre tout le plan, avec de la marge pour les étiquettes de sorties.
func frame() -> void:
	if _camera == null:
		return
	var aspect := float(size.x) / maxf(float(size.y), 1.0)
	var vfov := deg_to_rad(_camera.fov)
	var hfov := 2.0 * atan(tan(vfov * 0.5) * aspect)
	var depth := _extent.y * sin(deg_to_rad(_pitch))
	var fit_w := (_extent.x * 1.2) / (2.0 * tan(hfov * 0.5))
	var fit_h := (depth * 1.42) / (2.0 * tan(vfov * 0.5))
	var distance := maxf(fit_w, fit_h) * _zoom
	var orbit := Basis(Vector3.UP, deg_to_rad(_yaw)) * Basis(Vector3.RIGHT, deg_to_rad(-_pitch))
	_camera.position = _center + orbit * Vector3(0, 0, distance)
	_camera.look_at(_center, Vector3.UP)


func orbit(delta_yaw: float, delta_pitch: float) -> void:
	_yaw = clampf(_yaw + delta_yaw, -70.0, 70.0)
	_pitch = clampf(_pitch + delta_pitch, 30.0, 80.0)
	frame()


func zoom_by(factor: float) -> void:
	_zoom = clampf(_zoom * factor, 0.45, 1.2)
	frame()


func project(point: Vector2, height: float = 0.0) -> Vector2:
	if _camera == null or not _camera.is_inside_tree():
		return Vector2.ZERO
	return _camera.unproject_position(_p3(point, height))


## Point du sol sous un pixel de l'image, en mètres dans le repère du moteur.
func ground_at(pixel: Vector2) -> Vector2:
	if _camera == null or not _camera.is_inside_tree():
		return Vector2(-1, -1)
	var origin := _camera.project_ray_origin(pixel)
	var direction := _camera.project_ray_normal(pixel)
	if absf(direction.y) < 0.0001:
		return Vector2(-1, -1)
	var hit := origin + direction * (-origin.y / direction.y)
	return Vector2(hit.x, _plan_h - hit.z)
