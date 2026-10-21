"""
part_tags.csv 의 part_name 을 정규화해 형상 class 라벨을 붙이고,
커팅플랜에서 잘라낸 부품 전개 DXF(Data/dataset/KDM/*/*/unfold/*.dxf) 를 PNG 로 렌더해
이미지 경로 ↔ class 데이터셋을 만든다.

출력 (Data/part_class_dataset/)
  part_tags_labeled.csv   part_tags.csv 838행 + name_norm / name_family / shape / class
  dataset.csv             image_path, class, source(tag|label), 메타데이터
  images/<class>/*.png    부품 전개 외곽 렌더 (흰 배경, 검은 선, 정사각 캔버스)
  class_rules.md          적용한 규칙 요약
  README.md

실행:
  py scripts/build_part_class_dataset.py --dry      # 분류만, 이미지 없음
  py scripts/build_part_class_dataset.py            # 전체
  py scripts/build_part_class_dataset.py --only-ok  # match=ok 만 렌더
"""
import os, re, csv, sys, glob, json, random, argparse, collections

BASE = r"D:\노바투스2026"
TAGS_CSV = os.path.join(BASE, "Data", "_dataset", "part_tags.csv")
UNFOLD_GLOB = os.path.join(BASE, "Data", "dataset", "KDM", "*", "*", "unfold", "index.csv")
OUT = os.path.join(BASE, "Data", "part_class_dataset")
IMG_PX = 512
CLASSES = ["cylinder", "cone", "head", "ring", "flat"]

# ---------------------------------------------------------------- 1. 이름 정규화
MTEXT_FMT = re.compile(r"\\f[^;]*;|\\[A-Za-z][^;]*;|[{}]")

