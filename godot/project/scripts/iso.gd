extends Node2D
## Client de visualisation MARÉE — rendu **isométrique 2.5D** (M-06).
##
## Il ne simule rien et ne décide rien : il reçoit le plan (WebSocket v2) ou
## charge la géométrie versionnée du monde (`assets/world/mall_aubel.json`),
## et dessine. Toute la topologie vient du monde ; il n'y a pas de deuxième
## source de vérité en GDScript.
##
## Pourquoi l'isométrique et pas la 3D (voir docs/visuel/ISO.md) :
##   * le point de vue est fixe, l'information utile est la **répartition des
##     croyances**, pas la géométrie ;
##   * la 3D coûterait un pipeline glTF/PBR, une caméra, des ombres ;
##   * l'isométrique accepte des **tuiles et des sprites réels** (pré-rendus
##     depuis les glTF de M-04, coût nul au runtime) et garde la lisibilité.
##
## Projection 2:1 : (x, y) -> ((x - y)·k, (x + y)·k/2). L'inverse sert à
## cliquer un agent. Le tri de profondeur se fait sur (x + y) : les objets les
## plus proches (grand x+y) sont dessinés en dernier.
##
## Modes :
##   * `--view=top` (ou `MAREE_VIEW=top`) : repli sur l'ancien rendu 2D vu de
##     dessus (`scenes/top.tscn`), pour comparer ;
##   * `MAREE_DEMO=1` : population déterministe de démonstration (aucun
##     serveur), pour les captures de documentation — ce n'est pas une
##     mesure, c'est une illustration du rendu ;
##   * `MAREE_LEVEL=L0|L1|cut` : niveau affiché (défaut `cut`, la coupe).

const MARGIN := 16.0
const PANEL_W := 320.0
const HUD_H := 112.0
const BOTTOM_H := 112.0
const BANNER_MS := 9000.0

#: facteur d'élévation : 1 m de hauteur = _ELEV_K·k pixels vers le haut.
const ELEV_K := 1.15
#: hauteur verticale d'un mètre en pixels = _Z_K·k.
const Z_K := 0.9

const BELIEF_COLORS := {
	"A": Color(0.30, 0.58, 1.00),   # Grand Quai
	"B": Color(0.30, 0.85, 0.45),   # Ruelle des Cordiers
	"C": Color(1.00, 0.66, 0.20),   # Passage des Halles
	"D": Color(0.80, 0.45, 0.95),   # terrasse ouest (L1)
	"E": Color(0.20, 0.80, 0.85),   # terrasse est (L1)
}
const UNKNOWN := Color(0.52, 0.54, 0.58)
const INK := Color(0.88, 0.90, 0.93)
const DIM := Color(0.55, 0.58, 0.62)
const WARN := Color(1.00, 0.72, 0.30)

const FLOOR_A := Color(0.30, 0.31, 0.34)
const FLOOR_B := Color(0.26, 0.27, 0.30)
const GRID := Color(0.38, 0.40, 0.44, 0.55)
const WALL_TOP := Color(0.74, 0.72, 0.68)
const WALL_SIDE_R := Color(0.46, 0.44, 0.42)
const WALL_SIDE_L := Color(0.56, 0.54, 0.51)

var _ws := WebSocketPeer.new()
var _plan: Dictionary = {}
var _world: Dictionary = {}
var _snap: Dictionary = {}
var _ind: Dictionary = {}
var _narratives: Array[String] = []
var _selected := ""
var _status := "connexion…"
var _font: Font

# --- projection isométrique ----------------------------------------
var _k := 10.0
var _off := Vector2.ZERO
var _level_mode := "cut"      # L0 | L1 | cut
var _demo := false
var _demo_smoke := true

# --- D3 : état d'injection -----------------------------------------
var _live := false
var _world_smoke: Dictionary = {}
var _announcement := ""
var _announcement_at := -100000.0
var _notes: Array[String] = []
var _last_click_m := Vector2(-1.0, -1.0)
var _announce_edit: LineEdit
var _exit_pick: OptionButton
var _buttons: Array[Button] = []
var _hint: Label
var _panel: PanelContainer
var _toggle: Button

# --- F6 : indicateurs cliquables -----------------------------------
var _ind_boxes: Array = []
var _trace: Dictionary = {}

#: sprites pré-rendus (M-04 -> PNG isométriques), chargés une fois.
var _sprites: Dictionary = {}
#: décor placé dans le hall (sprites réels, positions déterministes).
var _decor: Array = []


func _ready() -> void:
	_font = ThemeDB.fallback_font
	_demo = OS.get_environment("MAREE_DEMO") == "1"
	_demo_smoke = OS.get_environment("MAREE_SMOKE") != "0"
	_fps_on = OS.get_environment("MAREE_FPS") == "1"
	_fps_t = Time.get_ticks_msec() / 1000.0
	var lvl := OS.get_environment("MAREE_LEVEL")
	if lvl != "":
		_level_mode = lvl
	if _view_mode() == "top":
		call_deferred("_swap_to_top")
		return
	_load_world()
	_load_sprites()
	_build_inject_ui()
	if _demo:
		_populate_demo()
	_ws.inbound_buffer_size = 8 * 1024 * 1024
	_ws.outbound_buffer_size = 1 * 1024 * 1024
	if not _demo:
		var url := OS.get_environment("MAREE_WS_URL")
		if url.is_empty():
			url = "ws://127.0.0.1:8765"
		var err := _ws.connect_to_url(url)
		if err != OK:
			_status = "connexion impossible : %s" % url


