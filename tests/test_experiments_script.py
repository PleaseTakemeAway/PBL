"""Exercise the launcher with fake servers; no GPU or network is used."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parents[1] / "experiments.sh"


class ExperimentsScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("CUTPLAN_", "VLLM_"))
            and name not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        }
        self.env["CUTPLAN_TEST_DIRECTORY"] = str(self.directory)
        self.env["CUTPLAN_PYTHON"] = str(
            self.executable(
                "python-capture",
                """
import json, os, pathlib, sys
keys = ["PROVIDER", "MODEL", "BASE_URL", "OUTPUT_FORMAT", "API_KEY"]
config = {role: {key: os.environ.get("CUTPLAN_" + role + "_" + key) for key in keys}
          for role in ("OCR", "REASON")}
pathlib.Path(os.environ["CUTPLAN_TEST_DIRECTORY"], "main.json").write_text(
    json.dumps({"config": config, "argv": sys.argv[1:]}))
""",
            )
        )
        self.env["CUTPLAN_VLLM_BIN"] = str(
            self.executable(
                "vllm-fake",
                """
import json, os, pathlib, signal, sys, time
root = pathlib.Path(os.environ["CUTPLAN_TEST_DIRECTORY"])
port = sys.argv[sys.argv.index("--port") + 1]
record = {"argv": sys.argv[1:], "gpu": os.environ["CUDA_VISIBLE_DEVICES"],
          "timeout": os.environ["VLLM_ENGINE_READY_TIMEOUT_S"]}
(root / (port + ".json")).write_text(json.dumps(record))
if os.environ.get("CUTPLAN_TEST_FAIL_PORT") == port:
    print("simulated engine startup failure", flush=True)
    sys.exit(1)
(root / (port + ".ready")).touch()
signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
try:
    for _ in range(1000):
        time.sleep(0.01)
finally:
    (root / (port + ".stopped")).touch()
""",
            )
        )
        self.executable(
            "curl",
            """