# (정규식, name_norm, name_family)  — 위에서부터 첫 매칭
NAME_RULES = [
    (r"^JACKET\s*SHELL",                       "JACKET SHELL",     "SHELL"),
    (r"^(L[/ ]?SHELL|L SHELL)",                "L SHELL",          "SHELL"),
    (r"^(CH|C)[ _/]?SHELL",                    "CHANNEL SHELL",    "SHELL"),
    (r"^S SHELL",                              "S SHELL",          "SHELL"),
    (r"^SHELL",                                "SHELL",            "SHELL"),
    (r"^CHANNEL",                              "CHANNEL",          "SHELL"),
    (r"^SKIRT",                                "SKIRT",            "SHELL"),
    (r"^CONE",                                 "CONE",             "CONE"),
    (r"^JACKET\s*HEAD",                        "JACKET HEAD",      "HEAD"),
    (r"^(TOP|BTM|BOTTOM)\s*HEAD",              "HEAD",             "HEAD"),
    (r"^[SC]/HEAD",                            "HEAD",             "HEAD"),
    (r"^HEAD",                                 "HEAD",             "HEAD"),
    # 노즐·맨홀 마크: N1, N11 INT, K1A,K1B, M1, MH1, S1, T1, H1, V1, D1, A1, E1, L2b, N4a ...
    (r"^(?:[A-Z]{1,2}\d{1,2}[a-z]?[A-Z]?(?:\s*INT)?(?:\s*,\s*)?)+\s*(?:/|$)", "NOZZLE", "NOZZLE"),
    (r"^(MH|M|N|K|S|T|H|V|D|A|E|L)\d{1,2}[a-z]?[A-Z]?\s+(NECK|SLEEVE)", "NOZZLE NECK", "NOZZLE"),
    (r"^(MH|M|N|K|S|T|H|V|D|A|E|L)\d{1,2}[a-z]?[A-Z]?\s+(LAP\s*PL)",  "NOZZLE LAP PLATE", "NOZZLE"),
    (r"^(MH|M|N|K|S|T|H|V|D|A|E|L)\d{1,2}[a-z]?[A-Z]?\s*(PAD|\s*,.*PAD)", "NOZZLE PAD", "PAD"),
    (r"^N/Z\s*NECK",                           "NOZZLE NECK",      "NOZZLE"),
    (r"^N/Z\s*PAD",                            "NOZZLE PAD",       "PAD"),
    (r"^[A-D]\s*PAD/",                         "NOZZLE PAD",       "PAD"),
    (r"^M\s*PAD/",                             "NOZZLE PAD",       "PAD"),
    (r"^K\d\s*PAD",                            "NOZZLE PAD",       "PAD"),
    (r"^(SADDLE|LIFT|LEG|LUG)[ _]?PAD",        "SUPPORT PAD",      "PAD"),
    (r"^(REINF\.?|RE-?)\s*PAD",                "REINF PAD",        "PAD"),
    (r"^PAD$",                                 "PAD",              "PAD"),
    (r"^(LIFT(ING)?|TAILDING|TAILING|EARTH)?\s*LUG", "LIFTING LUG", "LUG"),
    (r"^LIFT\s*RIB",                           "LIFT RIB",         "RIB"),
    (r"^(INT\.?|NOZ)\s*RIB",                   "RIB",              "RIB"),
    (r"^RIB",                                  "RIB",              "RIB"),
    (r"^GUSSET",                               "GUSSET",           "GUSSET"),
    (r"^STIFF",                                "STIFFENER",        "RIB"),
    (r"^BASE\s*PL",                            "BASE PLATE",       "SUPPORT PLATE"),
    (r"^WEB\s*PL",                             "WEB PLATE",        "SUPPORT PLATE"),
    (r"^(WEAR|BEAR)\s*PL",                     "WEAR PLATE",       "SUPPORT PLATE"),
    (r"^SL(I)?DING\s*(PL|SHOE)",               "SLIDING PLATE",    "SUPPORT PLATE"),
    (r"^(SUPT|SUPPORT|CONN|TOP|END|PUSH|DOWER PIN)\s*PL", "SUPPORT PLATE", "SUPPORT PLATE"),
    (r"^(IMP\.?|IMPINGEMENT)\s*(PL|BAFFLE)",   "IMPINGEMENT PLATE","INTERNAL"),
    (r"^BAFFLE",                               "BAFFLE",           "INTERNAL"),
    (r"^VORT",                                 "VORTEX BREAKER",   "INTERNAL"),
    (r"^DEFLECTOR",                            "DEFLECTOR",        "INTERNAL"),
    (r"^PASS\s*PART",                          "PASS PARTITION",   "INTERNAL"),
    (r"^(CH_)?COVER",                          "COVER PLATE",      "COVER"),
    (r"^SEAL(ING)?\s*STRIP",                   "SEALING STRIP",    "INTERNAL"),
    (r"^J\s*CLOSER",                           "J CLOSER",         "INTERNAL"),
    (r"^AH-",                                  "AH PLATE",         "INTERNAL"),
    (r"^LADDER",                               "LADDER",           "EXTERNAL"),
    (r"^INS(UL)?\.?\s*RING",                   "INSULATION RING",  "RING"),
    (r"^INS(UL)?\.?\s*CLIP",                   "INSULATION CLIP",  "CLIP"),
    (r"^FIRE\s*CLIP",                          "FIRE CLIP",        "RING"),
    (r"^COMP\s*RING",                          "COMPRESSION RING", "RING"),
    (r"^TEMPLATE",                             "TEMPLATE",         "RING"),
]
NAME_RULES = [(re.compile(p, re.I), n, f) for p, n, f in NAME_RULES]

