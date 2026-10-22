"""커팅플랜(CP) DXF 에서 판재·부품·조각을 읽는다. 테스트셋 정답을 만들 때 쓴다.

두 형식을 읽는다. 도면에 판재 라벨이 있으면 배치도, 없으면 전개도 모음으로 본다.

  배치도 (S-2120): 판재마다 "<재질> t<두께> x <폭> x <길이> <수량> sh't" 라벨과 테두리 사각형이 있다.
      테두리 안에 놓인 부품마다 "<도면 번호> <아이템>" 과 그 아래 "<부품명>" 두 줄 글자가 있다.
  전개도 모음 (D-1203): 판재 없이 부품 전개도를 줄지어 그렸다. 줄 왼쪽에 "002-1-1" 같은 큰 아이템 번호가,
      전개도 안에 "D=..\\PN=..\\PM=..\\PT=..\\PS=..\\PQ=.." 속성 글자가 있다.
      아이템 번호의 앞 3자리가 설계 도면 번호(002 -> OTH-002), 나머지가 그 도면의 아이템이다.

조각(piece)은 닫힌 외곽선 하나다.
  - 혼자 닫힌 엔티티(CIRCLE, 닫힌 LWPOLYLINE 등)나, LINE·ARC·열린 폴리라인이 끝점으로 이어져 고리 하나를
    이룬 것. 끝점은 0.1 mm 단위로 반올림해 잇는다. 블록(INSERT)은 풀어서 쓴다 (S-2120 은 COVER PLATE,
    INSUL SUP'T CLIP 을 블록으로 놓았다). DIMENSION, 글자, HATCH 는 형상으로 쓰지 않는다.
  - 조각 안에 들어 있는 닫힌 외곽은 구멍으로 보고 면적(area)에서 빼고 holes 로 센다.

부품 라벨마다 조각을 아래 순서로 찾는다 (parts.csv 의 outline 열).
  label  라벨 위치를 감싸는 가장 작은 조각. 전개도 모음에서 그 조각이 다른 조각의 구멍이면 바깥 조각
  face   모든 선을 교차점에서 쪼개 만든 면 중 라벨을 감싸는 가장 작은 면. 부품끼리 선을 공유해 고리가
         안 생기는 경우다. 네 변이 판 테두리에 닿는 면(부품을 놓고 남은 자리)은 쓰지 않는다
  near   같은 판(또는 같은 줄)에서 아직 라벨이 없는 조각 중 라벨에서 글자 높이 5배 안에 있는 가장 가까운 것
  none   못 찾음
라벨이 없는 조각은 pieces.csv 의 link 열에 추정 근거를 적어 부품에 묶는다.
  copy   같은 판에 크기·면적이 같은 라벨 붙은 조각이 있다 (같은 부품을 여러 장 놓고 라벨은 한 번만 쓴 경우)
  row    전개도 모음에서 같은 줄의 부품이 하나뿐이다 (분할 조각, 라벨 없는 반복 조각)

한계: 면(face)은 부품 안쪽에 그은 선이 있으면 부품 일부만 잡는다. near·copy·row 는 추정이다.
결과는 사람이 PNG 로 확인한다.
"""

import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import ezdxf
from ezdxf import path as ezpath
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from cutplan_agent.eval.drawing_refs import parse_ref