func _view_mode() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--view="):
			return a.split("=")[1]
	for a in OS.get_cmdline_args():
		if a.begins_with("--view="):
			return a.split("=")[1]
	var env := OS.get_environment("MAREE_VIEW")
	if env != "":
		return env
	return "iso"


func _swap_to_top() -> void:
	get_tree().change_scene_to_file("res://scenes/top.tscn")


var _fps_t := 0.0
var _fps_n := 0
var _fps_on := false

func _process(_delta: float) -> void:
	if not _demo:
		_ws.poll()
		while _ws.get_available_packet_count() > 0:
			_handle(_ws.get_packet().get_string_from_utf8())
		match _ws.get_ready_state():
			WebSocketPeer.STATE_OPEN:
				if _status != "connecté" and _status != "terminé":
					_status = "connecté"
			WebSocketPeer.STATE_CLOSED:
				if _status != "terminé":
					_status = "déconnecté"
	if _fps_on:
		_fps_n += 1
		var now := Time.get_ticks_msec() / 1000.0
		if now - _fps_t >= 1.0:
			print("iso fps : %d" % int(round(_fps_n / (now - _fps_t))))
			_fps_n = 0
			_fps_t = now
	queue_redraw()


func _handle(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var message: Dictionary = parsed
	match str(message.get("type", "")):
		"hello":
			_plan = message.get("plan", {})
			_live = bool(message.get("live", false))
			_apply_live_state()
		"snapshot":
			_snap = message
		"indicators":
			_ind = message
		"trace":
			_trace = message
		"world":
			_handle_world(message)
		"injection":
			_note("injecté : %s" % str(message.get("kind", "?")))
		"ack":
			_note("✔ %s en file" % str(message.get("kind", "?")))
		"error":
			_note("✖ %s" % str(message.get("reason", "erreur")))
		"incident":
			_note("incident %s : %s" % [
				str(message.get("agent_id", "?")),
				str(message.get("cause", "?")),
			])
		"narrative":
			_narratives.append("t%s — %s" % [message.get("tick"), message.get("text")])
			if _narratives.size() > 3:
				_narratives.pop_front()
		"end":
			_status = "terminé"


func _handle_world(message: Dictionary) -> void:
	match str(message.get("kind", "")):
		"smoke":
			_world_smoke = {
				"position": message.get("position", []),
				"radius": float(message.get("radius", 0.0)),
				"tick": int(message.get("tick", 0)),
			}
			_note("fumée visible (t%s)" % message.get("tick"))
		"announcement":
			_announcement = str(message.get("text", ""))
			_announcement_at = Time.get_ticks_msec()
			_note("annonce diffusée")
		"exit_closed":
			_note("sortie %s fermée" % message.get("exit", "?"))


# ------------------------------------------------------------------
# Chargement du monde et des sprites
# ------------------------------------------------------------------
func _load_world() -> void:
	var text := FileAccess.get_file_as_string("res://assets/world/mall_aubel.json")
	if text.is_empty():
		push_warning("iso : monde mall_aubel.json introuvable")
		return
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) == TYPE_DICTIONARY:
		_world = parsed


func _load_sprites() -> void:
	for name in [
		"painted_wooden_bench_1k", "planter_box_02_1k", "metal_trash_can_1k",
		"wooden_display_shelves_01_1k", "modern_ceiling_lamp_01_1k",
		"stairs-open", "platform-ramp", "sign",
	]:
		var path := "res://assets/sprites_iso/%s.png" % name
		if ResourceLoader.exists(path):
			_sprites[name] = load(path)


func _populate_demo() -> void:
	# Population déterministe : chaque espace reçoit des agents à des points
	# fixes (grille + test d'appartenance), avec une croyance = la sortie la
	# plus proche. Ce n'est PAS une simulation : c'est une illustration du
	# rendu, documentée comme telle dans docs/visuel/ISO.md.
	var agents: Array = []
	var uid := 0
	for lv in _levels():
		var exits: Array = lv.get("exits", [])
		for space in lv.get("spaces", []):
			var poly: Array = space.get("polygon", [])
			var pts := _sample_polygon(poly, 15)
			for pt in pts:
				uid += 1
				var belief := _nearest_exit(pt, exits)
				if uid % 5 == 0:
					belief = ""
				agents.append({
					"id": "A%02d" % uid,
					"profile": "visiteur",
					"label": "Visiteur",
					"kind": "demo",
					"pos": [pt.x, pt.y],
					"level": lv.get("id", "L0"),
					"belief": belief,
					"confidence": 0.6,
					"evacuated": false,
					"intention": "go_exit" if belief != "" else "search",
					"intention_target": belief,
					"perceived": [],
					"memory": [],
					"last_decision": null,
				})
	# Un peu de mobilier réel (sprites) dans le hall du rez-de-chaussée.
	_decor = [
		{"sprite": "painted_wooden_bench_1k", "pos": Vector2(8, 16), "level": "L0", "scale": 1.6},
		{"sprite": "planter_box_02_1k", "pos": Vector2(27, 16), "level": "L0", "scale": 1.4},
		{"sprite": "wooden_display_shelves_01_1k", "pos": Vector2(33, 16), "level": "L0", "scale": 1.8},
		{"sprite": "metal_trash_can_1k", "pos": Vector2(15, 8), "level": "L0", "scale": 1.0},
	]
	var smoke := {}
	if _demo_smoke:
		smoke = {"position": [23.0, 7.0], "radius": 8.0, "tick": 10}
	_snap = {
		"tick": 12,
		"sim_time": "2:00",
		"agents": agents,
		"exits_open": _all_exit_ids(),
		"smoke_active": _demo_smoke,
		"smoke": smoke,
		# deux goulots illustratifs (près de la sortie A et du kiosque) pour
		# montrer la couche de densité ; en run réel, la grille vient du moteur.
		"density_grid": [
			{"x": 15.0, "y": 2.0, "n": 3},
			{"x": 23.0, "y": 7.0, "n": 2},
		],
	}
	_status = "démo (rendu)"