# parts.csv 의 자유 텍스트 라벨(태그 없는 부품)에서 쓸 키워드 (포함 검색)
LABEL_KEYWORDS = [
    (r"LIFTING\s*LUG|LIFT\s*LUG|EARTH\s*LUG|TAIL(ING|DING)\s*LUG", "LIFTING LUG", "LUG"),
    (r"RIB\s*PL(ATE)?|\bRIB\b",            "RIB",              "RIB"),
    (r"PASS\s*PARTITION",                  "PASS PARTITION",   "INTERNAL"),
    (r"SEAL(ING)?\s*STRIP",                "SEALING STRIP",    "INTERNAL"),
    (r"BASE\s*PL(ATE)?",                   "BASE PLATE",       "SUPPORT PLATE"),
    (r"WEB\s*PL(ATE)?",                    "WEB PLATE",        "SUPPORT PLATE"),
    (r"SLIDING\s*SHOE|SLIDING\s*PL",       "SLIDING PLATE",    "SUPPORT PLATE"),
    (r"SADDLE\s*PAD",                      "SUPPORT PAD",      "PAD"),
    (r"REINF\.?\s*PAD|RE-?PAD",            "REINF PAD",        "PAD"),
    (r"INSUL\.?\s*CLIP|INS\.?\s*CLIP",     "INSULATION CLIP",  "CLIP"),
    (r"INSUL\.?\s*RING|INS\.?\s*RING",     "INSULATION RING",  "RING"),
    (r"\bCONE\b",                          "CONE",             "CONE"),
    (r"\bHEAD\b",                          "HEAD",             "HEAD"),
    (r"\bSHELL(-\d)?\b",                   "SHELL",            "SHELL"),
    (r"\bBAFFLE\b",                        "BAFFLE",           "INTERNAL"),
    (r"GUSSET",                            "GUSSET",           "GUSSET"),
    (r"COVER\s*PL",                        "COVER PLATE",      "COVER"),
    (r"WEAR\s*PL",                         "WEAR PLATE",       "SUPPORT PLATE"),
]
LABEL_KEYWORDS = [(re.compile(p, re.I), n, f) for p, n, f in LABEL_KEYWORDS]

NOZZLE_MARK = re.compile(r"^(?P<marks>[A-Z]{1,2}\d{1,2}[a-z]?[A-Z]?(?:\s*INT)?(?:\s*,\s*[A-Z]{1,2}\d{1,2}[a-z]?[A-Z]?)*)\s*(?:/\s*(?P<inch>B?\d+(?:,\d+)?B?))?", re.I)


def clean_name(raw):
    s = MTEXT_FMT.sub("", raw or "")
    s = s.replace("\u2300", "⌀").strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def normalize_name(raw):
    """-> (name_clean, name_norm, name_family, nozzle_mark, nozzle_inch)"""
    s = clean_name(raw)
    mark = inch = ""
    for rx, norm, fam in NAME_RULES:
        if rx.search(s):
            if fam in ("NOZZLE", "PAD") and norm in ("NOZZLE", "NOZZLE NECK", "NOZZLE PAD", "NOZZLE LAP PLATE"):
                m = NOZZLE_MARK.match(s)
                if m:
                    mark = m.group("marks").replace(" ", "")
                    inch = (m.group("inch") or "").replace("B", "")
                # "/24B", "/22B" 처럼 뒤에 붙는 인치
                m2 = re.search(r"/\s*B?(\d+)B?\s*$", s)
                if m2 and not inch:
                    inch = m2.group(1)
            return s, norm, fam, mark, inch
    return s, s, "OTHER", mark, inch


# ---------------------------------------------------------------- 2. size 파싱
SIZE_RECT = re.compile(r"^(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)$")
SIZE_RECT_R = re.compile(r"^(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*[xX]\s*R(\d+(?:\.\d+)?)$")
SIZE_DISC = re.compile(r"^⌀(\d+(?:\.\d+)?)$")
SIZE_RING = re.compile(r"^⌀(\d+(?:\.\d+)?)\s*[xX]\s*⌀(\d+(?:\.\d+)?)(?:\s*/\s*(\d+))?$")


def parse_size(raw):
    s = MTEXT_FMT.sub("", raw or "").replace("%%C", "⌀").replace("\u2300", "⌀").replace(" ", "")
    m = SIZE_RING.match(s)
    if m:
        return {"shape": "ring_split" if m.group(3) else "ring", "d_in": float(m.group(1)),
                "d_out": float(m.group(2)), "n_split": int(m.group(3) or 1), "w": "", "h": "", "r": ""}
    m = SIZE_DISC.match(s)
    if m:
        return {"shape": "disc", "d_in": "", "d_out": float(m.group(1)), "n_split": 1, "w": "", "h": "", "r": ""}
    m = SIZE_RECT_R.match(s)
    if m:
        return {"shape": "rect_radius", "d_in": "", "d_out": "", "n_split": 1,
                "w": float(m.group(1)), "h": float(m.group(2)), "r": float(m.group(3))}
    m = SIZE_RECT.match(s)
    if m:
        return {"shape": "rect", "d_in": "", "d_out": "", "n_split": 1,
                "w": float(m.group(1)), "h": float(m.group(2)), "r": ""}
    return {"shape": "unknown", "d_in": "", "d_out": "", "n_split": 1, "w": "", "h": "", "r": ""}


