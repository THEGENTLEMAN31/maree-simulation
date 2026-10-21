extends RefCounted
## Palette et primitives de dessin partagées par l'interface Godot.
##
## Aucune logique de simulation ici : uniquement du style (décision 9).
## Le rendu reste volontairement « cercles colorés, pas de sprites » (cadrage),
## mais avec une hiérarchie visuelle lisible en soutenance et en projection.

const BG := Color("#0b0f17")
const PANEL := Color("#141a26")
const PANEL_2 := Color("#1b2333")
const BORDER := Color("#2a3547")
const TEXT := Color("#e8edf6")
const MUTED := Color("#93a2ba")
const FAINT := Color("#5f6c82")
const ACCENT := Color("#a78bfa")
const BELIEF_A := Color("#56b4e9")
const BELIEF_B := Color("#e69f00")
const BELIEF_C := Color("#009e73")
const UNKNOWN := Color("#8c97a8")
const DANGER := Color("#ef4444")
const OK := Color("#cbd5e1")
const SMOKE := Color("#b9c2cf")


static func font() -> Font:
	return ThemeDB.fallback_font


static func panel(
	ci: CanvasItem,
	rect: Rect2,
	fill: Color = PANEL,
	border: Color = BORDER,
	radius: int = 14,
	border_w: int = 1
) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = fill
	sb.border_color = border
	sb.set_border_width_all(border_w)
	sb.set_corner_radius_all(radius)
	ci.draw_style_box(sb, rect)


static func text(
	ci: CanvasItem,
	pos: Vector2,
	label: String,
	size: int = 14,
	color: Color = TEXT,
	align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT,
	width: float = -1.0
) -> void:
	ci.draw_string(font(), pos, label, align, width, size, color)


static func text_right(
	ci: CanvasItem, right_x: float, y: float, label: String,
	size: int = 14, color: Color = TEXT
) -> void:
	var w := font().get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	ci.draw_string(font(), Vector2(right_x - w, y), label, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)


static func text_width(label: String, size: int = 14) -> float:
	return font().get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x


static func chip(
	ci: CanvasItem,
	pos: Vector2,
	label: String,
	color: Color,
	size: int = 12
) -> float:
	var w := text_width(label, size) + 18.0
	var h := float(size) + 12.0
	panel(ci, Rect2(pos, Vector2(w, h)), Color(color, 0.13), Color(color, 0.5), 8)
	text(ci, pos + Vector2(9, h * 0.5 + size * 0.36), label, size, color)
	return w


static func dot(ci: CanvasItem, center: Vector2, radius: float, color: Color) -> void:
	ci.draw_circle(center, radius + 1.5, Color(0, 0, 0, 0.35))
	ci.draw_circle(center, radius, color)


static func belief_color(belief: Variant) -> Color:
	match str(belief):
		"A":
			return BELIEF_A
		"B":
			return BELIEF_B
		"C":
			return BELIEF_C
		_:
			return UNKNOWN


static func belief_label(belief: Variant) -> String:
	match str(belief):
		"A", "B", "C":
			return "sortie %s" % str(belief)
		_:
			return "aucune info"


static func hhmmss(tick_seconds: int) -> String:
	var t: int = max(0, tick_seconds)
	return "%02d:%02d" % [t / 60, t % 60]