func _sample_polygon(poly: Array, per_space: int) -> Array:
	# Grille déterministe de points à l'intérieur du polygone.
	var xs: Array = []
	var ys: Array = []
	for p in poly:
		xs.append(float(p[0]))
		ys.append(float(p[1]))
	var minx: float = xs.min()
	var maxx: float = xs.max()
	var miny: float = ys.min()
	var maxy: float = ys.max()
	var out: Array = []
	var step := 2.4
	var y := miny + step * 0.5
	while y < maxy and out.size() < per_space:
		var x := minx + step * 0.5
		while x < maxx and out.size() < per_space:
			var pt := Vector2(x, y)
			if _point_in_poly(pt, poly):
				out.append(pt)
			x += step
		y += step
	return out


func _nearest_exit(pt: Vector2, exits: Array) -> String:
	var best := ""
	var best_d := 1e20
	for e in exits:
		var seg: Array = e.get("segment", [])
		if seg.size() < 2:
			continue
		var mid := Vector2(
			(float(seg[0][0]) + float(seg[1][0])) * 0.5,
			(float(seg[0][1]) + float(seg[1][1])) * 0.5
		)
		var d := pt.distance_to(mid)
		if d < best_d:
			best_d = d
			best = str(e.get("id", ""))
	return best


func _point_in_poly(pt: Vector2, poly: Array) -> bool:
	var inside := false
	var n := poly.size()
	var j := n - 1
	for i in range(n):
		var xi := float(poly[i][0])
		var yi := float(poly[i][1])
		var xj := float(poly[j][0])
		var yj := float(poly[j][1])
		if ((yi > pt.y) != (yj > pt.y)) and \
				(pt.x < (xj - xi) * (pt.y - yi) / (yj - yi + 1e-12) + xi):
			inside = not inside
		j = i
	return inside


func _levels() -> Array:
	return _world.get("levels", [])


func _level_by_id(id: String) -> Dictionary:
	for lv in _levels():
		if str(lv.get("id", "")) == id:
			return lv
	return {}


func _all_exit_ids() -> Array:
	var out: Array = []
	for lv in _levels():
		for e in lv.get("exits", []):
			out.append(str(e.get("id", "")))
	return out


func _elev_of(level_id: String) -> float:
	var lv := _level_by_id(level_id)
	return float(lv.get("elevation", 0.0))


# ------------------------------------------------------------------
# Projection isométrique
# ------------------------------------------------------------------
func _iso(x: float, y: float, level_id: String) -> Vector2:
	var sx := x - y
	var sy := (x + y) * 0.5 - _elev_of(level_id) * ELEV_K
	return Vector2(sx * _k, sy * _k) + _off


func _uniso(screen: Vector2, level_id: String) -> Vector2:
	var sx := (screen.x - _off.x) / _k
	var sy := (screen.y - _off.y) / _k + _elev_of(level_id) * ELEV_K
	# x - y = sx ; x + y = 2·sy
	var x := (sx + 2.0 * sy) * 0.5
	var y := (2.0 * sy - sx) * 0.5
	return Vector2(x, y)


func _visible_levels() -> Array:
	var all := _levels()
	if _level_mode == "cut":
		return all
	for lv in all:
		if str(lv.get("id", "")) == _level_mode:
			return [lv]
	return all


func _fit(view: Vector2) -> void:
	var avail_w: float = maxf(view.x - PANEL_W - 2.0 * MARGIN, 120.0)
	var avail_h: float = maxf(view.y - HUD_H - BOTTOM_H, 120.0)
	var minx := 1e20
	var maxx := -1e20
	var miny := 1e20
	var maxy := -1e20
	for lv in _visible_levels():
		var elev := float(lv.get("elevation", 0.0)) * ELEV_K
		for p in lv.get("outline", []):
			var sx := float(p[0]) - float(p[1])
			var sy := (float(p[0]) + float(p[1])) * 0.5 - elev
			minx = minf(minx, sx)
			maxx = maxf(maxx, sx)
			miny = minf(miny, sy)
			maxy = maxf(maxy, sy)
	if maxx - minx < 0.001:
		maxx = minx + 1.0
	if maxy - miny < 0.001:
		maxy = miny + 1.0
	_k = minf(avail_w / (maxx - minx), avail_h / (maxy - miny))
	_off = Vector2(
		MARGIN + (avail_w - (maxx - minx) * _k) * 0.5 - minx * _k,
		HUD_H + (avail_h - (maxy - miny) * _k) * 0.5 - miny * _k
	)