# ---------------------------------------------------------------- 3. class 결정
CYL_FAMILY_NORM = {"SHELL", "L SHELL", "CHANNEL SHELL", "S SHELL", "JACKET SHELL", "CHANNEL", "SKIRT", "NOZZLE NECK"}


def decide_class(name_norm, family, shape):
    """(class, rule) 태그 행: 이름 계열 + size 형식"""
    if family == "HEAD":
        return "head", "family=HEAD"
    if family == "CONE":
        return "cone", "family=CONE"
    if name_norm in CYL_FAMILY_NORM and shape in ("rect", "unknown"):
        return "cylinder", "cylinder family + rect"
    if name_norm == "NOZZLE":                      # 마크만 있는 이름: size 로 결정
        if shape in ("ring", "ring_split"):
            return "ring", "nozzle mark + ring size"
        if shape == "rect":
            return "cylinder", "nozzle mark + rect size (neck)"
        if shape == "disc":
            return "flat", "nozzle mark + disc size"
        return "flat", "nozzle mark + unknown size"
    if shape in ("ring", "ring_split"):
        return "ring", "ring size"
    if shape == "disc":
        return "flat", "disc size"
    return "flat", "default flat"


def decide_class_from_geometry(family, w, h, holes):
    """태그 없는 부품(라벨 텍스트만): 이름 계열 + bbox/구멍 기하"""
    if family == "HEAD":
        return "head", "label HEAD"
    if family == "CONE":
        return "cone", "label CONE"
    if family == "SHELL":
        return "cylinder", "label SHELL"
    if family in ("PAD", "RING"):
        try:
            w, h, holes = float(w), float(h), int(float(holes))
        except Exception:
            return "flat", "label pad (no geom)"
        if w > 0 and h > 0 and abs(w - h) / max(w, h) < 0.08 and holes >= 1:
            return "ring", "label pad + square bbox + hole"
        return "flat", "label pad + non-ring geom"
    return "flat", "label flat family"


# ---------------------------------------------------------------- 4. part_tags_labeled.csv
def build_tags_labeled():
    rows = list(csv.DictReader(open(TAGS_CSV, encoding="utf-8-sig")))
    out = []
    for r in rows:
        name_clean, norm, fam, mark, inch = normalize_name(r["part_name"])
        sz = parse_size(r["size"])
        cls, rule = decide_class(norm, fam, sz["shape"])
        out.append({**r, "name_clean": name_clean, "name_norm": norm, "name_family": fam,
                    "nozzle_mark": mark, "nozzle_inch": inch,
                    "shape": sz["shape"], "size_w": sz["w"], "size_h": sz["h"], "size_r": sz["r"],
                    "d_in": sz["d_in"], "d_out": sz["d_out"], "n_split": sz["n_split"],
                    "class": cls, "class_rule": rule})
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "part_tags_labeled.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    return out


# ---------------------------------------------------------------- 5. unfold index → 라벨 행
def collect_unfold_rows():
    rows = []
    for idx in glob.glob(UNFOLD_GLOB):
        d = os.path.dirname(idx)
        wo = os.path.basename(os.path.dirname(d))
        year = os.path.basename(os.path.dirname(os.path.dirname(d)))
        for r in csv.DictReader(open(idx, encoding="utf-8-sig")):
            r["_wo"], r["_year"], r["_dir"] = wo, year, d
            rows.append(r)
    return rows


