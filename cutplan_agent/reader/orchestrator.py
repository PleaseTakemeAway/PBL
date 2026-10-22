"""A model reads one command in plain language and runs the reader stages by tool calling.

PYTHONPATH=. python cutplan_agent/reader/orchestrator.py "cone_0019 를 전개도까지 판독해줘"

The orchestrating model only chooses which tool to call next; the stages do the work and
their OCR/reasoning models are set as in stages/run.py (--ocr-*, --reason-*, CUTPLAN_*).
The same loop runs three ways, so a local model and Claude can be compared on one harness:

  --provider openai --tool-mode native   OpenAI-compatible `tools` (vLLM needs
                                         --enable-auto-tool-choice --tool-call-parser)
  --provider openai --tool-mode schema   every turn is one JSON object {thought, tool,
                                         arguments} under a JSON schema (works on any vLLM
                                         with structured outputs; no tool parser needed)
  --provider anthropic                   Claude tool use (ANTHROPIC_API_KEY)

Orchestrator model: --model/--base-url, or CUTPLAN_ORCH_{PROVIDER,MODEL,BASE_URL,API_KEY};
for openai it falls back to the reasoning model (CUTPLAN_REASON_*), so after
`. runs/vllm/reason.env` the stages and the orchestrator share one local server.

Every run writes <output-dir>/orchestrator/<time>/: command.json (settings and tool list),
trajectory.jsonl (one line per model turn and per tool call) and messages.json (the
conversation as the provider saw it).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cutplan_agent.reader.stages.workspace import STAGES, write_json
from cutplan_agent.reader.tools import ReaderTools, Tool
from cutplan_agent.reader.vlm import make_clients

SYSTEM = f"""너는 DXF 도면 판독 파이프라인을 운영한다. 사용자의 요청을 읽고 tool 을 불러 일을 한 뒤, 무엇을 했고 결과가 어떤지 한국어로 짧게 보고한다.

판독은 13단계이고 순서가 정해져 있다: {" → ".join(STAGES)}.
- 도면 1장마다 작업 폴더(work)가 하나 있다. list_drawings 가 도면 경로(drawing)와 work 를 알려준다.
- 각 단계는 앞 단계가 work 에 남긴 파일만 읽는다. 앞 단계가 없거나 failed 이면 not_ready 가 돌아온다.
- 한 단계를 다시 돌리면 그 뒤 단계 파일은 지워지므로 뒤 단계도 다시 돌려야 한다.
- 모델을 쓰는 단계는 title_ocr(OCR), title_fields, view_labels, unfold_params, confirm(추론) 이다. 모델 호출이 실패해도 단계는 done 이 되고 model_calls 의 ok=false 와 error 로 드러난다. 이때 그 단계의 결과는 폴백 값이다.
- 네스팅 도면은 document 부터 skipped 가 정상이다. view_labels 가 3D 복원 불가로 판단하면 reconstruct 부터 skipped 다.
- 처음부터 끝까지 그대로 돌리면 될 때는 run_stages 한 번으로 돌린다. 중간 결과를 보고 판단해야 하면 run_<단계> 를 하나씩 부른다.
- 이미 돌린 단계가 있으면 stage_status 로 확인하고 필요한 단계부터 돌린다.
- 길이·치수를 직접 계산하지 않는다. 결과 값은 tool 결과에 있는 것만 인용한다.
- 요청에 없는 일은 하지 않는다. 정답 파일(label.json)은 읽지 않는다.

보고에는 돌린 단계와 상태(done/skipped/failed), 핵심 결과(형상, 전개 블랭크 등), review 항목이나 모델 오류가 있으면 그것을 적는다."""

SCHEMA_RULES = """

tool 은 아래 형식의 JSON 객체 하나로 부른다. 응답마다 tool 을 정확히 하나 부른다.
{"thought": "<다음에 무엇을 왜 하는지 한두 문장>", "tool": "<tool 이름>", "arguments": {...}}
일이 끝나면 tool 로 finish 를 부르고 arguments.answer 에 보고를 쓴다.

