"""
git 에서 뺀 데이터가 제자리에 있고, 옮긴 원본과 같은지 확인한다. 서버를 옮긴 뒤 처음 돌린다.

    PYTHONPATH=. uv run python scripts/check_data.py            # 모든 데이터 확인
    PYTHONPATH=. uv run python scripts/check_data.py --write Data   # 지금 있는 Data/ 로 기준 파일을 다시 쓴다

기준 파일은 scripts/data_manifests/ 에 있고 git 으로 관리한다. 두 종류다.

  - 파일별 (*.sha256): `sha256sum` 형식. 합성 도면처럼 파일 이름이 공개돼도 되는 것.
  - 요약 (*.digest): 파일 수, 전체 바이트, 파일별 (경로, sha256) 을 이어 붙인 sha256 하나.
    고객 데이터라 파일 이름을 public 레포에 남기지 않는 것 (Data/, test_data/).

어디서 받아 어디에 두는지는 docs/data/transfer.md. 경로는 cutplan_agent.config 의 ROOT (기본 레포 루트) 기준이다.
"""

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from cutplan_agent.config import ROOT

MANIFESTS = Path(__file__).resolve().parent / "data_manifests"


@dataclass(frozen=True)
class Dataset:
    path: str  # ROOT 기준
    manifest: str  # data_manifests/ 안의 파일 이름
    how: str  # 없을 때 할 일
    skip: tuple[str, ...] = ()  # 비교하지 않는 파일 (top 기준 경로)


DATASETS = (
    Dataset(
        "data_v3/synthetic",
        "data_v3_synthetic.sha256",
        "옮긴다. 생성기가 없어 다시 만들 수 없다",
    ),
    Dataset(
        "data_v3/generated",
        "data_v3_generated.sha256",
        "만든다: scripts/build_synthetic.py",
        ("compare.md",),  # --compare 를 줄 때만 생긴다
    ),
    Dataset("tests/fixtures", "tests_fixtures.sha256", "옮긴다"),
    Dataset(
        "data_v3/20261027example",
        "data_v3_20261027example.digest",
        "옮긴다. 회사 담당자가 그린 시험 도면 3건 (docs/data/transfer.md)",
    ),
    Dataset("Data", "Data.digest", "옮긴다"),
    Dataset("test_data", "test_data.digest", "옮긴다"),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _files(top: Path) -> list[Path]:
    # 심볼릭 링크로 둔 폴더도 따라간다. 파이썬 캐시는 데이터가 아니다
    return sorted(
        p
        for p in top.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(top).parts
    )


def _per_file(ds: Dataset) -> dict[str, str]:
    top = ROOT / ds.path
    return {
        f"{ds.path}/{p.relative_to(top).as_posix()}": _sha256(p)
        for p in _files(top)
        if p.relative_to(top).as_posix() not in ds.skip
    }


def _digest(ds: Dataset) -> dict[str, str]:
    top = ROOT / ds.path
    files = _files(top)
    total = hashlib.sha256()
    size = 0
    for p in files:
        total.update(f"{p.relative_to(top).as_posix()}\0{_sha256(p)}\n".encode())
        size += p.stat().st_size
    return {"files": str(len(files)), "bytes": str(size), "sha256": total.hexdigest()}


def _measure(ds: Dataset) -> dict[str, str]:
    return _digest(ds) if ds.manifest.endswith(".digest") else _per_file(ds)


def _read(manifest: Path) -> dict[str, str]:
    out = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if manifest.suffix == ".digest":
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
        else:
            digest, path = line.split(None, 1)
            out[path.strip()] = digest
    return out


def _write(ds: Dataset, measured: dict[str, str]) -> None:
    MANIFESTS.mkdir(exist_ok=True)
    if ds.manifest.endswith(".digest"):
        lines = [f"{k} = {v}" for k, v in measured.items()]
    else:
        lines = [f"{digest}  {path}" for path, digest in measured.items()]
    (MANIFESTS / ds.manifest).write_text("\n".join(lines) + "\n", encoding="utf-8")


def check(ds: Dataset) -> tuple[str, str]:
    top = ROOT / ds.path
    if not top.is_dir():
        return "없음", ds.how
    measured = _measure(ds)
    manifest = MANIFESTS / ds.manifest
    if not manifest.exists():
        shown = measured.get("files", str(len(measured)))
        return (
            "기준 없음",
            f"파일 {shown}개. 원본 쪽에서 --write {ds.path} 로 기준을 만든다",
        )
    expected = _read(manifest)
    if measured == expected:
        return "OK", f"파일 {measured.get('files', len(measured))}개 일치"
    if manifest.suffix == ".digest":
        diff = [f"{k} {expected.get(k)} → {measured.get(k)}" for k in expected]
        return "다름", "; ".join(diff)
    missing = sorted(set(expected) - set(measured))
    extra = sorted(set(measured) - set(expected))
    changed = sorted(
        k for k in set(expected) & set(measured) if expected[k] != measured[k]
    )
    parts = [
        f"{name} {len(items)}개 (예: {items[0]})"
        for name, items in (("빠짐", missing), ("추가", extra), ("내용 다름", changed))
        if items
    ]
    return "다름", "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument(
        "--write",
        metavar="PATH",
        choices=[ds.path for ds in DATASETS],
        help="이 데이터의 기준 파일을 지금 있는 파일로 다시 쓴다",
    )
    args = parser.parse_args(argv)
    if args.write:
        ds = next(ds for ds in DATASETS if ds.path == args.write)
        if not (ROOT / ds.path).is_dir():
            parser.error(f"{ROOT / ds.path} 가 없다")
        _write(ds, _measure(ds))
        print(f"wrote {MANIFESTS / ds.manifest}")
        return 0
    bad = False
    print(f"ROOT = {ROOT}")
    for ds in DATASETS:
        status, detail = check(ds)
        bad |= status == "다름"
        print(f"{status:6} {ds.path:24} {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