def label_unfold_rows(rows):
    out = []
    for r in rows:
        if not r["file"]:
            continue
        if r["tag_name"]:
            name_clean, norm, fam, mark, inch = normalize_name(r["tag_name"])
            sz = parse_size(r["tag_size"])
            cls, rule = decide_class(norm, fam, sz["shape"])
            src, name_raw, size_raw = "tag", r["tag_name"], r["tag_size"]
        else:
            lab = clean_name(r["label"])
            if not lab or re.fullmatch(r"[\d.\-]+", lab):
                continue
            hit = None
            for rx, norm, fam in LABEL_KEYWORDS:
                if rx.search(lab):
                    hit = (norm, fam); break
            if not hit:
                continue
            norm, fam = hit
            name_clean, mark, inch = lab, "", ""
            sz = parse_size("")
            cls, rule = decide_class_from_geometry(fam, r["w"], r["h"], r["holes"])
            src, name_raw, size_raw = "label", r["label"], ""
        out.append({
            "image_path": "", "class": cls, "source": src, "class_rule": rule,
            "year": r["_year"], "workorder": r["_wo"], "drawing": r["drawing"],
            "sheet_id": r["sheet_id"], "part_idx": r["part_idx"], "match": r["match"], "sheet_quality": r["quality"],
            "name_raw": name_raw, "name_clean": name_clean, "name_norm": norm, "name_family": fam,
            "nozzle_mark": mark, "nozzle_inch": inch,
            "size_raw": size_raw, "shape": sz["shape"],
            "material": r["tag_material"] or r["material"], "thickness": r["tag_thickness"] or r["thickness"],
            "qty": r["tag_qty"], "dwg_no": r["tag_dwg_no"],
            "bbox_w": r["w"], "bbox_h": r["h"], "rel_x": r["rel_x"], "rel_y": r["rel_y"],
            "n_ents": r["n_ents"], "holes": r["holes"],
            "unfold_dxf": os.path.relpath(os.path.join(r["_dir"], r["file"]), BASE).replace("\\", "/"),
        })
    return out


# ---------------------------------------------------------------- 5b. 외곽 닫힘 검사 + 재절단
NEST_JSON = os.path.join(BASE, "Data", "_dataset", "nesting_dataset.json")
CP_DXF_GLOB = os.path.join(BASE, "Data", "dataset", "KDM", "*", "*", "cutting_plan", "{drawing}.dxf")
RECUT_DIR = os.path.join(OUT, "recut_dxf")
GEOM = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE"}
EXCLUDE_LAYERS = {"부재번호"}
LOOP_TOL = 1.0   # 끝점 동일 판정 mm
CUT_TOL = 2.0    # bbox 포함 판정 mm


def _endpoints(e):
    """엔티티의 (끝점 목록, 자체 닫힘 여부). 끝점이 없으면 닫힌 도형."""
    pts, closed = _endpoints_raw(e)
    from ezdxf.math import Vec3
    return [Vec3(p) for p in pts], closed


def _endpoints_raw(e):
    from ezdxf.math import Vec3
    t = e.dxftype()
    try:
        if t == "LINE":
            return [e.dxf.start, e.dxf.end], False
        if t == "ARC":
            return [e.start_point, e.end_point], False
        if t == "CIRCLE":
            return [], True
        if t == "LWPOLYLINE":
            pts = [Vec3(v) for v in e.vertices()]
            if e.closed or (len(pts) > 2 and (pts[0] - pts[-1]).magnitude < LOOP_TOL):
                return [], True
            return [pts[0], pts[-1]], False
        if t == "POLYLINE":
            pts = [v.dxf.location for v in e.vertices]
            if e.is_closed or (len(pts) > 2 and (pts[0] - pts[-1]).magnitude < LOOP_TOL):
                return [], True
            return [pts[0], pts[-1]], False
        if t == "ELLIPSE":
            if abs(e.dxf.end_param - e.dxf.start_param) >= 2 * 3.14159 - 1e-3:
                return [], True
            return [e.start_point, e.end_point], False
        if t == "SPLINE":
            pts = list(e.control_points)
            if e.closed:
                return [], True
            return [pts[0], pts[-1]], False
    except Exception:
        pass
    return [], False


