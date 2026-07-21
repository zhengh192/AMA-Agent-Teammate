from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PythonTransformProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1, max_length=30_000)


class PythonSandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PythonSandboxRequest:
    code: str
    datasets: dict[str, list[dict[str, Any]]]
    timeout_seconds: float = 15


@dataclass(frozen=True, slots=True)
class PythonSandboxResult:
    output: dict[str, Any]
    stdout: str


class PythonSandbox(Protocol):
    async def execute(self, request: PythonSandboxRequest) -> PythonSandboxResult: ...


class DisabledPythonSandbox:
    async def execute(self, request: PythonSandboxRequest) -> PythonSandboxResult:
        del request
        raise PythonSandboxUnavailable(
            "Generated Python is disabled until an isolated sandbox runtime is configured."
        )


class DockerPythonSandbox:
    """Runs generated Python in a disposable, no-network container, never in the API process."""

    def __init__(
        self,
        *,
        image: str,
        timeout_seconds: float = 15,
        memory_mb: int = 256,
        cpus: float = 1.0,
        pids_limit: int = 64,
    ) -> None:
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.pids_limit = pids_limit

    async def execute(self, request: PythonSandboxRequest) -> PythonSandboxResult:
        if len(request.code) > 30_000:
            raise ValueError("Sandbox code exceeds the bounded size limit.")
        payload = json.dumps(request.datasets, ensure_ascii=False, default=str).encode("utf-8")
        if len(payload) > 5_000_000:
            raise ValueError("Sandbox input exceeds the bounded dataset limit.")

        with tempfile.TemporaryDirectory(prefix="ama-python-sandbox-") as temp:
            root = Path(temp)
            (root / "input.json").write_bytes(payload)
            (root / "analysis.py").write_text(
                _sandbox_wrapper(request.code),
                encoding="utf-8",
            )
            process = await asyncio.create_subprocess_exec(
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--memory",
                f"{self.memory_mb}m",
                "--cpus",
                str(self.cpus),
                "--pids-limit",
                str(self.pids_limit),
                "--user",
                "65534:65534",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=32m",
                "--mount",
                f"type=bind,source={root},target=/workspace,readonly",
                "--workdir",
                "/workspace",
                self.image,
                "python",
                "-I",
                "-B",
                "analysis.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=min(request.timeout_seconds, self.timeout_seconds),
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise PythonSandboxUnavailable("Sandbox execution timed out.") from None
            if process.returncode != 0:
                safe_error = stderr.decode("utf-8", errors="replace")[-1_000:]
                raise PythonSandboxUnavailable(
                    f"Sandbox execution failed: {safe_error or 'unknown error'}"
                )
            text = stdout.decode("utf-8", errors="replace")
            marker = "AMA_RESULT="
            result_line = next(
                (line for line in reversed(text.splitlines()) if line.startswith(marker)),
                None,
            )
            if result_line is None:
                raise PythonSandboxUnavailable("Sandbox did not return a structured result.")
            output = json.loads(result_line.removeprefix(marker))
            if not isinstance(output, dict):
                raise PythonSandboxUnavailable("Sandbox result must be a JSON object.")
            return PythonSandboxResult(output=output, stdout=text[-4_000:])


def _sandbox_wrapper(code: str) -> str:
    return (
        "import json\n"
        "from pathlib import Path\n"
        'datasets = json.loads(Path("/workspace/input.json").read_text(encoding="utf-8"))\n'
        "result = None\n"
        f"{code}\n"
        "if not isinstance(result, dict):\n"
        '    raise TypeError("Generated analysis must assign a JSON-compatible dict to result")\n'
        'print("AMA_RESULT=" + json.dumps(result, ensure_ascii=False, default=str))\n'
    )
