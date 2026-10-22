"""The orchestrator loop (reader/orchestrator.py), driven by a scripted model."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_reader_tools import no_models, sheet

from cutplan_agent.reader.orchestrator import Call, Log, OpenAISchema, Turn, orchestrate
from cutplan_agent.reader.tools import ReaderTools


class Scripted:
    """A backend that replays fixed turns and keeps the tool results it is sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = []
        self.results = []

    def start(self, system, command, tools):
        self.messages = [{"system": system, "command": command}]

    def next(self):
        return self.turns.pop(0)

    def add_results(self, results):
        self.results.extend(result for _, result in results)


class OrchestrateTest(unittest.TestCase):
    def test_loop_runs_calls_until_an_answer_and_logs_them(self):
        with TemporaryDirectory() as tmp:
            dxf = sheet(tmp)
            tools = ReaderTools(Path(tmp) / "out", no_models(), Path(tmp) / "in")
            backend = Scripted(
                [
                    Turn("", [Call("1", "list_drawings", {})]),
                    Turn(
                        "run everything",
                        [
                            Call(
                                "2",
                                "run_stages",
                                {"work": "sheet", "drawing": str(dxf)},
                            )
                        ],
                    ),
                    Turn("", [Call("3", "run_views", "{not json")]),
                    Turn("done", []),
                ]
            )
            log = Log(Path(tmp) / "log")
            answer = orchestrate("판독해줘", backend, tools, log, echo=lambda _: None)
            self.assertEqual(answer, "done")
            self.assertEqual(backend.results[1]["status"], "done")
            self.assertIn("not valid JSON", backend.results[2]["error"])
            lines = log.trajectory.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4 + 3)  # 4 model turns, 3 tool calls
            self.assertTrue((log.folder / "messages.json").is_file())

    def test_schema_mode_lists_every_tool_and_finish(self):
        tools = ReaderTools("out", no_models())
        backend = OpenAISchema("m", "http://127.0.0.1:1/v1")
        backend.start("system", "command", list(tools.tools.values()))
        names = [o["properties"]["tool"]["const"] for o in backend.schema()["anyOf"]]
        self.assertEqual(names, [*tools.tools, "finish"])
        self.assertIn("run_confirm", backend.messages[0]["content"])
        body = backend.body()
        self.assertNotIn("tools", body)
        self.assertEqual(body["response_format"]["type"], "json_schema")


if __name__ == "__main__":
    unittest.main()