def loop_check(msp):
    """-> (closed, n_open_ends, n_loops, n_geom). 모든 끝점이 짝수 차수면 닫힘."""
    from ezdxf.math import Vec3
    nodes = []  # (Vec3, degree)
    n_loops = n_geom = 0
    for e in msp:
        if e.dxftype() not in GEOM:
            continue
        n_geom += 1
        pts, self_closed = _endpoints(e)
        if self_closed:
            n_loops += 1
            continue
        for p in pts:
            p = Vec3(p)
            for i, (q, d) in enumerate(nodes):
                if (p - q).magnitude < LOOP_TOL:
                    nodes[i] = (q, d + 1); break
            else:
                nodes.append((p, 1))
    n_open = sum(1 for _, d in nodes if d % 2 == 1)
    # 열린 체인이 없으면 연결 엔티티들이 최소 한 개의 루프를 이룬다
    if nodes and n_open == 0:
        n_loops += 1
    return (n_geom > 0 and n_open == 0), n_open, n_loops, n_geom


def _ent_points(e):
    """bbox 포함 판정에 쓸 대표점들."""
    from ezdxf.math import Vec3
    return [Vec3(p) for p in _ent_points_raw(e)]


def _ent_points_raw(e):
    t = e.dxftype()
    try:
        if t == "LINE":
            return [e.dxf.start, e.dxf.end]
        if t == "ARC":
            return [e.start_point, e.end_point]
        if t == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            return [c.replace(x=c.x - r), c.replace(x=c.x + r), c.replace(y=c.y - r), c.replace(y=c.y + r)]
        if t == "LWPOLYLINE":
            return list(e.vertices())
        if t == "POLYLINE":
            return [v.dxf.location for v in e.vertices]
        if t == "ELLIPSE":
            return [e.start_point, e.end_point, e.dxf.center]
        if t == "SPLINE":
            return list(e.control_points)
    except Exception:
        pass
    return []


class Recutter:
    """parts.csv bbox 안에 *끝점이* 들어오는 엔티티를 CP DXF 에서 다시 잘라낸다 (ARC 누락 보완)."""
    def __init__(self):
        self.origin = {}
        for sh in json.load(open(NEST_JSON, encoding="utf8")):
            self.origin[(sh["drawing"], str(sh["sheet_id"]))] = (sh["origin"], sh["sheet_w"], sh["sheet_h"])
        self.docs = {}

    def msp(self, drawing):
        if drawing not in self.docs:
            import ezdxf
            paths = glob.glob(CP_DXF_GLOB.format(drawing=glob.escape(drawing)))
            self.docs[drawing] = ezdxf.readfile(paths[0]).modelspace() if paths else None
        return self.docs[drawing]

    def recut(self, r, dst):
        import ezdxf
        key = (r["drawing"], str(r["sheet_id"]))
        if key not in self.origin:
            return None
        (ox, oy), sw, sh = self.origin[key]
        msp = self.msp(r["drawing"])
        if msp is None:
            return None
        x0, y0 = ox + float(r["rel_x"]), oy + float(r["rel_y"])
        x1, y1 = x0 + float(r["bbox_w"]), y0 + float(r["bbox_h"])
        picked = []
        for e in msp:
            if e.dxftype() not in GEOM or e.dxf.layer in EXCLUDE_LAYERS:
                continue
            pts = _ent_points(e)
            if not pts:
                continue
            if all(x0 - CUT_TOL <= p.x <= x1 + CUT_TOL and y0 - CUT_TOL <= p.y <= y1 + CUT_TOL for p in pts):
                xs = [p.x for p in pts]; ys = [p.y for p in pts]
                if (max(xs) - min(xs) >= sw - CUT_TOL) and (max(ys) - min(ys) >= sh - CUT_TOL):
                    continue  # 판재 외곽선
                picked.append(e)
        if not picked:
            return None
        new = ezdxf.new("R2010"); nmsp = new.modelspace(); new.layers.add("BLANK")
        for e in picked:
            c = e.copy(); c.translate(-x0, -y0, 0); c.dxf.layer = "BLANK"; nmsp.add_entity(c)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        new.saveas(dst)
        return nmsp


