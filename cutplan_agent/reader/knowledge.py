"""Domain-knowledge loader: the reasoning VLM reads the project's skills/*.md before it judges.

`load_domain_prompt(topic)` follows docs/agent/skill_agent_framework.md §3-2: a topic is
the file stem of any markdown under the skills root (e.g. `unfold_rules`, `unfold_extract`,
`drawing_conventions_kr`). The root defaults to `<repo>/skills` next to this package and can be
moved with CUTPLAN_SKILLS_DIR. STAGE_TOPICS fixes which documents each reasoning stage reads.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# unfold_rules.md: "부품 유형을 정하기 전에 unfold_rules" (00_system_role_and_procedure.md 원칙 4)
STAGE_TOPICS = {
    "part_class": ("unfold_rules", "unfold_extract"),
    "unfold_params": ("unfold_extract", "unfold_rules", "drawing_conventions_kr"),
}


def skills_dir() -> Path:
    return Path(os.getenv("CUTPLAN_SKILLS_DIR") or DEFAULT_SKILLS_DIR)


def topics() -> dict[str, Path]:
    """Map topic (file stem) to path; Office lock files such as `~$README.md` are skipped."""
    root = skills_dir()
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        if path.name.startswith("~$") or path.stem in found:
            continue
        found[path.stem] = path
    return found


@lru_cache(maxsize=None)
def _read(path: Path, mtime_ns: int) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_domain_prompt(topic: str) -> dict:
    """Return {topic, path, sha256, text}; an unknown topic is a configuration error."""
    path = topics().get(topic)
    if path is None:
        raise FileNotFoundError(f"skill topic {topic!r} not found under {skills_dir()}")
    text, digest = _read(path.resolve(), path.stat().st_mtime_ns)
    return {"topic": topic, "path": str(path), "sha256": digest, "text": text}


def skill_system_prompt(names: list[str] | tuple[str, ...]) -> tuple[str, list[dict]]:
    """Join the requested documents into one system-prompt block plus their trace records."""
    docs = [load_domain_prompt(name) for name in names]
    body = "\n\n".join(
        f'<skill topic="{d["topic"]}">\n{d["text"].strip()}\n</skill>' for d in docs
    )
    guide = (
        "Domain knowledge (skills). Apply these rules when judging the part shape and reading values. "
        "When a skill describes tools, output fields or a JSON layout that differ from this task's "
        "output contract, follow the output contract and keep only the domain rules.\n\n"
        + body
    )
    return guide, [{k: d[k] for k in ("topic", "path", "sha256")} for d in docs]
