
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

TWIP = 20.0


def f(value, default=0.0):
    return default if value is None else float(value)


def i(value, default=0):
    return default if value is None else int(value)


def b(value) -> bool:
    return str(value).lower() == "true"


def child(el, typ):
    if el is None:
        return None
    for c in el:
        if c.attrib.get("type") == typ or c.tag == typ:
            return c
    return None


def rgba(el, default=(0, 0, 0, 1)):
    if el is None:
        return default
    return (
        i(el.attrib.get("red")) / 255,
        i(el.attrib.get("green")) / 255,
        i(el.attrib.get("blue")) / 255,
        i(el.attrib.get("alpha"), 255) / 255,
    )


@dataclass
class Matrix:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    def apply(self, x, y):
        return self.a * x + self.c * y + self.tx, self.b * x + self.d * y + self.ty

    def mul(self, inner: "Matrix") -> "Matrix":
        return Matrix(
            self.a * inner.a + self.c * inner.b,
            self.b * inner.a + self.d * inner.b,
            self.a * inner.c + self.c * inner.d,
            self.b * inner.c + self.d * inner.d,
            self.a * inner.tx + self.c * inner.ty + self.tx,
            self.b * inner.tx + self.d * inner.ty + self.ty,
        )


def parse_matrix(el) -> Matrix:
    if el is None:
        return Matrix()
    return Matrix(
        f(el.attrib.get("scaleX"), 1.0),
        f(el.attrib.get("rotateSkew0"), 0.0),
        f(el.attrib.get("rotateSkew1"), 0.0),
        f(el.attrib.get("scaleY"), 1.0),
        f(el.attrib.get("translateX"), 0.0),
        f(el.attrib.get("translateY"), 0.0),
    )


@dataclass
class Shape:
    commands: list[tuple]
    fill: tuple[float, float, float, float] | None = (0, 0, 0, 1)
    stroke: tuple[float, float, float, float] | None = None
    width: float = 0.5


@dataclass
class Font:
    fid: int
    glyphs: list[Shape]


@dataclass
class TextRecord:
    font_id: int
    text_height: float
    x: float
    y: float
    entries: list[tuple[int, float]]
    color: tuple[float, float, float, float]


@dataclass
class TextDef:
    cid: int
    matrix: Matrix
    records: list[TextRecord]
    bounds: tuple[float, float, float, float] | None = None


@dataclass
class Place:
    cid: int
    depth: int
    matrix: Matrix
    clip_depth: int | None = None

    @property
    def is_clip(self) -> bool:
        return self.clip_depth is not None


class XmlVectorRenderer:
    def __init__(self, page_w: float, page_h: float):
        self.page_w = page_w
        self.page_h = page_h

    def pdf_point(self, x_twip, y_twip):
        return x_twip / TWIP, self.page_h - y_twip / TWIP

    def build_path(self, c, shape: Shape, matrix: Matrix):
        if not shape.commands:
            return None
        path = c.beginPath()
        cur_pdf = (0.0, 0.0)
        started = False
        for cmd in shape.commands:
            if cmd[0] == "M":
                x, y = matrix.apply(cmd[1], cmd[2])
                px, py = self.pdf_point(x, y)
                path.moveTo(px, py)
                cur_pdf = (px, py)
                started = True
            elif cmd[0] == "L" and started:
                x, y = matrix.apply(cmd[1], cmd[2])
                px, py = self.pdf_point(x, y)
                path.lineTo(px, py)
                cur_pdf = (px, py)
            elif cmd[0] == "Q" and started:
                cx, cy, ax, ay = cmd[1], cmd[2], cmd[3], cmd[4]
                qx, qy = matrix.apply(cx, cy)
                ex, ey = matrix.apply(ax, ay)
                qx, qy = self.pdf_point(qx, qy)
                ex, ey = self.pdf_point(ex, ey)
                p0x, p0y = cur_pdf
                c1x = p0x + 2.0 / 3.0 * (qx - p0x)
                c1y = p0y + 2.0 / 3.0 * (qy - p0y)
                c2x = ex + 2.0 / 3.0 * (qx - ex)
                c2y = ey + 2.0 / 3.0 * (qy - ey)
                path.curveTo(c1x, c1y, c2x, c2y, ex, ey)
                cur_pdf = (ex, ey)
        return path

    def draw_shape(self, c, shape: Shape, matrix: Matrix, force_fill=None):
        path = self.build_path(c, shape, matrix)
        if path is None:
            return 0
        fill = force_fill if force_fill is not None else shape.fill
        stroke = shape.stroke
        if fill is None and stroke is None:
            return 0
        if fill is not None:
            c.setFillColor(Color(*fill[:3], alpha=fill[3]))
        if stroke is not None:
            c.setStrokeColor(Color(*stroke[:3], alpha=stroke[3]))
            c.setLineWidth(shape.width)
        c.drawPath(path, fill=1 if fill is not None else 0, stroke=1 if stroke is not None else 0)
        return 1

    def clip_shape(self, c, shape: Shape, matrix: Matrix):
        path = self.build_path(c, shape, matrix)
        if path is None:
            return 0
        c.clipPath(path, stroke=0, fill=0)
        return 1