# ------------------------------------------------------------------
# Dessin
# ------------------------------------------------------------------
func _draw() -> void:
	var view := _viewport()
	draw_rect(Rect2(Vector2.ZERO, view), Color(0.05, 0.06, 0.08))
	if _world.is_empty():
		_text(Vector2(MARGIN, 40), "Monde introuvable (mall_aubel.json) — %s" % _status, 16)
		_draw_hud(view)
		return
	_fit(view)
	for lv in _visible_levels():
		_draw_floor(lv)
	_draw_ground_overlay()
	_draw_objects()
	_draw_announcement(view)
	_draw_hud(view)
	_draw_trace(view)
	_draw_inspector(view)


func _draw_floor(lv: Dictionary) -> void:
	var level_id := str(lv.get("id", "L0"))
	var holes: Array = lv.get("holes", [])
	for space in lv.get("spaces", []):
		var poly: Array = space.get("polygon", [])
		_draw_tiles(poly, holes, level_id)
	# contour du niveau (murs de façade) en trait fin
	var outline := PackedVector2Array()
	for p in lv.get("outline", []):
		outline.append(_iso(float(p[0]), float(p[1]), level_id))
	if outline.size() >= 3:
		draw_polyline(outline, Color(0.20, 0.22, 0.26, 0.9), 1.5)


func _draw_tiles(poly: Array, holes: Array, level_id: String) -> void:
	var xs: Array = []
	var ys: Array = []
	for p in poly:
		xs.append(float(p[0]))
		ys.append(float(p[1]))
	var minx: float = xs.min()
	var maxx: float = xs.max()
	var miny: float = ys.min()
	var maxy: float = ys.max()
	var step := 2.0
	var j := 0
	var y := miny
	while y < maxy:
		var i := 0
		var x := minx
		while x < maxx:
			var cx := x + step * 0.5
			var cy := y + step * 0.5
			if _point_in_poly(Vector2(cx, cy), poly) and not _in_holes(Vector2(cx, cy), holes):
				var shade := FLOOR_A if (i + j) % 2 == 0 else FLOOR_B
				var diamond := PackedVector2Array([
					_iso(x, y, level_id), _iso(x + step, y, level_id),
					_iso(x + step, y + step, level_id), _iso(x, y + step, level_id),
				])
				draw_colored_polygon(diamond, shade)
				i += 1
			x += step
		j += 1
		y += step


func _in_holes(pt: Vector2, holes: Array) -> bool:
	for h in holes:
		if _point_in_poly(pt, h):
			return true
	return false


func _draw_ground_overlay() -> void:
	# densité (goulots) : losanges rouges translucides
	for cell in _snap.get("density_grid", []):
		var n := int(cell.get("n", 0))
		if n < 2:
			continue
		var cx := float(cell["x"])
		var cy := float(cell["y"])
		var lvl := _level_for_point(Vector2(cx, cy))
		var d := PackedVector2Array([
			_iso(cx - 1, cy - 1, lvl), _iso(cx + 1, cy - 1, lvl),
			_iso(cx + 1, cy + 1, lvl), _iso(cx - 1, cy + 1, lvl),
		])
		draw_colored_polygon(d, Color(0.95, 0.25, 0.20, minf(0.10 * n, 0.42)))
	# fumée : nappe semi-transparente au-dessus du sol
	var smoke: Dictionary = _snap.get("smoke", {})
	if smoke.is_empty() or not bool(_snap.get("smoke_active", false)):
		smoke = _world_smoke
	if smoke.is_empty():
		return
	var pos = smoke.get("position", [])
	if typeof(pos) != TYPE_ARRAY or (pos as Array).size() < 2:
		return
	var radius_m := float(smoke.get("radius", 0.0))
	if radius_m <= 0.0:
		return
	var lvl := _level_for_point(Vector2(float(pos[0]), float(pos[1])))
	var centre := _iso(float(pos[0]), float(pos[1]), lvl)
	var r := radius_m * _k
	draw_circle(centre, r, Color(0.55, 0.57, 0.62, 0.30))
	draw_circle(centre, r * 0.55, Color(0.45, 0.47, 0.52, 0.22))
	for ring in [0.45, 0.72, 1.0]:
		draw_arc(centre, r * float(ring), 0.0, TAU, 48, Color(0.78, 0.80, 0.84, 0.30), 1.2)
	_text(centre + Vector2(-24, -4), "fumée", 12, Color(0.85, 0.87, 0.90))


func _level_for_point(pt: Vector2) -> String:
	# niveau du plus bas qui contient le point (sinon L0)
	var best := "L0"
	for lv in _levels():
		if not _level_visible(lv):
			continue
		var inside := false
		var spaces: Array = lv.get("spaces", [])
		if spaces.is_empty():
			inside = _point_in_poly(pt, lv.get("outline", []))
		else:
			for s in spaces:
				if _point_in_poly(pt, s.get("polygon", [])):
					inside = true
					break
		if inside:
			best = str(lv.get("id", "L0"))
	return best


func _level_visible(lv: Dictionary) -> bool:
	if _level_mode == "cut":
		return true
	return str(lv.get("id", "")) == _level_mode