def check_and_recut(ds, log=print):
    """각 행에 outline_closed / n_open_ends / n_loops / recut / geom_dxf 를 채운다."""
    import ezdxf
    rc = Recutter()
    n_closed = n_recut = n_fixed = 0
    for i, r in enumerate(ds):
        src = os.path.join(BASE, r["unfold_dxf"])
        try:
            closed, n_open, n_loops, n_geom = loop_check(ezdxf.readfile(src).modelspace())
        except Exception:
            closed, n_open, n_loops, n_geom = False, -1, 0, 0
        r.update({"outline_closed": int(closed), "n_open_ends": n_open, "n_loops": n_loops, "n_geom": n_geom,
                  "recut": 0, "geom_dxf": r["unfold_dxf"]})
        if closed:
            n_closed += 1
        else:
            stem = f"{r['workorder']}_{re.sub(r'[^A-Za-z0-9_-]+', '_', r['drawing'])}_S{int(r['sheet_id']):02d}_P{int(r['part_idx']):03d}"
            dst = os.path.join(RECUT_DIR, stem + ".dxf")
            try:
                nmsp = rc.recut(r, dst)
            except Exception as e:
                nmsp = None
            if nmsp is not None:
                c2, o2, l2, g2 = loop_check(nmsp)
                if c2 or (o2 < n_open and g2 > n_geom):
                    n_recut += 1; n_fixed += int(c2)
                    r.update({"outline_closed": int(c2), "n_open_ends": o2, "n_loops": l2, "n_geom": g2,
                              "recut": 1, "geom_dxf": os.path.relpath(dst, BASE).replace("\\", "/")})
                else:
                    try: os.remove(dst)
                    except OSError: pass
        if (i + 1) % 300 == 0:
            log(f"  loop-check {i+1}/{len(ds)} closed={n_closed} recut={n_recut} fixed={n_fixed}")
    log(f"loop-check done: closed(original)={n_closed} recut={n_recut} closed(after recut)={n_fixed} / {len(ds)}")


# ---------------------------------------------------------------- 6. 렌더
def render_dxf(src, dst, px=IMG_PX):
    import ezdxf
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, LineweightPolicy
    from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_policy=LineweightPolicy.ABSOLUTE, min_lineweight=0.6)
    backend = PyMuPdfBackend()
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(msp, finalize=True)
    # 정사각 캔버스, 여백 6%
    from ezdxf.addons.drawing import layout
    page = layout.Page(px, px, layout.Units.px, margins=layout.Margins.all(px * 0.06))
    settings = layout.Settings(fit_page=True, scale=1)
    png = backend.get_pixmap_bytes(page, fmt="png", settings=settings, render_box=None)
    with open(dst, "wb") as f:
        f.write(png)


def render_all(ds, only_ok, limit=None, log=print):
    done = fail = 0
    for i, r in enumerate(ds):
        if only_ok and r["match"] != "ok":
            continue
        cls_dir = os.path.join(OUT, "images", r["class"])
        os.makedirs(cls_dir, exist_ok=True)
        stem = f"{r['workorder']}_{re.sub(r'[^A-Za-z0-9_-]+', '_', r['drawing'])}_S{int(r['sheet_id']):02d}_P{int(r['part_idx']):03d}"
        dst = os.path.join(cls_dir, stem + ".png")
        r["image_path"] = os.path.relpath(dst, OUT).replace("\\", "/")
        src = os.path.join(BASE, r.get("geom_dxf") or r["unfold_dxf"])
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            done += 1; continue
        try:
            render_dxf(src, dst)
            done += 1
        except Exception as e:
            fail += 1; r["image_path"] = ""; r["class_rule"] += f" | render_fail:{type(e).__name__}"
        if (done + fail) % 200 == 0:
            log(f"  rendered {done} fail {fail} / {i+1}")
        if limit and done >= limit:
            break
    return done, fail