def parse_shape_records(shape_records_el, default_fill=(0, 0, 0, 1), default_stroke=None, width=0.5) -> Shape:
    x = y = 0.0
    commands = []
    for rec in shape_records_el or []:
        typ = rec.attrib.get("type")
        if typ == "StyleChangeRecord":
            if b(rec.attrib.get("stateMoveTo")):
                x = f(rec.attrib.get("moveDeltaX"))
                y = f(rec.attrib.get("moveDeltaY"))
                commands.append(("M", x, y))
        elif typ == "StraightEdgeRecord":
            if b(rec.attrib.get("generalLineFlag")):
                x += f(rec.attrib.get("deltaX"))
                y += f(rec.attrib.get("deltaY"))
            elif b(rec.attrib.get("vertLineFlag")):
                y += f(rec.attrib.get("deltaY"))
            else:
                x += f(rec.attrib.get("deltaX"))
            commands.append(("L", x, y))
        elif typ == "CurvedEdgeRecord":
            cx = x + f(rec.attrib.get("controlDeltaX"))
            cy = y + f(rec.attrib.get("controlDeltaY"))
            x = cx + f(rec.attrib.get("anchorDeltaX"))
            y = cy + f(rec.attrib.get("anchorDeltaY"))
            commands.append(("Q", cx, cy, x, y))
    return Shape(commands, fill=default_fill, stroke=default_stroke, width=width)


def parse_font(el) -> Font:
    fid = i(el.attrib.get("fontID"))
    table = child(el, "glyphShapeTable")
    glyphs = []
    if table is not None:
        for item in table:
            if item.attrib.get("type") == "SHAPE":
                glyphs.append(parse_shape_records(child(item, "shapeRecords"), default_fill=(0, 0, 0, 1)))
    return Font(fid, glyphs)


def parse_text(el) -> TextDef:
    cid = i(el.attrib.get("characterID"))
    matrix = parse_matrix(child(el, "textMatrix"))
    bounds_el = child(el, "textBounds")
    bounds = None
    if bounds_el is not None:
        bounds = (
            f(bounds_el.attrib.get("Xmin")),
            f(bounds_el.attrib.get("Ymin")),
            f(bounds_el.attrib.get("Xmax")),
            f(bounds_el.attrib.get("Ymax")),
        )
    records = []
    current_font = 0
    current_height = 1.0
    current_x = 0.0
    current_y = 0.0
    current_color = (0, 0, 0, 1)
    trs = child(el, "textRecords")
    if trs is not None:
        for tr in trs:
            if tr.attrib.get("type") != "TEXTRECORD":
                continue
            if tr.attrib.get("fontId") is not None:
                current_font = i(tr.attrib.get("fontId"))
            if tr.attrib.get("textHeight") is not None:
                current_height = f(tr.attrib.get("textHeight"), current_height)
            if tr.attrib.get("xOffset") is not None:
                current_x = f(tr.attrib.get("xOffset"), current_x)
            if tr.attrib.get("yOffset") is not None:
                current_y = f(tr.attrib.get("yOffset"), current_y)
            color_el = child(tr, "textColorA")
            if color_el is not None:
                current_color = rgba(color_el, current_color)
            entries = []
            ge = child(tr, "glyphEntries")
            if ge is not None:
                for g in ge:
                    if g.attrib.get("type") == "GLYPHENTRY":
                        entries.append((i(g.attrib.get("glyphIndex")), f(g.attrib.get("glyphAdvance"))))
            records.append(TextRecord(current_font, current_height, current_x, current_y, entries, current_color))
    return TextDef(cid, matrix, records, bounds)