func _draw_objects() -> void:
	# Liste des objets à trier par profondeur (x + y), du plus loin au plus
	# proche : c'est ce qui donne le recouvrement correct.
	var items: Array = []
	for lv in _visible_levels():
		var level_id := str(lv.get("id", "L0"))
		var dim := _level_dimmed(lv)
		for ob in lv.get("obstacles", []):
			var poly: Array = ob.get("polygon", [])
			var depth := _poly_depth(poly)
			items.append({"depth": depth, "kind": "obstacle", "ob": ob, "level": level_id, "dim": dim})
		for link in _world.get("vertical", []):
			if str(link.get("from", "")) == level_id or str(link.get("to", "")) == level_id:
				items.append({
					"depth": _poly_depth(link.get("polygon", [])) + 0.01,
					"kind": "link", "link": link, "level": level_id, "dim": dim,
				})
	for d in _decor:
		if _level_visible(_level_by_id(str(d.get("level", "L0")))):
			items.append({
				"depth": float(d["pos"].x) + float(d["pos"].y),
				"kind": "decor", "d": d, "dim": false,
			})
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var lvl := str(agent.get("level", "L0"))
		if not _level_visible(_level_by_id(lvl)):
			continue
		var p: Array = agent.get("pos", [0, 0])
		items.append({
			"depth": float(p[0]) + float(p[1]),
			"kind": "agent", "agent": agent, "level": lvl,
			"dim": _level_dimmed(_level_by_id(lvl)),
		})
	items.sort_custom(func(a, b): return float(a["depth"]) < float(b["depth"]))
	for it in items:
		match str(it["kind"]):
			"obstacle":
				_draw_prism(it["ob"].get("polygon", []), float(it["ob"].get("height", 1.0)), it["level"], it["dim"])
			"link":
				_draw_link(it["link"], it["dim"])
			"decor":
				_draw_decor(it["d"])
			"agent":
				_draw_agent(it["agent"], it["level"], it["dim"])


func _level_dimmed(lv: Dictionary) -> bool:
	# en mode niveau unique, l'autre niveau n'est pas dessiné ; en coupe, on
	# atténue le niveau non « actif » (le plus bas) pour la lisibilité.
	if _level_mode == "cut":
		return str(lv.get("id", "")) != "L0"
	return false


func _poly_depth(poly: Array) -> float:
	var s := 0.0
	for p in poly:
		s += float(p[0]) + float(p[1])
	return s / maxf(1.0, float(poly.size()))


func _draw_prism(poly: Array, height_m: float, level_id: String, dim: bool) -> void:
	if (poly as Array).size() < 3:
		return
	var alpha := 0.35 if dim else 1.0
	var base: Array = []
	var top: Array = []
	var hpx := height_m * _k * Z_K
	for p in poly:
		var b := _iso(float(p[0]), float(p[1]), level_id)
		base.append(b)
		top.append(b - Vector2(0, hpx))
	# faces latérales, triées par profondeur, puis le dessus
	var faces: Array = []
	var n := base.size()
	for i in range(n):
		var j := (i + 1) % n
		var quad := PackedVector2Array([base[i], base[j], top[j], top[i]])
		var dx: float = float(poly[j][0]) - float(poly[i][0])
		var dy: float = float(poly[j][1]) - float(poly[i][1])
		var shade := WALL_SIDE_L
		if dx > dy:
			shade = WALL_SIDE_R
		var depth: float = (base[i].y + base[j].y) * 0.5
		faces.append({"depth": depth, "quad": quad, "shade": shade})
	faces.sort_custom(func(a, b): return float(a["depth"]) < float(b["depth"]))
	for f in faces:
		draw_colored_polygon(f["quad"], Color(f["shade"], alpha))
	var top_poly := PackedVector2Array(top)
	draw_colored_polygon(top_poly, Color(WALL_TOP, alpha))
	draw_polyline(top_poly, Color(0.30, 0.30, 0.32, alpha), 1.0)


func _draw_link(link: Dictionary, dim: bool) -> void:
	var poly: Array = link.get("polygon", [])
	if (poly as Array).size() < 3:
		return
	var alpha := 0.35 if dim else 1.0
	var from := str(link.get("from", "L0"))
	var to := str(link.get("to", "L1"))
	var lower := from if _elev_of(from) <= _elev_of(to) else to
	var upper := to if lower == from else from
	# Deux dalles (bas et haut) reliées par les arêtes : pas de quadrilatère
	# auto-intersectant (la triangulation échouait sur un « nœud papillon »).
	var lower_poly := PackedVector2Array()
	var upper_poly := PackedVector2Array()
	for p in poly:
		lower_poly.append(_iso(float(p[0]), float(p[1]), lower))
		upper_poly.append(_iso(float(p[0]), float(p[1]), upper))
	draw_colored_polygon(lower_poly, Color(0.55, 0.58, 0.64, 0.55 * alpha))
	draw_colored_polygon(upper_poly, Color(0.62, 0.65, 0.71, 0.55 * alpha))
	var n := lower_poly.size()
	for i in range(n):
		var j := (i + 1) % n
		draw_line(lower_poly[i], upper_poly[i], Color(0.75, 0.78, 0.84, alpha), 1.2)
	# axe de l'escalator / de l'escalier
	draw_line(lower_poly[0], upper_poly[0], Color(0.85, 0.87, 0.90, alpha), 1.6)


func _draw_decor(d: Dictionary) -> void:
	var tex: Texture2D = _sprites.get(str(d.get("sprite", "")), null)
	if tex == null:
		return
	var pos: Vector2 = d["pos"]
	var lvl := str(d.get("level", "L0"))
	var centre := _iso(pos.x, pos.y, lvl)
	var s := float(d.get("scale", 1.5)) * _k
	var rect := Rect2(centre - Vector2(s * 0.5, s), Vector2(s, s))
	draw_texture_rect(tex, rect, false, Color(1, 1, 1, 0.95))