# ---------------------------------------------------------------- 7. split, 저장
def assign_split(ds, seed=0):
    random.seed(seed)
    by_cls = collections.defaultdict(list)
    for r in ds:
        if r["image_path"]:
            by_cls[r["class"]].append(r)
    for cls, rs in by_cls.items():
        random.shuffle(rs)
        n = len(rs)
        for i, r in enumerate(rs):
            r["split"] = "train" if i < n * 0.8 else ("val" if i < n * 0.9 else "test")
    for r in ds:
        r.setdefault("split", "")


def write_dataset(ds):
    fields = ["image_path", "class", "split", "source", "match", "outline_closed", "n_open_ends", "n_loops", "n_geom",
              "recut", "geom_dxf", "class_rule", "year", "workorder", "drawing",
              "sheet_id", "part_idx", "sheet_quality", "name_raw", "name_clean", "name_norm", "name_family",
              "nozzle_mark", "nozzle_inch", "size_raw", "shape", "material", "thickness", "qty", "dwg_no",
              "bbox_w", "bbox_h", "rel_x", "rel_y", "n_ents", "holes", "unfold_dxf"]
    with open(os.path.join(OUT, "dataset.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(ds)


def summarize(ds, tags):
    s = {}
    s["tags_total"] = len(tags)
    s["tags_by_class"] = dict(collections.Counter(r["class"] for r in tags))
    s["tags_by_name_norm"] = dict(collections.Counter(r["name_norm"] for r in tags).most_common())
    s["tags_by_shape"] = dict(collections.Counter(r["shape"] for r in tags))
    s["ds_total"] = len(ds)
    s["ds_with_image"] = sum(1 for r in ds if r["image_path"])
    s["ds_by_class_source"] = {f"{c}/{src}": n for (c, src), n in sorted(collections.Counter((r["class"], r["source"]) for r in ds if r["image_path"]).items())}
    s["ds_by_class_match"] = {f"{c}/{m}": n for (c, m), n in sorted(collections.Counter((r["class"], r["match"]) for r in ds if r["image_path"]).items())}
    s["ds_by_split_class"] = {f"{sp}/{c}": n for (sp, c), n in sorted(collections.Counter((r["split"], r["class"]) for r in ds if r["image_path"]).items())}
    s["ds_by_class_closed"] = {f"{c}/closed={cl}": n for (c, cl), n in sorted(collections.Counter((r["class"], r.get("outline_closed", "")) for r in ds if r["image_path"]).items())}
    s["ds_recut"] = sum(1 for r in ds if r.get("recut") == 1)
    s["ds_by_wo"] = dict(collections.Counter(r["workorder"] for r in ds if r["image_path"]).most_common())
    s["ds_by_name_norm"] = dict(collections.Counter(r["name_norm"] for r in ds if r["image_path"]).most_common())
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="분류만, 렌더 없음")
    ap.add_argument("--only-ok", action="store_true", help="match=ok 만 렌더")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    tags = build_tags_labeled()
    print(f"part_tags_labeled.csv: {len(tags)} rows, class={dict(collections.Counter(r['class'] for r in tags))}")
    print("  shape:", dict(collections.Counter(r["shape"] for r in tags)))
    print("  OTHER family names:", sorted(set(r["name_clean"] for r in tags if r["name_family"] == "OTHER")))

    ds = label_unfold_rows(collect_unfold_rows())
    print(f"dataset candidates: {len(ds)}  by source={dict(collections.Counter(r['source'] for r in ds))}  by class={dict(collections.Counter(r['class'] for r in ds))}")
    if a.dry:
        for r in ds:
            r["split"] = ""
        write_dataset(ds)
        json.dump(summarize(ds, tags), open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    check_and_recut(ds)
    done, fail = render_all(ds, a.only_ok, a.limit)
    print(f"rendered {done}, failed {fail}")
    assign_split(ds)
    write_dataset(ds)
    s = summarize(ds, tags)
    json.dump(s, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: s[k] for k in ("ds_with_image", "ds_by_class_source", "ds_by_class_closed", "ds_recut", "ds_by_split_class")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