import os, pathlib, sys
from urllib.parse import urlsplit
url = next(arg for arg in sys.argv if arg.startswith("http"))
port = urlsplit(url).port
sys.exit(0 if pathlib.Path(os.environ["CUTPLAN_TEST_DIRECTORY"], str(port) + ".ready").exists() else 7)
""",
        )
        self.env["PATH"] = str(self.directory) + os.pathsep + self.env["PATH"]
        self.env["CUTPLAN_BATCH_OUTPUT"] = str(self.directory / "output")
        self.env["CUTPLAN_VLLM_STARTUP_TIMEOUT"] = "10"

    def executable(self, name, source):
        path = self.directory / name
        path.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=self.directory,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def captured(self):
        return json.loads((self.directory / "main.json").read_text())

    def test_unset_gpu_environment_has_defaults_and_dry_run_does_not_start_servers(
        self,
    ):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GPUs=0", result.stdout)
        self.assertIn("GPUs=1", result.stdout)
        self.assertIn("Qwen/Qwen3.6-27B", result.stdout)
        self.assertFalse((self.directory / "main.json").exists())
        self.assertFalse((self.directory / "output").exists())

    def test_default_local_servers_receive_limits_and_stop_on_exit(self):
        result = self.run_script("sample.dxf")
        self.assertEqual(result.returncode, 0, result.stderr)
        for port, gpu in (("8000", "0"), ("8001", "1")):
            record = json.loads((self.directory / f"{port}.json").read_text())
            self.assertEqual(record["gpu"], gpu)
            self.assertEqual(record["timeout"], "10")
            self.assertIn("--max-num-seqs=16", record["argv"])
            if port == "8001":
                self.assertIn(
                    "--structured-outputs-config.backend=xgrammar", record["argv"]
                )
            else:
                self.assertNotIn(
                    "--structured-outputs-config.backend=xgrammar", record["argv"]
                )
            self.assertTrue((self.directory / f"{port}.stopped").exists())
        self.assertEqual(
            self.captured()["config"]["REASON"]["BASE_URL"], "http://127.0.0.1:8001/v1"
        )
        self.assertEqual(
            self.captured()["config"]["REASON"]["OUTPUT_FORMAT"], "json_schema"
        )
        self.assertEqual(self.captured()["config"]["OCR"]["OUTPUT_FORMAT"], "raw")

    def test_api_roles_need_no_local_server_and_output_flags_are_consumed(self):
        result = self.run_script(
            "--ocr-mode",
            "api",
            "--ocr-model",
            "ocr-remote",
            "--ocr-base-url",
            "https://ocr.example/v1",
            "--reason-mode",
            "api",
            "--reason-model",
            "reason-remote",
            "--reason-base-url",
            "https://reason.example/v1",
            "--ocr-output-format",
            "json_schema",
            "--reason-output-format=json_schema",
            "--overwrite",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        capture = self.captured()
        self.assertEqual(capture["config"]["OCR"]["OUTPUT_FORMAT"], "raw")
        self.assertEqual(capture["config"]["REASON"]["OUTPUT_FORMAT"], "json_schema")
        self.assertNotIn("--ocr-output-format", capture["argv"])
        self.assertNotIn("--reason-output-format", capture["argv"])
        self.assertIn(str(SCRIPT.parent / "../data_v3/synthetic"), capture["argv"])
        self.assertFalse((self.directory / "8000.json").exists())
        self.assertFalse((self.directory / "8001.json").exists())

    def test_legacy_local_launcher_uses_xgrammar_and_environment_not_main_format_flags(
        self,
    ):
        # The fake server records this variable; the legacy launcher uses its
        # own startup timeout rather than exporting vLLM's newer timeout.
        self.env["VLLM_ENGINE_READY_TIMEOUT_S"] = "10"
        result = subprocess.run(
            ["bash", str(SCRIPT.with_name("experiments_local.sh")), "sample.dxf"],
            cwd=self.directory,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        capture = self.captured()
        self.assertEqual(capture["config"]["OCR"]["OUTPUT_FORMAT"], "raw")
        self.assertEqual(capture["config"]["REASON"]["OUTPUT_FORMAT"], "json_schema")
        self.assertNotIn("--ocr-output-format", capture["argv"])
        self.assertNotIn("--reason-output-format", capture["argv"])
        record = json.loads((self.directory / "8001.json").read_text())
        self.assertIn("--structured-outputs-config.backend=xgrammar", record["argv"])

    def test_local_ocr_api_reasoning_and_explicit_key(self):
        self.env["TEST_REASON_KEY"] = "test-key-only"
        result = self.run_script(
            "--reason-mode",
            "api",
            "--reason-provider",
            "anthropic",
            "--reason-model",
            "test-claude",
            "--reason-api-key-env",
            "TEST_REASON_KEY",
            "sample.dxf",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.captured()["config"]
        self.assertEqual(config["OCR"]["PROVIDER"], "openai")
        self.assertEqual(config["REASON"]["PROVIDER"], "anthropic")
        self.assertEqual(config["REASON"]["API_KEY"], "test-key-only")
        self.assertNotIn("test-key-only", result.stdout + result.stderr)
        self.assertTrue((self.directory / "8000.stopped").exists())
        self.assertFalse((self.directory / "8001.json").exists())

    def test_api_ocr_local_reasoning_with_multiple_gpus_and_last_argument_override(
        self,
    ):
        self.env["CUTPLAN_REASON_GPU"] = "7"
        result = self.run_script(
            "--ocr-mode=api",
            "--ocr-model=remote-ocr",
            "--ocr-base-url=https://ocr.example/v1",
            "--reason-gpu",
            "4,5",
            "--reason-vllm-arg=--max-num-seqs=8",
            "sample.dxf",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.directory / "8001.json").read_text())
        self.assertEqual(record["gpu"], "4,5")
        self.assertEqual(
            record["argv"][record["argv"].index("--tensor-parallel-size") + 1], "2"
        )
        self.assertEqual(record["argv"][-1], "--max-num-seqs=8")
        self.assertTrue((self.directory / "8001.stopped").exists())
        self.assertFalse((self.directory / "8000.json").exists())

    def test_overlap_and_bad_options_fail_before_starting_servers(self):
        for args in (
            ("--ocr-gpu", "4", "--reason-gpu", "4"),
            ("--ocr-output-format", "invalid"),
            ("----reason-vllm-arg=--max-model-len=16384",),
            ("--reason-gpu",),
            ("--reason-gpu", "4,4,"),
        ):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse((self.directory / "8000.json").exists())

    def test_shared_gpu_override_is_explicit(self):
        result = self.run_script(
            "--dry-run", "--ocr-gpu", "4", "--reason-gpu", "4", "--allow-shared-gpus"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reason_startup_failure_stops_ocr_and_never_runs_main(self):
        self.env["CUTPLAN_TEST_FAIL_PORT"] = "8001"
        result = self.run_script("sample.dxf")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("reason vLLM exited during startup", result.stderr)
        self.assertTrue((self.directory / "8000.stopped").exists())
        self.assertFalse((self.directory / "main.json").exists())


if __name__ == "__main__":
    unittest.main()