func _draw_agent(agent: Dictionary, level_id: String, dim: bool) -> void:
	var p: Array = agent.get("pos", [0, 0])
	var base := _iso(float(p[0]), float(p[1]), level_id)
	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
	var alpha := 0.30 if dim else 1.0
	var r: float = clampf(_k * 0.5, 3.5, 9.0)
	# ombre au sol (petit losange sombre)
	var shadow := PackedVector2Array([
		base + Vector2(-r, 0), base + Vector2(0, -r * 0.5),
		base + Vector2(r, 0), base + Vector2(0, r * 0.5),
	])
	draw_colored_polygon(shadow, Color(0, 0, 0, 0.28 * alpha))
	# corps : une « silhouette » isométrique (bille + corps) teintée par la
	# croyance — le sujet du projet reste visible.
	var body_top := base - Vector2(0, r * 2.2)
	draw_line(base, body_top, Color(colour, alpha), r * 1.4)
	draw_circle(body_top, r * 0.9, Color(colour, alpha))
	# liseré « croit une sortie fermée »
	if belief != "" and not _is_open(belief):
		draw_arc(body_top, r * 1.4, 0.0, TAU, 16, Color(WARN, alpha), 1.4)
	if str(agent["id"]) == _selected:
		draw_arc(body_top, r * 1.9, 0.0, TAU, 20, Color(Color.WHITE, alpha), 1.8)


# ------------------------------------------------------------------
# HUD, inspecteur, injection (repris du client v2, adapté à l'iso)
# ------------------------------------------------------------------
func _draw_hud(view: Vector2) -> void:
	var tick := int(_snap.get("tick", 0))
	var sim_time := str(_snap.get("sim_time", "0:00"))
	var agents: Array = _snap.get("agents", [])
	var remaining := 0
	for agent in agents:
		if not bool(agent.get("evacuated", false)):
			remaining += 1
	var evacuated := agents.size() - remaining
	_text(Vector2(MARGIN, 26), "MARÉE — Port-Aubel · vue isométrique", 18, INK)
	_text(
		Vector2(MARGIN, 48),
		"t%s   %s   évacués %d/%d   niveau %s" % [
			tick, sim_time, evacuated, agents.size(), _level_mode,
		],
		13,
		DIM,
	)
	_ind_boxes.clear()
	var ix := MARGIN
	var iy := 68.0
	for item in [
		["I1_consensus", "I1", "%.2f"], ["I2_entropy", "I2", "%.2f"],
		["I3_evacuated", "I3", "%.2f"], ["I5_max_density", "I5", "%.1f/m²"],
		["I6_belief_gap", "I6", "%.2f"], ["I7_delay_seconds", "I7", "%.0f s"],
	]:
		var text := "%s %s" % [item[1], item[2] % float(_ind.get(item[0], 0.0))]
		var w := _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x
		var box := Rect2(ix - 3.0, iy - 12.0, w + 8.0, 16.0)
		if str(_trace.get("indicator", "")) == str(item[0]):
			draw_rect(box, Color(0.20, 0.24, 0.30))
		_text(Vector2(ix, iy), text, 11, DIM)
		_ind_boxes.append({"rect": box, "key": str(item[0])})
		ix += w + 18.0
	_text(
		Vector2(view.x - PANEL_W - 250, 26),
		_status if _live else "%s (rejeu)" % _status,
		13,
		DIM if _live else WARN,
	)
	var note_y := 46.0
	for note in _notes:
		var colour := WARN if note.begins_with("✖") else DIM
		_text(Vector2(view.x - PANEL_W - 250, note_y), note, 11, colour)
		note_y += 15.0
	_para(
		Vector2(MARGIN, 78),
		"silhouette = sortie crue (A bleu, B vert, C orange, D/E violet/cyan, gris = aucune) · anneau orange = croit une sortie fermée · losanges rouges = goulots · touches 1/2/3 = niveau · cliquer un indicateur = sa chaîne",
		view.x - PANEL_W - 2.0 * MARGIN,
		9,
		Color(0.45, 0.48, 0.52),
	)
	var y := view.y - 16.0 - float(maxf(_narratives.size() - 1, 0)) * 18.0
	for line in _narratives:
		_text(Vector2(MARGIN, y), line, 13, Color(0.72, 0.76, 0.80))
		y += 18.0


