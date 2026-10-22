"""커팅플랜 부품 라벨이 가리키는 설계 도면을 입력 도면 파일에서 찾는다.

정답(커팅플랜)에 있는 부품이 입력 도면에서 나올 수 있는지 보는 데 쓴다. 입력에 없는 도면을
가리키는 부품은 에이전트가 아무리 잘해도 맞출 수 없다.

부품 라벨 형식은 워크오더마다 다르다. 아래 두 형식만 읽는다.
  "<설비 태그>-<3자리 도면 번호> <아이템>"  예) S-2120-002 1-1, 652-E-704-004 1-13
  "D=<설비 태그>-<도면 번호>[-<아이템>]..."  예) D=D-1203-2-2-1\\PN=BASE..., D=EA-1361-2-5\\PN=...
부품명만 있거나 재질·두께만 있는 라벨, 풍선 번호, 설비 태그만 있는 라벨("204-E-205")은
도면을 알 수 없는 라벨로 센다.

입력 도면 파일 이름은 영문 대문자와 숫자만 남겨 비교한다. 이름에 태그가 들어 있고 태그 바로 뒤의
첫 3자리 숫자가 도면 번호와 같으면 그 도면으로 본다.
  예) ("S-2120", 2) -> "VP-S-2120-DWG-002_R0 (DETAIL OF BODY).dwg"
      ("D-1203", 2) -> "VP-EVP-D-1203-OTH-002_0_DETAIL OF BODY & SUPPORT LUG.pdf"
"""

import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# 태그 뒤에 3자리 도면 번호, 그 뒤에 공백과 아이템이 와야 한다. 아이템이 없으면 설비 태그일 수 있다
_SPACED = re.compile(
    r"^\s*(?P<tag>[A-Z0-9][A-Z0-9/]*(?:-[A-Z0-9/]+)*?)-(?P<num>\d{3})(?=\s+\S)"
)
# 속성 블록 형식. 도면 번호 뒤에는 -, \, 쉼표, 공백이 오거나 문자열이 끝난다
_ATTR = re.compile(r"D=(?P<tag>[A-Z0-9/][A-Z0-9/\-]*?)-(?P<num>\d{1,3})(?=[-\\,\s]|$)")


def parse_ref(label: str) -> Optional[Tuple[str, int]]:
    """부품 라벨에서 (설비 태그, 도면 번호) 를 읽는다. 읽을 수 없으면 None."""
    label = (label or "").upper()
    m = _ATTR.search(label) or _SPACED.match(label)
    if not m:
        return None
    return m.group("tag"), int(m.group("num"))


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def find_drawings(tag: str, num: int, names: Iterable[str]) -> List[str]:
    """입력 도면 파일 이름 중 (태그, 도면 번호) 에 해당하는 것."""
    t = _norm(tag)
    hits = []
    for name in names:
        s = _norm(Path(name).stem)
        i = s.find(t)
        while i >= 0:
            m = re.search(r"\d{3}", s[i + len(t) :])
            if m and int(m.group()) == num:
                hits.append(name)
                break
            i = s.find(t, i + 1)
    return hits


def ref_text(tag: str, num: int) -> str:
    return f"{tag}-{num:03d}"


def coverage(labels: Iterable[str], names: Iterable[str]) -> dict:
    """라벨마다 도면을 찾아 센다. 아무것도 빼거나 막지 않고 숫자만 돌려준다.

    반환: parts (라벨 수), with_ref (도면 번호를 읽은 라벨), missing (입력에 그 도면이 없는 라벨),
    missing_refs (도면별 개수, 많은 순), found_refs (찾은 도면 -> 파일 이름).
    """
    names = list(names)
    n = with_ref = 0
    missing: Counter = Counter()
    hits_by_ref: dict = {}
    for label in labels:
        n += 1
        ref = parse_ref(label)
        if ref is None:
            continue
        with_ref += 1
        key = ref_text(*ref)
        if key not in hits_by_ref:
            hits_by_ref[key] = sorted(find_drawings(*ref, names))
        if not hits_by_ref[key]:
            missing[key] += 1
    return {
        "parts": n,
        "with_ref": with_ref,
        "missing": sum(missing.values()),
        "missing_refs": missing.most_common(),
        "found_refs": {k: v for k, v in hits_by_ref.items() if v},
    }


def missing_text(cov: dict) -> str:
    """index.csv 한 칸에 넣을 문자열. 예) S-2120-004 x5; S-2120-006 x1"""
    return "; ".join(f"{k} x{v}" for k, v in cov["missing_refs"])