tool 목록:
"""


@dataclass
class Call:
    id: str
    name: str
    arguments: Any  # parsed JSON, or the raw string when it was not valid JSON


@dataclass
class Turn:
    text: str
    calls: list[Call]
    stop: str | None = None
    usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------- backends
class OpenAITools:
    """OpenAI-compatible chat completions with `tools` (vLLM, OpenAI, ...)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        thinking: str = "off",
        timeout: float = 600,
    ):
        self.model, self.base_url, self.api_key = model, base_url.rstrip("/"), api_key
        self.max_tokens, self.temperature, self.timeout = (
            max_tokens,
            temperature,
            timeout,
        )
        self.thinking = thinking
        self.messages: list[dict] = []

    def start(self, system: str, command: str, tools: list[Tool]) -> None:
        self.tools = tools
        self.messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": command},
        ]

    def body(self) -> dict:
        body = {
            "model": self.model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in self.tools
            ],
            "tool_choice": "auto",
        }
        if self.thinking != "default":
            # Qwen3 chat templates (vLLM): thinking on or off for this request.
            body["chat_template_kwargs"] = {"enable_thinking": self.thinking == "on"}
        return body

    def post(self, body: dict) -> dict:
        import requests

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        r = requests.post(
            self.base_url + "/chat/completions",
            json=body,
            headers=headers,
            timeout=self.timeout,
        )
        if not r.ok:
            hint = ""
            if "tool-call-parser" in r.text:
                hint = (
                    "\nthe server has no tool parser: restart it with "
                    "--enable-auto-tool-choice --tool-call-parser <parser>, "
                    "or use --tool-mode schema"
                )
            raise RuntimeError(f"{r.status_code}: {r.text[:1000]}{hint}")
        return r.json()

    def next(self) -> Turn:
        data = self.post(self.body())
        choice = data["choices"][0]
        message = choice["message"]
        calls = []
        for c in message.get("tool_calls") or []:
            raw = c["function"].get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                arguments = raw
            calls.append(Call(c["id"], c["function"]["name"], arguments))
        kept = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            kept["tool_calls"] = message["tool_calls"]
        self.messages.append(kept)
        return Turn(
            message.get("content") or "",
            calls,
            choice.get("finish_reason"),
            data.get("usage") or {},
        )

    def add_results(self, results: list[tuple[Call, dict]]) -> None:
        for call, result in results:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )


class OpenAISchema(OpenAITools):
    """No `tools` field: the reply is one JSON object constrained by a JSON schema that
    lists every tool with its arguments, plus `finish`. The tool descriptions go into the
    system prompt, because the model never sees a schema it is decoded with."""

    def start(self, system: str, command: str, tools: list[Tool]) -> None:
        listing = "\n".join(
            f"- {t.name}({json.dumps(t.parameters['properties'], ensure_ascii=False)})"
            f": {t.description}"
            for t in tools
        )
        listing += '\n- finish({"answer": {"type": "string"}}): 일을 끝내고 보고한다.'
        super().start(system + SCHEMA_RULES + listing, command, tools)
        self.count = 0

    def schema(self) -> dict:
        options = [(t.name, t.parameters) for t in self.tools] + [
            (
                "finish",
                {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            )
        ]
        return {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "thought": {"type": "string"},
                        "tool": {"const": name},
                        "arguments": parameters,
                    },
                    "required": ["thought", "tool", "arguments"],
                    "additionalProperties": False,
                }
                for name, parameters in options
            ]
        }

    def body(self) -> dict:
        body = super().body()
        del body["tools"], body["tool_choice"]
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tool_call",
                "strict": True,
                "schema": self.schema(),
            },
        }
        return body

    def next(self) -> Turn:
        data = self.post(self.body())
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        self.messages.append({"role": "assistant", "content": content})
        usage = data.get("usage") or {}
        try:
            reply = json.loads(content)
        except json.JSONDecodeError:
            # Cut off by max_tokens: send the error back as if it were a tool result.
            self.count += 1
            bad = Call(f"call_{self.count}", "invalid_reply", content)
            return Turn("", [bad], choice.get("finish_reason"), usage)
        if reply["tool"] == "finish":
            return Turn(reply["arguments"]["answer"], [], "finish", usage)
        self.count += 1
        call = Call(f"call_{self.count}", reply["tool"], reply["arguments"])
        return Turn(
            reply.get("thought", ""), [call], choice.get("finish_reason"), usage
        )

    def add_results(self, results: list[tuple[Call, dict]]) -> None:
        for call, result in results:
            self.messages.append(
                {
                    "role": "user",
                    "content": f"[{call.name} 결과]\n"
                    + json.dumps(result, ensure_ascii=False),
                }
            )