func _draw_inspector(view: Vector2) -> void:
	var x := view.x - PANEL_W
	draw_rect(Rect2(Vector2(x, 0), Vector2(PANEL_W, view.y)), Color(0.08, 0.09, 0.11))
	draw_line(Vector2(x, 0), Vector2(x, view.y), Color(0.18, 0.20, 0.24), 1.0)
	var agent := _agent_by_id(_selected)
	if agent.is_empty():
		_text(Vector2(x + 16, 30), "Cliquez un agent", 14, DIM)
		_text(Vector2(x + 16, 52), "Sa mémoire, sa dernière", 12, DIM)
		_text(Vector2(x + 16, 68), "décision et la règle qu'il", 12, DIM)
		_text(Vector2(x + 16, 84), "a appliquée s'afficheront ici.", 12, DIM)
		return
	var width := PANEL_W - 32.0
	var y := 28.0
	var belief := str(agent.get("belief", ""))
	var colour: Color = BELIEF_COLORS.get(belief, UNKNOWN)
	_text(Vector2(x + 16, y), str(agent["id"]), 18, INK)
	y += 20.0
	_text(Vector2(x + 16, y), str(agent.get("label", agent.get("profile", "?"))), 12, DIM)
	y += 16.0
	_text(Vector2(x + 16, y), "niveau %s · profil %s" % [
		str(agent.get("level", "L0")), str(agent.get("profile", "?")),
	], 12, DIM)
	y += 20.0
	var target: Variant = agent.get("intention_target")
	var arrow := ""
	if target != null and str(target) != "":
		arrow = " → %s" % str(target)
	_text(Vector2(x + 16, y), "intention : %s%s" % [str(agent.get("intention", "—")), arrow], 12, INK)
	y += 18.0
	draw_circle(Vector2(x + 24, y - 4), 7.0, colour)
	_text(Vector2(x + 40, y), "croit en %s (%.0f %%)" % [
		belief if belief != "" else "rien", float(agent.get("confidence", 0.0)) * 100.0,
	], 12, INK)
	y += 18.0
	if belief != "" and not _is_open(belief):
		_text(Vector2(x + 16, y), "⚠ croit une sortie fermée", 12, WARN)
		y += 18.0
	var perceived: Array = agent.get("perceived", [])
	_text(Vector2(x + 16, y), "perçu : %s" % ("—" if perceived.is_empty() else _join(perceived)), 11, DIM)
	y += 18.0
	var decision: Variant = agent.get("last_decision")
	y = _section(x, y, "dernière décision")
	if typeof(decision) == TYPE_DICTIONARY and not decision.is_empty():
		var d: Dictionary = decision
		_text(Vector2(x + 16, y), "t%s · %s · déclencheur : %s" % [
			d.get("tick", "?"), d.get("kind", "?"), d.get("trigger", "—"),
		], 11, DIM)
		y += 16.0
		y = _para(Vector2(x + 16, y), "raison : %s" % str(d.get("reason", "—")), width, 12, INK)
	else:
		y = _para(Vector2(x + 16, y), "aucune décision encore prise", width, 12, DIM)


func _draw_announcement(view: Vector2) -> void:
	if _announcement.is_empty():
		return
	if Time.get_ticks_msec() - _announcement_at > BANNER_MS:
		return
	var width := view.x - PANEL_W - 2.0 * MARGIN
	var text := "📣  %s" % _announcement
	var height := _font.get_multiline_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, width - 16.0, 14).y + 12.0
	var x := MARGIN
	var y := view.y - BOTTOM_H + 4.0
	draw_rect(Rect2(Vector2(x, y), Vector2(width, height)), Color(0.10, 0.12, 0.15, 0.94))
	draw_rect(Rect2(Vector2(x, y), Vector2(width, height)), Color(0.35, 0.62, 0.95), false, 1.0)
	_para(Vector2(x + 8, y + 4), text, width - 16.0, 14, Color(0.82, 0.88, 0.96))


func _draw_trace(view: Vector2) -> void:
	if _trace.is_empty():
		return
	var width: float = minf(620.0, view.x - PANEL_W - 2.0 * MARGIN)
	var lines: Array[String] = []
	if not bool(_trace.get("found", false)):
		lines.append("%s : %s" % [str(_trace.get("indicator", "?")), str(_trace.get("reason", "aucune variation"))])
	else:
		lines.append("%s  %s → %s   (tick %s, delta %s)" % [
			str(_trace.get("indicator", "?")), str(_trace.get("from")), str(_trace.get("to")),
			str(_trace.get("tick")), str(_trace.get("delta")),
		])
		for step in _trace.get("events", []):
			lines.append("t%s #%s  %s" % [str(step.get("tick")), str(step.get("seq")), str(step.get("label"))])
			if lines.size() >= 12:
				break
	var height := 0.0
	for line in lines:
		height += _font.get_multiline_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, width, 11).y + 2.0
	var top: float = maxf(view.y - height - 34.0, HUD_H)
	draw_rect(Rect2(Vector2(MARGIN - 10.0, top - 6.0), Vector2(width + 20.0, height + 16.0)), Color(0.05, 0.06, 0.08, 0.92))
	var y := top + 6.0
	for line in lines:
		y = _para(Vector2(MARGIN, y), line, width, 11, DIM)