SHEET_RE = re.compile(
    r"^\s*(?P<material>\S+(?:\s*\([^)]*\))?)\s+[tT]\s*(?P<t>\d+(?:\.\d+)?)"
    r"(?:\s*\((?P<clad>[^)]*)\))?\s*[xX×*]\s*(?P<w>\d+(?:\.\d+)?)\s*[xX×*]\s*"
    r"(?P<l>\d+(?:\.\d+)?)\s*L?\s+(?P<qty>\d+)\s*(?:SH'?T|EA|매)",
    re.IGNORECASE,
)
ITEM_ROW_RE = re.compile(r"^(?P<dwg>\d{3})(?:-(?P<item>\d+(?:-\d+)*))?$")
ATTR_KEYS = {"D": "dwg", "N": "name", "M": "material", "T": "thickness"}
ATTR_KEYS.update({"S": "size", "Q": "qty"})
GEOM_TYPES = {"LINE", "ARC", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ELLIPSE", "SPLINE"}
SNAP = 1  # 끝점 반올림 자릿수 (0.1 mm)
FLAT_DIST = 0.5  # 곡선을 점으로 펼 때 허용 오차 (mm)
NEAR_HEIGHTS = 5.0  # near: 라벨에서 글자 높이 몇 배까지 찾는가


@dataclass
class Piece:
    piece_id: int
    poly: Polygon  # 구멍을 빼지 않은 바깥 외곽
    kind: str  # circle | polyline | chain | face
    n_ents: int = 1
    net_area: float = 0.0  # 구멍을 뺀 면적
    n_holes: int = 0
    hole_ids: List[int] = field(default_factory=list)
    part_no: Optional[int] = None
    link: str = ""  # label | face | near | copy | row
    row: str = ""  # 전개도 모음에서 조각이 놓인 줄의 아이템 번호

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return self.poly.bounds

    @property
    def w(self) -> float:
        x0, _, x1, _ = self.poly.bounds
        return x1 - x0

    @property
    def h(self) -> float:
        _, y0, _, y1 = self.poly.bounds
        return y1 - y0

    @property
    def center(self) -> Tuple[float, float]:
        x0, y0, x1, y1 = self.poly.bounds
        return (x0 + x1) / 2, (y0 + y1) / 2


@dataclass
class Text:
    text: str
    x: float
    y: float
    height: float
    rotation: float  # 도
    kind: str  # TEXT | MTEXT


@dataclass
class Sheet:
    sheet_id: int
    material: str
    thickness: float
    clad: str
    sheet_w: float
    sheet_h: float
    sheet_qty: int
    label_text: str
    border: str = "none"  # found | none
    box: Optional[Tuple[float, float, float, float]] = None
    notes: List[str] = field(default_factory=list)

    def contains(self, x: float, y: float) -> bool:
        if self.box is None:
            return False
        x0, y0, x1, y1 = self.box
        return x0 <= x <= x1 and y0 <= y <= y1


@dataclass
class Part:
    part_no: int
    label_text: str
    tag: str = ""
    dwg_no: Optional[int] = None
    item: str = ""
    name: str = ""
    material: str = ""
    thickness: Optional[float] = None
    size: str = ""
    qty: Optional[int] = None
    sheet_id: Optional[int] = None
    row: str = ""  # 전개도 모음의 줄 아이템 번호 (예: 002-1-3)
    piece_id: Optional[int] = None
    outline: str = "none"  # label | face | near | none
    x: float = 0.0
    y: float = 0.0
    h_text: float = 0.0


@dataclass
class CutPlan:
    layout: str  # nesting | unfold_list
    sheets: List[Sheet]
    parts: List[Part]
    pieces: List[Piece]
    texts: List[Text]
    unused_texts: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- 형상
def _points(e) -> List[Tuple[float, float]]:
    try:
        p = ezpath.make_path(e)
    except (TypeError, ValueError):
        return []
    return [(v.x, v.y) for v in p.flattening(FLAT_DIST)]


def _is_closed(e, pts) -> bool:
    t = e.dxftype()
    if t == "CIRCLE":
        return True
    if t == "ELLIPSE":
        span = (e.dxf.end_param - e.dxf.start_param) % (2 * math.pi)
        return span < 1e-6 or abs(span - 2 * math.pi) < 1e-6
    if t in ("LWPOLYLINE", "POLYLINE") and e.is_closed:
        return True
    if t == "SPLINE" and e.closed:
        return True
    return len(pts) > 2 and math.dist(pts[0], pts[-1]) < 10 ** (-SNAP)


def _key(p: Tuple[float, float]) -> Tuple[float, float]:
    return (round(p[0], SNAP), round(p[1], SNAP))


def _chain_loop(segs: List[List[Tuple[float, float]]]) -> Optional[list]:
    """끝점이 모두 두 번씩 만나 고리 하나를 이루면 그 점 목록. 아니면 None."""
    ends = defaultdict(list)
    for i, s in enumerate(segs):
        ends[_key(s[0])].append(i)
        ends[_key(s[-1])].append(i)
    if any(len(v) != 2 for v in ends.values()):
        return None
    used = [False] * len(segs)
    loop = list(segs[0])
    used[0] = True
    cur, start = _key(segs[0][-1]), _key(segs[0][0])
    while cur != start:
        nxt = next((i for i in ends[cur] if not used[i]), None)
        if nxt is None:
            return None
        s = segs[nxt] if _key(segs[nxt][0]) == cur else segs[nxt][::-1]
        loop.extend(s[1:])
        used[nxt] = True
        cur = _key(s[-1])
    return loop if all(used) else None


def _polygon(pts) -> Optional[Polygon]:
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0 or poly.geom_type != "Polygon":
        return None
    return poly


def _geom_entities(entities, depth=0):
    """형상 엔티티. 블록(INSERT)은 풀어서 놓인 위치·회전대로 돌려준다."""
    for e in entities:
        t = e.dxftype()
        if t in GEOM_TYPES:
            yield e
        elif t == "INSERT" and depth < 4:
            try:
                yield from _geom_entities(e.virtual_entities(), depth + 1)
            except (ezdxf.DXFError, ValueError, ZeroDivisionError):
                continue


def read_geometry(msp) -> Tuple[List[Piece], List[LineString]]:
    """닫힌 외곽 조각과, 면(face)을 만들 때 쓸 모든 선."""
    closed, open_segs, lines = [], [], []
    for e in _geom_entities(msp):
        pts = _points(e)
        if len(pts) < 2:
            continue
        lines.append(LineString(pts))
        (closed if _is_closed(e, pts) else open_segs).append((e, pts))
    pieces: List[Piece] = []

    def add(pts, kind, n):
        poly = _polygon(pts)
        if poly is not None:
            pieces.append(Piece(len(pieces) + 1, poly, kind, n))

    for e, pts in closed:
        add(pts, "circle" if e.dxftype() == "CIRCLE" else "polyline", 1)

    parent = list(range(len(open_segs)))  # 열린 선은 끝점으로 묶는다 (union-find)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_at: Dict[Tuple[float, float], int] = {}
    for i, (_, pts) in enumerate(open_segs):
        for k in (_key(pts[0]), _key(pts[-1])):
            if k in first_at:
                parent[find(i)] = find(first_at[k])
            else:
                first_at[k] = i
    groups = defaultdict(list)
    for i in range(len(open_segs)):
        groups[find(i)].append(open_segs[i][1])
    for segs in groups.values():
        loop = _chain_loop(segs)
        if loop is not None:  # 고리가 아닌 선 (치수 보조선, 중심선 등) 은 조각이 아니다
            add(loop, "chain", len(segs))
    return pieces, lines


def faces(lines: List[LineString]) -> List[Polygon]:
    """모든 선을 교차점에서 쪼갠 뒤 생기는 면."""
    if not lines:
        return []
    return [p for p in polygonize(unary_union(lines)) if p.area > 0]


def settle_holes(pieces: List[Piece]) -> Dict[int, int]:
    """조각 안에 바로 들어 있는 닫힌 외곽을 구멍으로 보고 net_area, n_holes 를 채운다.
    반환: 구멍 조각 id -> 그 구멍을 가진 조각 id."""
    by_area = sorted(pieces, key=lambda p: p.poly.area)
    parent_of: Dict[int, int] = {}
    for i, p in enumerate(by_area):
        inner = [q for q in by_area[:i] if p.poly.contains(q.poly)]
        top = [
            q
            for q in inner
            if not any(r.poly.contains(q.poly) for r in inner if r is not q)
        ]
        p.n_holes = len(top)
        p.hole_ids = [q.piece_id for q in top]
        p.net_area = p.poly.area - sum(q.poly.area for q in top)
        for q in top:
            parent_of[q.piece_id] = p.piece_id
    return parent_of


# ----------------------------------------------------------------------------- 글자
def read_texts(msp) -> List[Text]:
    out = []
    for e in msp.query("TEXT MTEXT"):
        if e.dxftype() == "TEXT":
            s, h = e.dxf.text, e.dxf.height
            p = e.dxf.align_point if e.dxf.halign or e.dxf.valign else e.dxf.insert
        else:
            s, h, p = e.plain_text(split=False), e.dxf.char_height, e.dxf.insert
        s = s.replace("%%C", "Ø").replace("%%c", "Ø").strip()
        if s:
            out.append(Text(s, p.x, p.y, h, e.dxf.get("rotation", 0.0), e.dxftype()))
    return out


def parse_attrs(text: str) -> Dict[str, str]:
    """'D=..\\nN=BASE\\nPL\\nM=..' -> {dwg, name, material, thickness, size, qty}. 줄바꿈된 값은 잇는다."""
    out: Dict[str, str] = {}
    cur = None
    for line in text.replace("\\P", "\n").splitlines():
        m = re.match(r"^\s*([A-Z])=(.*)$", line)
        if m and m.group(1) in ATTR_KEYS:
            cur = ATTR_KEYS[m.group(1)]
            out[cur] = m.group(2).strip()
        elif cur:
            sep = "" if cur == "size" else " "
            out[cur] = (out[cur] + sep + line.strip()).strip()
    if "size" in out:
        out["size"] = re.sub(r"\s+", "", out["size"])
    return out


def _local(t: Text, x: float, y: float) -> Tuple[float, float]:
    """글자 t 의 방향 기준으로 (x, y) 의 상대 좌표."""
    a = math.radians(-t.rotation)
    dx, dy = x - t.x, y - t.y
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def _num(s: str) -> Optional[float]:
    m = re.search(r"\d+(?:\.\d+)?", s or "")
    return float(m.group()) if m else None


def _name_below(ref: Text, texts: List[Text], used) -> Optional[Text]:
    best, best_d = None, math.inf
    for t in texts:
        if id(t) in used or t is ref or parse_ref(t.text):
            continue
        if not (0.6 * ref.height <= t.height <= 1.6 * ref.height):
            continue
        dx, dy = _local(ref, t.x, t.y)
        if -3.0 * ref.height < dy < -0.3 * ref.height and abs(dx) < 3.0 * ref.height:
            d = math.hypot(dx, dy)
            if d < best_d:
                best, best_d = t, d
    return best


def _item_key(item: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", item or ""))


# ----------------------------------------------------------------------------- 조각 배정
def _assign(
    parts: List[Part],
    pieces: List[Piece],
    lines: List[LineString],
    ok: Callable[[Piece], bool],
    region: Callable[[float, float], object],
    hole_to_outer: bool,
) -> None:
    """부품 라벨마다 조각을 찾는다 (label -> face -> near). pieces 에 face 조각이 추가될 수 있다."""
    cand = [p for p in pieces if ok(p)]
    parent_of = settle_holes(pieces) if hole_to_outer else {}
    by_id = {p.piece_id: p for p in pieces}
    taken = set()

    def take(part: Part, pc: Piece, how: str):
        part.piece_id, part.outline = pc.piece_id, how
        if pc.part_no is None:
            pc.part_no, pc.link = part.part_no, how
        taken.add(pc.piece_id)

    for part in parts:  # label
        pt = Point(part.x, part.y)
        hit = [p for p in cand if p.poly.covers(pt)]
        if hit:
            pc = min(hit, key=lambda p: p.poly.area)
            while hole_to_outer and pc.piece_id in parent_of:
                pc = by_id[parent_of[pc.piece_id]]
            take(part, pc, "label")
    face_list = None
    for part in parts:  # face
        if part.piece_id is not None:
            continue
        if face_list is None:
            face_list = faces(lines)
        pt = Point(part.x, part.y)
        hit = [f for f in face_list if f.covers(pt)]
        if not hit:
            continue
        outer = Polygon(min(hit, key=lambda f: f.area).exterior)
        pc = next(
            (p for p in pieces if p.kind == "face" and p.poly.equals(outer)), None
        )
        if pc is None:
            pc = Piece(max(p.piece_id for p in pieces) + 1, outer, "face", 0)
            if not ok(pc):
                continue
            pieces.append(pc)
            cand.append(pc)
            by_id[pc.piece_id] = pc
        take(part, pc, "face")
    for part in parts:  # near
        if part.piece_id is not None:
            continue
        pt, reg = Point(part.x, part.y), region(part.x, part.y)
        free = [
            p
            for p in cand
            if p.piece_id not in taken and reg is not None and region(*p.center) is reg
        ]
        free = [p for p in free if p.poly.distance(pt) <= NEAR_HEIGHTS * part.h_text]
        if free:
            take(part, min(free, key=lambda p: p.poly.distance(pt)), "near")


def _same_shape(a: Piece, b: Piece) -> bool:
    return (
        abs(a.w - b.w) < 0.5
        and abs(a.h - b.h) < 0.5
        and abs(a.poly.area - b.poly.area) <= 0.005 * max(a.poly.area, 1.0)
    )


# ----------------------------------------------------------------------------- 읽기
def read_cp(dxf_path: str, tag: str = "") -> CutPlan:
    """CP DXF 를 읽는다. tag 는 전개도 모음에서 아이템 번호 앞에 붙일 설비 태그 (예: D-1203)."""
    msp = ezdxf.readfile(dxf_path).modelspace()
    pieces, lines = read_geometry(msp)
    texts = read_texts(msp)
    sheet_texts = [(t, SHEET_RE.match(t.text)) for t in texts]
    sheet_texts = [(t, m) for t, m in sheet_texts if m]
    if sheet_texts:
        cp = _read_nesting(pieces, lines, texts, sheet_texts)
    else:
        cp = _read_unfold_list(pieces, lines, texts, tag)
    settle_holes(cp.pieces)
    return cp


def _read_nesting(pieces, lines, texts, sheet_texts) -> CutPlan:
    sheets: List[Sheet] = []
    border_ids = set()
    order = sorted(sheet_texts, key=lambda x: (-x[0].y, x[0].x))
    for i, (t, m) in enumerate(order, 1):
        w, l = float(m["w"]), float(m["l"])
        s = Sheet(
            sheet_id=i,
            material=m["material"].strip(),
            thickness=float(m["t"]),
            clad=m["clad"] or "",
            sheet_w=w,
            sheet_h=l,
            sheet_qty=int(m["qty"]),
            label_text=t.text,
        )
        cands = [
            p
            for p in pieces
            if abs(min(p.w, p.h) - min(w, l)) < 1.0
            and abs(max(p.w, p.h) - max(w, l)) < 1.0
        ]
        if cands:
            b = min(cands, key=lambda p: p.poly.distance(Point(t.x, t.y)))
            s.border, s.box = "found", b.poly.bounds
            border_ids.add(b.piece_id)
        sheets.append(s)
    boxes = [Polygon.from_bounds(*s.box) for s in sheets if s.box]

    def ok(p: Piece) -> bool:
        """판 테두리, 판을 감싸는 도면 틀, 판 밖의 형상, 네 변이 판 테두리에 닿는 면(부품을 놓고
        남은 자리)은 부품 조각이 아니다."""
        if p.piece_id in border_ids or any(p.poly.contains(b) for b in boxes):
            return False
        if sheet_of(*p.center) is None:
            return False
        x0, y0, x1, y1 = p.poly.bounds
        for b in boxes:
            bx0, by0, bx1, by1 = b.bounds
            if max(abs(x0 - bx0), abs(y0 - by0), abs(x1 - bx1), abs(y1 - by1)) < 1.0:
                return False
        return True

    def sheet_of(x, y) -> Optional[Sheet]:
        return next((s for s in sheets if s.contains(x, y)), None)

    used = {id(t) for t, _ in sheet_texts}
    refs = [t for t in texts if id(t) not in used and parse_ref(t.text)]
    used |= {id(t) for t in refs}
    parts: List[Part] = []
    for t in sorted(refs, key=lambda t: (-t.y, t.x)):
        tag, num = parse_ref(t.text)
        words = t.text.split(None, 1)
        name_t = _name_below(t, texts, used)
        if name_t is not None:
            used.add(id(name_t))
        s = sheet_of(t.x, t.y)
        parts.append(
            Part(
                part_no=len(parts) + 1,
                label_text=t.text,
                tag=tag,
                dwg_no=num,
                item=words[1].strip() if len(words) > 1 else "",
                name=name_t.text if name_t else "",
                material=s.material if s else "",
                thickness=s.thickness if s else None,
                qty=1,
                sheet_id=s.sheet_id if s else None,
                x=t.x,
                y=t.y,
                h_text=t.height,
            )
        )
    _assign(parts, pieces, lines, ok, sheet_of, hole_to_outer=False)
    part_pieces = [p for p in pieces if ok(p)]
    labelled = [p for p in part_pieces if p.part_no is not None]
    for p in part_pieces:  # copy: 같은 판의 같은 모양 조각
        if p.part_no is not None:
            continue
        same = [
            q
            for q in labelled
            if sheet_of(*q.center) is sheet_of(*p.center) and _same_shape(p, q)
        ]
        if len({q.part_no for q in same}) == 1:
            p.part_no, p.link = same[0].part_no, "copy"
    for t in texts:  # 판 밖 메모 (잔재 사용 등) 는 가장 가까운 판에 붙인다
        if id(t) in used or not boxes or "잔재" not in t.text:
            continue
        s = min(
            (s for s in sheets if s.box),
            key=lambda s: Polygon.from_bounds(*s.box).distance(Point(t.x, t.y)),
        )
        s.notes.append(t.text)
        used.add(id(t))
    unused = [t.text for t in texts if id(t) not in used]
    return CutPlan("nesting", sheets, parts, part_pieces, texts, unused)


def _read_unfold_list(pieces, lines, texts, tag) -> CutPlan:
    rows = [t for t in texts if t.kind == "TEXT" and ITEM_ROW_RE.match(t.text)]
    attrs = [t for t in texts if t.text.startswith("D=")]
    used = {id(t) for t in rows} | {id(t) for t in attrs}
    # 열: 아이템 번호의 x 가 비슷한 것끼리. 줄: 같은 열에서 이웃 번호와의 중간까지
    cols: List[List[Text]] = []
    for t in sorted(rows, key=lambda t: t.x):
        if cols and abs(cols[-1][0].x - t.x) < 4 * t.height:
            cols[-1].append(t)
        else:
            cols.append([t])
    bands = []  # (row text, x0, x1, y0, y1)
    for ci, col in enumerate(cols):
        x0 = min(t.x for t in col)
        x1 = min(t.x for t in cols[ci + 1]) if ci + 1 < len(cols) else math.inf
        col.sort(key=lambda t: -t.y)
        for ri, t in enumerate(col):
            top = (col[ri - 1].y + t.y) / 2 if ri > 0 else math.inf
            bot = (col[ri + 1].y + t.y) / 2 if ri + 1 < len(col) else -math.inf
            bands.append((t, x0, x1, bot, top))

    def band_of(x, y):
        return next((b for b in bands if b[1] <= x < b[2] and b[3] <= y < b[4]), None)

    def ok(p: Piece) -> bool:  # 줄 밖의 형상 (설명 그림) 은 부품 조각이 아니다
        return band_of(*p.center) is not None

    parts: List[Part] = []
    for t in attrs:
        a = parse_attrs(t.text)
        b = band_of(t.x, t.y)
        row = ITEM_ROW_RE.match(b[0].text) if b else None
        ref = parse_ref(t.text)
        parts.append(
            Part(
                part_no=0,
                label_text=t.text,
                tag=tag or (ref[0] if ref else ""),
                dwg_no=int(row["dwg"]) if row else (ref[1] if ref else None),
                item=(row["item"] or "") if row else "",
                name=a.get("name", ""),
                material=a.get("material", ""),
                thickness=_num(a.get("thickness", "")),
                size=a.get("size", ""),
                qty=int(_num(a["qty"])) if _num(a.get("qty", "")) else None,
                row=b[0].text if b else "",
                x=t.x,
                y=t.y,
                h_text=t.height,
            )
        )
    labelled_rows = {p.row for p in parts}
    for t, *_ in bands:  # 속성 글자가 없는 줄도 부품으로 남긴다 (형상만 있음)
        if t.text not in labelled_rows:
            m = ITEM_ROW_RE.match(t.text)
            parts.append(
                Part(0, t.text, tag, int(m["dwg"]), m["item"] or "", row=t.text)
            )
    parts.sort(key=lambda p: (p.dwg_no or 0, _item_key(p.item), -p.y, p.x))
    for i, p in enumerate(parts, 1):
        p.part_no = i
    labelled = [p for p in parts if p.label_text.startswith("D=")]
    _assign(labelled, pieces, lines, ok, band_of, hole_to_outer=True)
    in_band = [p for p in pieces if ok(p)]
    by_row = defaultdict(list)
    for p in parts:
        by_row[p.row].append(p)
    for pc in in_band:  # row: 같은 줄의 부품이 하나뿐이면 그 부품의 조각
        if pc.part_no is not None:
            continue
        b = band_of(*pc.center)
        row_parts = by_row.get(b[0].text, [])
        if len(row_parts) == 1:
            pc.part_no, pc.link = row_parts[0].part_no, "row"
    unused = [t.text for t in texts if id(t) not in used]
    cp = CutPlan("unfold_list", [], parts, in_band, texts, unused)
    for pc in in_band:
        pc.row = band_of(*pc.center)[0].text
    return cp


def as_rows(cp: CutPlan) -> Dict[str, List[dict]]:
    """CSV 로 쓸 행. sheets, parts, pieces."""
    by_piece = {p.piece_id: p for p in cp.pieces}
    by_sheet = {s.sheet_id: s for s in cp.sheets}

    def sheet_id_of(p: Piece):
        return next((s.sheet_id for s in cp.sheets if s.contains(*p.center)), "")

    n_pieces = defaultdict(int)
    for p in cp.pieces:
        if p.part_no is not None:
            n_pieces[p.part_no] += 1
    sheets = []
    for s in cp.sheets:
        d = asdict(s)
        notes = d.pop("notes")
        d.pop("box")
        d["n_parts"] = sum(1 for p in cp.parts if p.sheet_id == s.sheet_id)
        d["n_pieces"] = sum(1 for p in cp.pieces if sheet_id_of(p) == s.sheet_id)
        d["remnant"] = "yes" if notes else ""
        d["note"] = " / ".join(notes)
        sheets.append(d)
    parts = []
    for p in cp.parts:
        d = asdict(p)
        pc = by_piece.get(p.piece_id)
        s = by_sheet.get(p.sheet_id)
        d["dwg_ref"] = f"{p.tag}-{p.dwg_no:03d}" if p.tag and p.dwg_no else ""
        d["w"] = round(pc.w, 1) if pc else ""
        d["h"] = round(pc.h, 1) if pc else ""
        d["area"] = round(pc.net_area) if pc else ""
        d["holes"] = pc.n_holes if pc else ""
        d["n_pieces"] = n_pieces.get(p.part_no, 0)
        d["rel_x"] = round(pc.bounds[0] - s.box[0], 1) if pc and s and s.box else ""
        d["rel_y"] = round(pc.bounds[1] - s.box[1], 1) if pc and s and s.box else ""
        for k in ("x", "y", "h_text"):
            d.pop(k)
        parts.append(d)
    pieces = []
    for p in cp.pieces:
        pieces.append(
            {
                "piece_id": p.piece_id,
                "sheet_id": sheet_id_of(p),
                "row": p.row,
                "part_no": p.part_no or "",
                "link": p.link,
                "kind": p.kind,
                "w": round(p.w, 1),
                "h": round(p.h, 1),
                "area": round(p.net_area),
                "holes": p.n_holes,
                "n_ents": p.n_ents,
                "x0": round(p.bounds[0], 1),
                "y0": round(p.bounds[1], 1),
            }
        )
    return {"sheets": sheets, "parts": parts, "pieces": pieces}