class AnthropicTools:
    """Claude tool use with a hand-written loop, the same loop as the OpenAI backends."""

    def __init__(self, model: str, *, max_tokens: int = 16000, effort: str = "medium"):
        from cutplan_agent.client import make_client

        self.client = make_client()
        self.model, self.max_tokens, self.effort = model, max_tokens, effort
        self.messages: list[dict] = []

    def start(self, system: str, command: str, tools: list[Tool]) -> None:
        self.system = system
        self.tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        self.messages = [{"role": "user", "content": command}]

    def next(self) -> Turn:
        # fallbacks: a request the model declines is retried on a fallback model.
        response = self.client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system,
            tools=self.tools,
            output_config={"effort": self.effort},
            messages=self.messages,
        )
        content = [block.to_dict() for block in response.content]
        self.messages.append({"role": "assistant", "content": content})
        text = "\n".join(b["text"] for b in content if b["type"] == "text")
        calls = [
            Call(b["id"], b["name"], b["input"])
            for b in content
            if b["type"] == "tool_use"
        ]
        return Turn(text, calls, response.stop_reason, response.usage.to_dict())

    def add_results(self, results: list[tuple[Call, dict]]) -> None:
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                        "is_error": "error" in result,
                    }
                    for call, result in results
                ],
            }
        )


# ---------------------------------------------------------------------- loop
class Log:
    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.trajectory = folder / "trajectory.jsonl"

    def write(self, entry: dict) -> None:
        with self.trajectory.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def orchestrate(
    command: str,
    backend,
    tools: ReaderTools,
    log: Log,
    *,
    max_turns: int = 40,
    echo=print,
) -> str:
    """Ask, run the tools the model calls, send the results back; repeat until the model
    answers without a tool call. Returns the answer."""
    backend.start(SYSTEM, command, list(tools.tools.values()))
    t0 = time.time()
    answer = f"(stopped after {max_turns} turns without an answer)"
    try:
        for turn in range(1, max_turns + 1):
            reply = backend.next()
            log.write(
                {
                    "turn": turn,
                    "seconds": round(time.time() - t0, 1),
                    "text": reply.text,
                    "calls": [vars(c) for c in reply.calls],
                    "stop": reply.stop,
                    "usage": reply.usage,
                }
            )
            if reply.text.strip() and reply.calls:
                echo(f"[{turn:02d}] {short(reply.text, 200)}")
            if not reply.calls:
                answer = reply.text
                break
            results = []
            for call in reply.calls:
                echo(f"[{turn:02d}] -> {call.name}({short(call.arguments)})")
                started = time.time()
                if call.name == "invalid_reply" or isinstance(call.arguments, str):
                    result = {
                        "error": "the reply was not valid JSON (too long?): "
                        + short(call.arguments, 300)
                    }
                else:
                    result = tools.call(call.name, call.arguments)
                log.write(
                    {
                        "turn": turn,
                        "tool": call.name,
                        "id": call.id,
                        "seconds": round(time.time() - started, 1),
                        "result": result,
                    }
                )
                echo(f"     <- {short(result)}")
                results.append((call, result))
            backend.add_results(results)
    finally:
        write_json(log.folder / "messages.json", backend.messages)
    return answer