# ------------------------------------------------------------------
# Injection (D3) — identique au client v2
# ------------------------------------------------------------------
func _build_inject_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	_toggle = Button.new()
	_toggle.text = "Masquer l'injection ▴"
	_toggle.position = Vector2(MARGIN, HUD_H)
	_toggle.custom_minimum_size = Vector2(232, 26)
	_toggle.pressed.connect(_toggle_panel)
	layer.add_child(_toggle)
	_panel = PanelContainer.new()
	_panel.position = Vector2(MARGIN, HUD_H + 32.0)
	_panel.custom_minimum_size = Vector2(300, 0)
	_panel.modulate = Color(1, 1, 1, 0.94)
	layer.add_child(_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	_panel.add_child(box)
	var title := Label.new()
	title.text = "Injecter un événement"
	title.add_theme_font_size_override("font_size", 14)
	box.add_child(title)
	_announce_edit = LineEdit.new()
	_announce_edit.text = "Évacuation immédiate, sortie B"
	box.add_child(_announce_edit)
	var row := HBoxContainer.new()
	box.add_child(row)
	var announce := Button.new()
	announce.text = "Annoncer"
	announce.pressed.connect(_inject_announcement)
	row.add_child(announce)
	_buttons.append(announce)
	_exit_pick = OptionButton.new()
	for exit_id in ["A", "B", "C"]:
		_exit_pick.add_item(exit_id)
	row.add_child(_exit_pick)
	_buttons.append(_exit_pick)
	var close := Button.new()
	close.text = "Fermer"
	close.pressed.connect(_inject_exit_closed)
	row.add_child(close)
	_buttons.append(close)
	var smoke := Button.new()
	smoke.text = "Fumée ici"
	smoke.tooltip_text = "Cliquez d'abord sur le plan : la fumée naît à cet endroit"
	smoke.pressed.connect(_inject_smoke)
	box.add_child(smoke)
	_buttons.append(smoke)
	_hint = Label.new()
	_hint.text = "connexion…"
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint.custom_minimum_size = Vector2(284, 0)
	_hint.add_theme_font_size_override("font_size", 11)
	_hint.add_theme_color_override("font_color", DIM)
	box.add_child(_hint)


func _toggle_panel() -> void:
	_panel.visible = not _panel.visible
	_toggle.text = "Masquer l'injection ▴" if _panel.visible else "Injecter un événement ▾"


func _apply_live_state() -> void:
	for button in _buttons:
		button.disabled = not _live
	if _live:
		_hint.text = "cliquez le plan, puis « Fumée ici »"
		_hint.add_theme_color_override("font_color", DIM)
	else:
		_hint.text = "rejeu : injection désactivée (le serveur la refuserait)"
		_hint.add_theme_color_override("font_color", WARN)


func _send(command: Dictionary) -> void:
	if _ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		_note("✖ socket fermée : rien n'a été envoyé")
		return
	_ws.send_text(JSON.stringify(command))


func _inject_announcement() -> void:
	var text := _announce_edit.text.strip_edges()
	if text.is_empty():
		_note("✖ annonce vide : écrivez un texte")
		return
	_send({"type": "inject", "kind": "announcement", "text": text})


func _inject_exit_closed() -> void:
	var exit_id := _exit_pick.get_item_text(_exit_pick.selected)
	_send({"type": "inject", "kind": "exit_closed", "exit": exit_id})


func _inject_smoke() -> void:
	if _last_click_m.x < 0.0:
		_note("✖ cliquez d'abord sur le plan")
		return
	_send({"type": "inject", "kind": "smoke", "position": [_last_click_m.x, _last_click_m.y], "radius": 8.0})


func _note(text: String) -> void:
	_notes.append(text)
	while _notes.size() > 3:
		_notes.pop_front()
	if _hint != null:
		_hint.text = "\n".join(_notes)


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------
func _section(x: float, y: float, title: String) -> float:
	draw_line(Vector2(x + 16, y - 8), Vector2(x + PANEL_W - 16, y - 8), Color(0.20, 0.22, 0.26), 1.0)
	_text(Vector2(x + 16, y + 6), title, 12, Color(0.60, 0.72, 0.86))
	return y + 24.0


func _para(position: Vector2, text: String, width: float, font_size: int = 12, colour: Color = INK) -> float:
	var sized := _font.get_multiline_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, width, font_size)
	draw_multiline_string(_font, position + Vector2(0, font_size), text, HORIZONTAL_ALIGNMENT_LEFT, width, font_size, -1, colour)
	return position.y + sized.y + 4.0


func _join(items: Array) -> String:
	var out := PackedStringArray()
	for item in items:
		out.append(str(item))
	return ", ".join(out)


func _when(tick: int) -> String:
	if tick < 0:
		return "J-%d" % int(round(-float(tick) / 8640.0))
	return "t%d" % tick


func _viewport() -> Vector2:
	return get_viewport_rect().size


func _is_open(exit_id: String) -> bool:
	var open: Array = _snap.get("exits_open", [])
	if open.is_empty():
		return true
	return exit_id in open


func _request_trace(click: Vector2) -> bool:
	for box in _ind_boxes:
		var rect: Rect2 = box["rect"]
		if rect.has_point(click):
			_trace = {"indicator": box["key"], "found": false, "reason": "en attente du serveur…"}
			_send({"type": "trace", "indicator": box["key"]})
			return true
	return false


func _agent_by_id(agent_id: String) -> Dictionary:
	if agent_id.is_empty():
		return {}
	for agent in _snap.get("agents", []):
		if str(agent["id"]) == agent_id:
			return agent
	return {}


func _text(position: Vector2, text: String, font_size: int = 13, colour: Color = INK) -> void:
	draw_string(_font, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_1:
				_level_mode = "L0"
			KEY_2:
				_level_mode = "L1"
			KEY_3:
				_level_mode = "cut"
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_last_click_m = _click_to_world(event.position)
		_select_at(event.position)


func _click_to_world(click: Vector2) -> Vector2:
	# essaie chaque niveau visible ; le premier dont l'inverse tombe dans un
	# espace fait foi (sinon L0).
	for lv in _visible_levels():
		var w := _uniso(click, str(lv.get("id", "L0")))
		if _point_in_poly(w, lv.get("outline", [])):
			return w
	return _uniso(click, "L0")


func _select_at(click: Vector2) -> void:
	if _request_trace(click):
		return
	var best := ""
	var best_distance: float = maxf(10.0, _k * 1.2)
	for agent in _snap.get("agents", []):
		if bool(agent.get("evacuated", false)):
			continue
		var lvl := str(agent.get("level", "L0"))
		if not _level_visible(_level_by_id(lvl)):
			continue
		var p: Array = agent.get("pos", [0, 0])
		var d := _iso(float(p[0]), float(p[1]), lvl).distance_to(click)
		if d < best_distance:
			best_distance = d
			best = str(agent["id"])
	_selected = best