def parse_line_styles(el):
    styles = {1: ((0, 0, 0, 1), 0.5)}
    if el is None:
        return styles
    idx = 1
    for ls in el:
        width = max(f(ls.attrib.get("width"), 10.0) / TWIP, 0.25)
        color = None
        for c in ls:
            if c.attrib.get("type") in {"RGB", "RGBA"}:
                color = rgba(c, (0, 0, 0, 1))
                break
        styles[idx] = (color or (0, 0, 0, 1), width)
        idx += 1
    return styles


def parse_define_shape(el) -> Shape:
    shapes = child(el, "shapes")
    if shapes is None:
        shapes = child(el, "shapeWithStyle")
    if shapes is None:
        shapes = child(el, "shapeRecords")
    line_styles = parse_line_styles(child(shapes, "lineStyles") if shapes is not None else None)
    records = child(shapes, "shapeRecords") if shapes is not None and child(shapes, "shapeRecords") is not None else shapes
    if records is None:
        return Shape([])
    x = y = 0.0
    commands = []
    stroke = None
    width = 0.5
    saw_line_style = False
    for rec in records:
        typ = rec.attrib.get("type")
        if typ == "StyleChangeRecord":
            if b(rec.attrib.get("stateLineStyle")):
                line_idx = i(rec.attrib.get("lineStyle"), 0)
                if line_idx:
                    stroke, width = line_styles.get(line_idx, ((0, 0, 0, 1), 0.5))
                    saw_line_style = True
                else:
                    stroke = None
            if b(rec.attrib.get("stateMoveTo")):
                x = f(rec.attrib.get("moveDeltaX"))
                y = f(rec.attrib.get("moveDeltaY"))
                commands.append(("M", x, y))
        elif typ == "StraightEdgeRecord":
            if b(rec.attrib.get("generalLineFlag")):
                x += f(rec.attrib.get("deltaX"))
                y += f(rec.attrib.get("deltaY"))
            elif b(rec.attrib.get("vertLineFlag")):
                y += f(rec.attrib.get("deltaY"))
            else:
                x += f(rec.attrib.get("deltaX"))
            commands.append(("L", x, y))
        elif typ == "CurvedEdgeRecord":
            cx = x + f(rec.attrib.get("controlDeltaX"))
            cy = y + f(rec.attrib.get("controlDeltaY"))
            x = cx + f(rec.attrib.get("anchorDeltaX"))
            y = cy + f(rec.attrib.get("anchorDeltaY"))
            commands.append(("Q", cx, cy, x, y))
    return Shape(commands, fill=None, stroke=stroke if saw_line_style else None, width=width)


def parse_place(el) -> Place | None:
    cid = el.attrib.get("characterId") or el.attrib.get("characterID")
    if cid is None:
        return None
    return Place(
        i(cid),
        i(el.attrib.get("depth")),
        parse_matrix(child(el, "matrix")),
        i(el.attrib.get("clipDepth")) if el.attrib.get("clipDepth") is not None else None,
    )


