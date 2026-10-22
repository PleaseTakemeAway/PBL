"""Compare actual OCR outputs without changing the reconstruction pipeline.

Example (use an existing server):
  python scripts/verify_ocr_output.py --base-url http://127.0.0.1:8000/v1 \
    --image output/run/sample/analysis/title_block.png --output-dir output/ocr_probe

--start-vllm temporarily starts ONE server on --port and stops its own process
group in finally. API responses, prompts and untruncated content are preserved.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests

from cutplan_agent.reader.vlm import extract_json
from cutplan_agent.reader.vlm_output import normalize_response, output_instructions

ROOT = Path(__file__).resolve().parents[1] / "cutplan_agent" / "reader"


def title_prompt() -> str:
    """Read the current production prompt verbatim, without importing adapters."""
    tree = ast.parse((ROOT / "dxf_adapter.py").read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TITLE_BLOCK_PROMPT"
            for target in node.targets
        )
    )
    return ast.literal_eval(assignment.value)


@contextmanager
def endpoint(args):
    if not args.start_vllm:
        yield args.base_url.rstrip("/")
        return
    address = f"http://127.0.0.1:{args.port}"
    try:
        requests.get(address + "/health", timeout=2)
    except requests.ConnectionError:
        pass
    else:
        raise RuntimeError(f"port {args.port} already has a server")
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=args.gpu,
        VLLM_ENGINE_READY_TIMEOUT_S=str(args.startup_timeout),
        TRITON_ALLOW_NON_CONSTEXPR_GLOBALS="1",
    )
    command = [
        args.vllm_bin,
        "serve",
        args.model,
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--max-model-len",
        "8192",
        "--max-num-seqs",
        "1",
        "--gpu-memory-utilization",
        "0.20",
    ]
    process = None
    with (args.output_dir / "server.log").open("w") as stream:
        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + args.startup_timeout
            notice = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"probe vLLM exited ({process.returncode}); inspect server.log"
                    )
                try:
                    ready = requests.get(address + "/health", timeout=2).ok
                except requests.RequestException:
                    ready = False
                if ready:
                    print(f"Probe server ready: {address}", flush=True)
                    yield address + "/v1"
                    return
                if time.monotonic() >= notice:
                    print("Waiting for probe server; inspect server.log", flush=True)
                    notice = time.monotonic() + 30
                time.sleep(1)
            raise TimeoutError("probe vLLM startup timed out")
        finally:
            if process is not None:
                # start_new_session=True makes this group exclusive to our test.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                print("Probe server stopped.", flush=True)


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def probe(args, base_url):
    image_data = args.image.read_bytes()
    mime = "image/png" if args.image.suffix.lower() == ".png" else "image/jpeg"
    image = {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime};base64," + base64.b64encode(image_data).decode()
        },
    }
    variants = [
        (
            "current_schema_text_first",
            title_prompt() + output_instructions("ocr", "title_block"),
            False,
            {},
        ),
        (
            "short_fields_text_first",
            "Read the title block. Return only a JSON object with drawing_no, "
            "part_name, material, thickness_mm, scale, units, projection, weight_kg. "
            "Use a ratio string for scale and null for unknown values.",
            False,
            {},
        ),
        ("free_ocr_text_first", "Free OCR.", False, {}),
        ("free_ocr_image_first", "Free OCR.", True, {}),
        (
            "free_ocr_image_first_repetition_penalty",
            "Free OCR.",
            True,
            {"repetition_penalty": 1.1},
        ),
    ]
    headers = {}
    key = os.getenv("CUTPLAN_OCR_API_KEY", "")
    if key:
        headers["Authorization"] = "Bearer " + key
    models = requests.get(base_url + "/models", headers=headers, timeout=10)
    models.raise_for_status()
    (args.output_dir / "models.json").write_text(json.dumps(models.json(), indent=2))
    results = []
    for name, prompt, image_first, extra in variants:
        text = {"type": "text", "text": prompt}
        content = [image, text] if image_first else [text, image]
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 1500,
            "temperature": 0.0,
            **extra,
        }
        (args.output_dir / f"{name}.prompt.txt").write_text(prompt)
        start = time.monotonic()
        record = {"variant": name, "image_first": image_first}
        try:
            response = requests.post(
                base_url + "/chat/completions", json=body, headers=headers, timeout=180
            )
            record["http_status"] = response.status_code
            (args.output_dir / f"{name}.http.json").write_text(response.text)
            response.raise_for_status()
            wire = response.json()
            choice = wire["choices"][0]
            raw = choice["message"].get("content") or ""
            (args.output_dir / f"{name}.raw.txt").write_text(raw)
            record.update(
                raw_chars=len(raw),
                finish_reason=choice.get("finish_reason"),
                usage=wire.get("usage"),
                preview=raw[:800],
                title_block_repetitions=raw.count("Title Block"),
                matched_text=[
                    word for word in args.expect if compact(word) in compact(raw)
                ],
            )
            try:
                parsed = extract_json(raw)
                normalized, legacy = normalize_response(parsed, "ocr", "title_block")
                record.update(
                    title_block_valid=True, normalized=normalized, legacy=legacy
                )
            except (ValueError, TypeError) as exc:
                record.update(title_block_valid=False, validation_error=str(exc))
        except requests.RequestException as exc:
            record["error"] = str(exc)
        record["seconds"] = round(time.monotonic() - start, 2)
        results.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        report = {
            "model": args.model,
            "image": str(args.image.resolve()),
            "image_sha256": hashlib.sha256(image_data).hexdigest(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "expected_text": args.expect,
            "results": results,
        }
        (args.output_dir / "results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-ai/DeepSeek-OCR-2")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--start-vllm", action="store_true")
    parser.add_argument("--vllm-bin", default="vllm")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--startup-timeout", type=int, default=600)
    parser.add_argument("--expect", action="append", default=[])
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("image does not exist")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if (args.output_dir / "results.json").exists():
        parser.error("use a new output directory to preserve earlier results")
    with endpoint(args) as base_url:
        probe(args, base_url)
    print(f"Results: {args.output_dir / 'results.json'}")


if __name__ == "__main__":
    main()
