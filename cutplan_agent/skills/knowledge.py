# -*- coding: utf-8 -*-
"""
도메인 지식 로더. '어떤 지식을 언제 불러오는가' 자체가 정책(policy)의 일부가 되도록 skill 로 노출한다.

knowledge/<topic>.md 를 그대로 돌려준다. topic 목록은 list_topics() 로.
"""

from pathlib import Path
from typing import Dict, List

from ..config import KNOWLEDGE_DIR
from ..state import logged


def list_topics() -> List[Dict[str, str]]:
    out = []
    for p in sorted(KNOWLEDGE_DIR.glob("*.md")):
        first = (
            p.read_text(encoding="utf8").strip().splitlines()[0].lstrip("# ").strip()
        )
        out.append({"topic": p.stem, "title": first})
    return out


@logged
def load_domain_prompt(topic: str) -> dict:
    """도메인 지식 문서를 불러온다. topic: drawing_conventions_kr | unfold_rules | split_and_margin |
    material_mapping | nesting_rules | design_data_ga | por_format"""
    p = KNOWLEDGE_DIR / f"{topic}.md"
    if not p.exists():
        return {
            "error": f"없는 topic: {topic}",
            "available": [t["topic"] for t in list_topics()],
        }
    return {"topic": topic, "text": p.read_text(encoding="utf8")}