def rebuild_pdf_page_from_swf_xml(xml_path: Path, out_pdf: Path, page_w: float, page_h: float) -> dict:
    root = ET.parse(xml_path).getroot()
    fonts: dict[int, Font] = {}
    defs = {}
    places = []
    sprite = None

    for el in root.iter():
        typ = el.attrib.get("type")
        if typ == "DefineFont2Tag":
            font = parse_font(el)
            fonts[font.fid] = font
        elif typ == "DefineSpriteTag" and sprite is None:
            sprite = el

    container = sprite if sprite is not None else root
    for el in container.iter():
        typ = el.attrib.get("type")
        if typ == "DefineText2Tag":
            td = parse_text(el)
            defs[td.cid] = td
        elif typ and typ.startswith("DefineShape"):
            sid = el.attrib.get("shapeId") or el.attrib.get("characterID")
            if sid is not None:
                defs[i(sid)] = parse_define_shape(el)
        elif typ and typ.startswith("PlaceObject"):
            pl = parse_place(el)
            if pl is not None:
                places.append(pl)

    places.sort(key=lambda p: p.depth)
    renderer = XmlVectorRenderer(page_w, page_h)
    c = canvas.Canvas(str(out_pdf), pagesize=(page_w, page_h), pageCompression=1)
    clip_places = [pl for pl in places if pl.is_clip]

    def shape_bbox(shape: Shape, matrix: Matrix):
        xs = []
        ys = []
        for cmd in shape.commands:
            points = []
            if cmd[0] in {"M", "L"}:
                points = [(cmd[1], cmd[2])]
            elif cmd[0] == "Q":
                points = [(cmd[1], cmd[2]), (cmd[3], cmd[4])]
            for x, y in points:
                px, py = matrix.apply(x, y)
                xs.append(px)
                ys.append(py)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def union_bbox(boxes):
        boxes = [box for box in boxes if box is not None]
        if not boxes:
            return None
        return min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)

    def text_bbox(text: TextDef, text_matrix: Matrix):
        boxes = []
        for rec in text.records:
            font = fonts.get(rec.font_id)
            if not font:
                continue
            cursor_x = rec.x
            scale = rec.text_height / 1024.0
            for glyph_index, adv in rec.entries:
                if glyph_index < len(font.glyphs):
                    glyph_matrix = text_matrix.mul(Matrix(scale, 0, 0, scale, cursor_x, rec.y))
                    boxes.append(shape_bbox(font.glyphs[glyph_index], glyph_matrix))
                cursor_x += adv
        return union_bbox(boxes)

    def align_text_matrix_to_bounds(text: TextDef, local_matrix: Matrix):
        if text.bounds is None:
            return local_matrix, False
        bbox = text_bbox(text, local_matrix)
        if bbox is None:
            return local_matrix, False
        bx = (bbox[0] + bbox[2]) / 2.0
        by = (bbox[1] + bbox[3]) / 2.0
        tx = (text.bounds[0] + text.bounds[2]) / 2.0
        ty = (text.bounds[1] + text.bounds[3]) / 2.0
        dx = tx - bx
        dy = ty - by
        if abs(dx) < 1.0 and abs(dy) < 1.0:
            return local_matrix, False
        return Matrix(1, 0, 0, 1, dx, dy).mul(local_matrix), True

    def apply_active_clips(depth: int) -> int:
        applied = 0
        for clip in clip_places:
            if clip.depth < depth <= (clip.clip_depth or clip.depth):
                clip_obj = defs.get(clip.cid)
                if isinstance(clip_obj, Shape):
                    applied += renderer.clip_shape(c, clip_obj, clip.matrix)
        return applied

    drawn_shapes = drawn_texts = drawn_glyphs = missing = skipped_clips = applied_clips = bounds_aligned_texts = 0
    for pl in places:
        obj = defs.get(pl.cid)
        if obj is None:
            missing += 1
            continue
        if pl.is_clip:
            skipped_clips += 1
            continue
        c.saveState()
        if isinstance(obj, Shape):
            applied_clips += apply_active_clips(pl.depth)
            drawn_shapes += renderer.draw_shape(c, obj, pl.matrix)
        elif isinstance(obj, TextDef):
            aligned_local_matrix, aligned = align_text_matrix_to_bounds(obj, obj.matrix)
            text_matrix = pl.matrix.mul(aligned_local_matrix)
            if aligned:
                bounds_aligned_texts += 1
            for rec in obj.records:
                font = fonts.get(rec.font_id)
                if not font:
                    missing += 1
                    continue
                cursor_x = rec.x
                scale = rec.text_height / 1024.0
                for glyph_index, adv in rec.entries:
                    if glyph_index < len(font.glyphs):
                        glyph_matrix = text_matrix.mul(Matrix(scale, 0, 0, scale, cursor_x, rec.y))
                        drawn_glyphs += renderer.draw_shape(c, font.glyphs[glyph_index], glyph_matrix, force_fill=rec.color)
                    else:
                        missing += 1
                    cursor_x += adv
                drawn_texts += 1
        c.restoreState()
    c.showPage()
    c.save()
    return {
        "xml": str(xml_path),
        "pdf": str(out_pdf),
        "fonts": len(fonts),
        "defs": len(defs),
        "places": len(places),
        "drawn_shapes": drawn_shapes,
        "drawn_text_records": drawn_texts,
        "drawn_glyphs": drawn_glyphs,
        "missing": missing,
        "skipped_clips": skipped_clips,
        "applied_clips": applied_clips,
        "bounds_aligned_texts": bounds_aligned_texts,
        "size": out_pdf.stat().st_size,
    }