# ---------------------------------------------------------------------- CLI
def make_backend(args: argparse.Namespace):
    provider = args.provider or os.getenv("CUTPLAN_ORCH_PROVIDER") or "openai"
    if provider == "anthropic":
        from cutplan_agent.config import MODEL  # also loads .env

        model = args.model or os.getenv("CUTPLAN_ORCH_MODEL") or MODEL
        return provider, model, AnthropicTools(model, effort=args.effort)
    model = (
        args.model
        or os.getenv("CUTPLAN_ORCH_MODEL")
        or os.getenv("CUTPLAN_REASON_MODEL")
    )
    base_url = (
        args.base_url
        or os.getenv("CUTPLAN_ORCH_BASE_URL")
        or os.getenv("CUTPLAN_REASON_BASE_URL")
    )
    if not model or not base_url:
        sys.exit(
            "set the orchestrator model: --model and --base-url, CUTPLAN_ORCH_*, or "
            "source runs/vllm/reason.env"
        )
    api_key = os.getenv("CUTPLAN_ORCH_API_KEY") or os.getenv(
        "CUTPLAN_REASON_API_KEY", ""
    )
    cls = OpenAISchema if args.tool_mode == "schema" else OpenAITools
    backend = cls(
        model,
        base_url,
        api_key,
        max_tokens=args.max_tokens,
        thinking=args.thinking,
    )
    return provider, model, backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", help="what to do, in plain language")
    parser.add_argument("--provider", choices=["openai", "anthropic"])
    parser.add_argument("--model", help="orchestrator model")
    parser.add_argument("--base-url", help="orchestrator endpoint (openai)")
    parser.add_argument("--tool-mode", choices=["native", "schema"], default="native")
    parser.add_argument(
        "--thinking",
        choices=["off", "on", "default"],
        default="off",
        help="openai: Qwen3 enable_thinking via chat_template_kwargs; default sends nothing",
    )
    parser.add_argument("--max-tokens", type=int, default=2048, help="openai, per turn")
    parser.add_argument(
        "--effort", choices=["low", "medium", "high", "xhigh", "max"], default="medium"
    )
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--input-dir", type=Path, default=Path("data_v3/synthetic"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/reader/agent"))
    for role in ("ocr", "reason"):
        parser.add_argument(
            f"--{role}-model", help=f"stage model, CUTPLAN_{role.upper()}_*"
        )
        parser.add_argument(f"--{role}-base-url")
        parser.add_argument(f"--{role}-provider", choices=["openai", "anthropic"])
    parser.add_argument(
        "--no-vlm", action="store_true", help="stages run without models"
    )
    args = parser.parse_args(argv)

    provider, model, backend = make_backend(args)
    clients = make_clients(
        disabled=args.no_vlm,
        ocr_model=args.ocr_model,
        reason_model=args.reason_model,
        ocr_base_url=args.ocr_base_url,
        reason_base_url=args.reason_base_url,
        ocr_provider=args.ocr_provider,
        reason_provider=args.reason_provider,
    )
    tools = ReaderTools(args.output_dir, clients, args.input_dir)
    log = Log(
        args.output_dir / "orchestrator" / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    write_json(
        log.folder / "command.json",
        {
            "command": args.command,
            "provider": provider,
            "model": model,
            "tool_mode": args.tool_mode if provider == "openai" else "native",
            "thinking": args.thinking if provider == "openai" else None,
            "effort": args.effort if provider == "anthropic" else None,
            "stage_models": {
                role: client.config.model or None
                for role, client in zip(("ocr", "reason"), clients)
            },
            "input_dir": str(args.input_dir),
            "output_dir": str(args.output_dir),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools.tools.values()
            ],
        },
    )
    print(f"[start] {provider} {model} -> {log.folder}", flush=True)
    try:
        answer = orchestrate(
            args.command, backend, tools, log, max_turns=args.max_turns
        )
    except Exception as exc:
        print(f"failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    write_json(log.folder / "answer.json", {"answer": answer})
    print("\n" + answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
