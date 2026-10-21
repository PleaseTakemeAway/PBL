"""Pure-Python DXF reader (ASCII DXF R12-R2018 subset) with ezdxf passthrough.

Reads every modelspace entity regardless of layer and returns flat RawEntity
records in drawing units. INSERT blocks are flattened with scale/rotation,
LWPOLYLINE bulges become arcs, DIMENSION blocks are exploded so their
geometry can be rendered but kept separate from part geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, degrees, hypot, pi, radians, sin, sqrt
from pathlib import Path
import re
from typing import Any

Point = tuple[float, float]


@dataclass
class RawEntity:
    kind: str                      # line, arc, circle, text, dimension, dimension_geom, other
    handle: str
    layer: str = "0"
    linetype: str = "BYLAYER"
    points: list[Point] = field(default_factory=list)   # line endpoints / polyline tessellation
    center: Point | None = None
    radius: float | None = None
    start_angle: float | None = None                    # degrees, CCW
    end_angle: float | None = None
    text: str | None = None
    height: float | None = None
    measurement: float | None = None                    # dimension value
    dim_type: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def bbox(self) -> tuple[float, float, float, float] | None:
        pts = list(self.points)
        if self.kind == "circle" and self.center:
            r = self.radius or 0
            pts += [(self.center[0]-r, self.center[1]-r), (self.center[0]+r, self.center[1]+r)]
        elif self.kind == "arc" and self.center:
            pts += arc_points(self.center, self.radius, self.start_angle, self.end_angle, 16)
        elif self.kind in {"text", "dimension"} and self.center:
            h = self.height or 1.0
            w = h*0.7*len(self.text or "")
            pts += [self.center, (self.center[0]+w, self.center[1]+h)]
        if not pts:
            return None
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


def arc_points(center: Point, radius: float, a1: float, a2: float, n: int) -> list[Point]:
    if a2 < a1:
        a2 += 360
    return [(center[0]+radius*cos(radians(a1+(a2-a1)*i/n)), center[1]+radius*sin(radians(a1+(a2-a1)*i/n))) for i in range(n+1)]


def bulge_to_arc(p1: Point, p2: Point, bulge: float) -> tuple[Point, float, float, float]:
    """Return (center, radius, start_angle, end_angle) for a polyline bulge segment."""
    theta = 4*atan2(bulge, 1)  # signed included angle
    chord = hypot(p2[0]-p1[0], p2[1]-p1[1])
    radius = chord/(2*sin(abs(theta)/2))
    mx, my = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2
    d = sqrt(max(radius*radius-(chord/2)**2, 0.0))
    nx, ny = -(p2[1]-p1[1])/chord, (p2[0]-p1[0])/chord
    sign = 1 if abs(theta) <= pi else -1
    if bulge > 0:
        cx, cy = mx-nx*d*sign, my-ny*d*sign
    else:
        cx, cy = mx+nx*d*sign, my+ny*d*sign
    a1 = degrees(atan2(p1[1]-cy, p1[0]-cx))
    a2 = degrees(atan2(p2[1]-cy, p2[0]-cx))
    if bulge < 0:
        a1, a2 = a2, a1
    return (cx, cy), radius, a1 % 360, a2 % 360


_MTEXT_CODES = re.compile(r"\\[A-Za-z][^;\\]*;|\\[A-Za-z~]|[{}]")


def clean_mtext(text: str) -> str:
    text = _MTEXT_CODES.sub("", text).replace("\\P", "\n")
    return text.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%p", "±").strip()


# ----------------------------------------------------------------------------- pure parser
class _Pairs:
    def __init__(self, text: str):
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.pairs = [(lines[i].strip(), lines[i+1]) for i in range(0, len(lines)-1, 2)]

    def section(self, name: str) -> list[tuple[str, str]]:
        start = None
        for i, (c, v) in enumerate(self.pairs):
            if c == "0" and v.strip() == "SECTION" and i+1 < len(self.pairs) and self.pairs[i+1][1].strip() == name:
                start = i+2
            elif start is not None and c == "0" and v.strip() == "ENDSEC":
                return self.pairs[start:i]
        return []


def _split(pairs: list[tuple[str, str]]) -> list[dict]:
    out, cur = [], None
    for c, v in pairs:
        if c == "0":
            if cur:
                out.append(cur)
            cur = {"type": v.strip(), "g": []}
        elif cur is not None:
            cur["g"].append((c, v))
    if cur:
        out.append(cur)
    return out


def _f(e, code, default=None):
    for c, v in e["g"]:
        if c == code:
            try:
                return float(v)
            except ValueError:
                return default
    return default


def _s(e, code, default=""):
    for c, v in e["g"]:
        if c == code:
            return v.strip()
    return default


def _all(e, code):
    return [v for c, v in e["g"] if c == code]


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class PureDxfReader:
    def __init__(self, path: Path):
        self.pairs = _Pairs(_read_text(path))
        self.header = self._header()
        self.layers = self._layers()
        self.blocks = self._blocks()

    def _header(self) -> dict:
        out, key = {}, None
        for c, v in self.pairs.section("HEADER"):
            if c == "9":
                key = v.strip()
            elif key and c in {"1", "70", "10", "20"}:
                out.setdefault(key, v.strip())
        return out

    def _layers(self) -> dict:
        out = {}
        for e in _split(self.pairs.section("TABLES")):
            if e["type"] == "LAYER":
                out[_s(e, "2")] = _s(e, "6", "CONTINUOUS")
        return out

    def _blocks(self) -> dict:
        blocks, cur = {}, None
        for e in _split(self.pairs.section("BLOCKS")):
            if e["type"] == "BLOCK":
                cur = _s(e, "2")
                blocks[cur] = {"base": (_f(e, "10", 0.0), _f(e, "20", 0.0)), "ents": []}
            elif e["type"] == "ENDBLK":
                cur = None
            elif cur:
                blocks[cur]["ents"].append(e)
        return blocks

    def entities(self) -> list[RawEntity]:
        out: list[RawEntity] = []
        for e in _split(self.pairs.section("ENTITIES")):
            if _s(e, "67", "0") == "1":      # paper space
                continue
            self._convert(e, out, (0.0, 0.0), 1.0, 0.0, None)
        return out

    def _convert(self, e, out, offset, scale, rot, parent_kind):
        cs, sn = cos(radians(rot)), sin(radians(rot))

        def tr(x, y):
            x, y = x*scale, y*scale
            return (offset[0]+x*cs-y*sn, offset[1]+x*sn+y*cs)

        t = e["type"]
        layer = _s(e, "8", "0")
        lt = _s(e, "6", "BYLAYER")
        if lt.upper() == "BYLAYER":
            lt = self.layers.get(layer, "CONTINUOUS")
        handle = _s(e, "5", f"auto{len(out)}")
        geom_kind = parent_kind or None
        base = dict(handle=handle, layer=layer, linetype=lt)
        if t == "LINE":
            out.append(RawEntity(geom_kind or "line", points=[tr(_f(e, "10"), _f(e, "20")), tr(_f(e, "11"), _f(e, "21"))], **base))
        elif t == "CIRCLE":
            out.append(RawEntity(geom_kind or "circle", center=tr(_f(e, "10"), _f(e, "20")), radius=_f(e, "40")*scale, **base))
        elif t == "ARC":
            out.append(RawEntity(geom_kind or "arc", center=tr(_f(e, "10"), _f(e, "20")), radius=_f(e, "40")*scale,
                                 start_angle=(_f(e, "50", 0)+rot) % 360, end_angle=(_f(e, "51", 360)+rot) % 360, **base))
        elif t == "ELLIPSE":
            cx, cy = _f(e, "10"), _f(e, "20")
            mx, my = _f(e, "11")*scale, _f(e, "21")*scale
            ratio = _f(e, "40", 1.0)
            a, ang = hypot(mx, my), atan2(my, mx)+radians(rot)
            s1, s2 = _f(e, "41", 0.0), _f(e, "42", 2*pi)
            if s2 < s1:
                s2 += 2*pi
            n = 32
            pts = []
            for i in range(n+1):
                u = s1+(s2-s1)*i/n
                px, py = a*cos(u), a*ratio*sin(u)
                c0 = tr(cx, cy)
                pts.append((c0[0]+px*cos(ang)-py*sin(ang), c0[1]+px*sin(ang)+py*cos(ang)))
            for i in range(n):
                out.append(RawEntity(geom_kind or "line", points=[pts[i], pts[i+1]], attributes={"source": "ellipse", "source_handle": handle}, **{**base, "handle": f"{handle}:{i}"}))
        elif t in {"LWPOLYLINE", "POLYLINE"}:
            pts, bul = [], []
            for c, v in e["g"]:
                if c == "10":
                    pts.append([float(v), 0.0]); bul.append(0.0)
                elif c == "20" and pts:
                    pts[-1][1] = float(v)
                elif c == "42" and pts:
                    bul[-1] = float(v)
            closed = int(float(_s(e, "70", "0"))) & 1
            n = len(pts)
            segs = range(n if closed else n-1)
            for i in segs:
                p1, p2, b = tuple(pts[i]), tuple(pts[(i+1) % n]), bul[i]
                sub = {**base, "handle": f"{handle}:{i}"}
                if abs(b) < 1e-9:
                    out.append(RawEntity(geom_kind or "line", points=[tr(*p1), tr(*p2)], attributes={"source": "polyline", "source_handle": handle}, **sub))
                else:
                    c, r, a1, a2 = bulge_to_arc(p1, p2, b)
                    out.append(RawEntity(geom_kind or "arc", center=tr(*c), radius=r*scale, start_angle=(a1+rot) % 360, end_angle=(a2+rot) % 360,
                                         attributes={"source": "polyline_bulge", "source_handle": handle}, **sub))
        elif t == "SPLINE":
            fit = [(float(v), 0.0) for c, v in e["g"] if c == "11"]
            ys = [float(v) for c, v in e["g"] if c == "21"]
            pts = [(fit[i][0], ys[i]) for i in range(min(len(fit), len(ys)))]
            if len(pts) < 2:
                cps = [(float(v), 0.0) for c, v in e["g"] if c == "10"]
                cys = [float(v) for c, v in e["g"] if c == "20"]
                pts = [(cps[i][0], cys[i]) for i in range(min(len(cps), len(cys)))]
            for i in range(len(pts)-1):
                out.append(RawEntity(geom_kind or "line", points=[tr(*pts[i]), tr(*pts[i+1])], attributes={"source": "spline_approx", "source_handle": handle}, **{**base, "handle": f"{handle}:{i}"}))
        elif t in {"TEXT", "MTEXT"}:
            raw = "".join(_all(e, "3"))+_s(e, "1")
            txt = clean_mtext(raw) if t == "MTEXT" else raw.replace("%%c", "Ø").replace("%%d", "°").replace("%%p", "±")
            h = _f(e, "40", 2.5)*scale
            out.append(RawEntity("text", center=tr(_f(e, "10", 0), _f(e, "20", 0)), text=txt, height=h,
                                 attributes={"rotation": (_f(e, "50", 0)+rot) % 360, "mtext": t == "MTEXT"}, **base))
        elif t == "DIMENSION":
            override = _s(e, "1")
            meas = _f(e, "42")
            txt_pos = tr(_f(e, "11", _f(e, "10", 0)), _f(e, "21", _f(e, "20", 0)))
            dt = int(float(_s(e, "70", "0"))) & 0x0F
            out.append(RawEntity("dimension", center=txt_pos, text=override if override and override != "<>" else None,
                                 measurement=meas*scale if meas is not None else None, dim_type=dt, height=2.5*scale,
                                 attributes={"def_point": tr(_f(e, "10", 0), _f(e, "20", 0)),
                                             "defpoint2": tr(_f(e, "13", 0), _f(e, "23", 0)),
                                             "defpoint3": tr(_f(e, "14", 0), _f(e, "24", 0)),
                                             "block": _s(e, "2")}, **base))
            blk = self.blocks.get(_s(e, "2"))
            if blk:
                for be in blk["ents"]:
                    self._convert(be, out, offset, scale, rot, "dimension_geom")
        elif t == "INSERT":
            name = _s(e, "2")
            blk = self.blocks.get(name)
            if not blk:
                return
            ix, iy = tr(_f(e, "10", 0), _f(e, "20", 0))
            sx = _f(e, "41", 1.0)*scale
            r2 = (_f(e, "50", 0)+rot) % 360
            bx, by = blk["base"]
            c2, s2 = cos(radians(r2)), sin(radians(r2))
            off = (ix-(bx*sx*c2-by*sx*s2), iy-(bx*sx*s2+by*sx*c2))
            for be in blk["ents"]:
                self._convert(be, out, off, sx, r2, parent_kind)
        elif t in {"SOLID", "HATCH", "POINT", "ATTDEF", "VIEWPORT", "LEADER", "MLEADER"}:
            out.append(RawEntity("other", attributes={"dxftype": t}, **base))
        else:
            out.append(RawEntity("other", attributes={"dxftype": t}, **base))

    def insunits(self) -> str | None:
        return {"1": "inch", "4": "mm", "5": "cm", "6": "m"}.get(self.header.get("$INSUNITS"))


# ----------------------------------------------------------------------------- ezdxf path
def _read_with_ezdxf(path: Path) -> tuple[list[RawEntity], str | None]:
    import ezdxf  # type: ignore
    doc = ezdxf.readfile(str(path))
    out: list[RawEntity] = []

    def emit(entity, parent_kind=None):
        t = entity.dxftype()
        layer = entity.dxf.layer
        lt = entity.dxf.get("linetype", "BYLAYER")
        if str(lt).upper() == "BYLAYER":
            lt = doc.layers.get(layer).dxf.linetype if layer in doc.layers else "CONTINUOUS"
        base = dict(handle=str(entity.dxf.handle), layer=layer, linetype=str(lt))
        k = parent_kind
        if t == "LINE":
            out.append(RawEntity(k or "line", points=[tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]], **base))
        elif t == "CIRCLE":
            out.append(RawEntity(k or "circle", center=tuple(entity.dxf.center)[:2], radius=float(entity.dxf.radius), **base))
        elif t == "ARC":
            out.append(RawEntity(k or "arc", center=tuple(entity.dxf.center)[:2], radius=float(entity.dxf.radius),
                                 start_angle=float(entity.dxf.start_angle) % 360, end_angle=float(entity.dxf.end_angle) % 360, **base))
        elif t in {"LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE", "INSERT"}:
            if t in {"ELLIPSE", "SPLINE"}:
                pts = [tuple(p)[:2] for p in entity.flattening(0.1)]
                for i in range(len(pts)-1):
                    out.append(RawEntity(k or "line", points=[pts[i], pts[i+1]], attributes={"source": t.lower(), "source_handle": base["handle"]}, **{**base, "handle": f"{base['handle']}:{i}"}))
                return
            for i, sub in enumerate(entity.virtual_entities()):
                emit(sub, k)
        elif t in {"TEXT", "MTEXT"}:
            txt = entity.plain_text() if t == "MTEXT" else entity.dxf.text
            height_attr = "char_height" if t == "MTEXT" else "height"
            height = float(entity.dxf.get(height_attr, 2.5))
            out.append(RawEntity("text", center=tuple(entity.dxf.insert)[:2], text=clean_mtext(txt), height=height,
                                 attributes={"rotation": float(entity.dxf.get("rotation", 0.0)), "mtext": t == "MTEXT"}, **base))
        elif t == "DIMENSION":
            try:
                # Group code 42 is the measurement stored by the authoring CAD.
                # Prefer it when present because get_measurement() recomputes from
                # model-space points and loses drawing-scale/display overrides.
                stored = entity.dxf.get("actual_measurement", None)
                meas = float(stored) if stored is not None else float(entity.get_measurement())
            except Exception:
                meas = None
            override = entity.dxf.get("text", "")
            attrs = {"def_point": tuple(entity.dxf.defpoint)[:2]}
            for name in ("defpoint2", "defpoint3"):
                point = entity.dxf.get(name, None)
                if point is not None:
                    attrs[name] = tuple(point)[:2]
            out.append(RawEntity("dimension", center=tuple(entity.dxf.get("text_midpoint", entity.dxf.defpoint))[:2],
                                 text=override if override and override != "<>" else None, measurement=meas,
                                 dim_type=int(entity.dimtype), height=2.5, attributes=attrs, **base))
            try:
                for sub in entity.virtual_entities():
                    emit(sub, "dimension_geom")
            except Exception:
                pass
        else:
            out.append(RawEntity("other", attributes={"dxftype": t}, **base))

    for ent in doc.modelspace():
        emit(ent)
    units = {1: "inch", 4: "mm", 5: "cm", 6: "m"}.get(doc.header.get("$INSUNITS", 0))
    return out, units


def read_dxf(path: str | Path) -> tuple[list[RawEntity], dict]:
    """Return (entities, info). info = {units, reader}."""
    path = Path(path)
    try:
        ents, units = _read_with_ezdxf(path)
        return ents, {"units": units, "reader": "ezdxf"}
    except ImportError:
        reader = PureDxfReader(path)
        return reader.entities(), {"units": reader.insunits(), "reader": "pure"}
