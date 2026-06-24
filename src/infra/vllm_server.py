"""vLLM Server Manager — launches vLLM as a local subprocess server.

Manages the lifecycle of a ``vllm serve`` process so that the rest of
the application can connect to it via the OpenAI-compatible endpoint
(through LiteLlm / ADK's ``LiteLlm`` wrapper).

Usage:
    from infra.vllm_server import VllmServer

    server = VllmServer()
    server.start()
    api_base = server.api_base  # "http://localhost:8000/v1"
    # ... use with LiteLlm(model="openai/qwen", api_base=api_base) ...
    server.stop()
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error
from typing import Any

from infra.logging import get_logger
from infra.settings import get_section

logger = get_logger(__name__)

_MODEL_TIERS = [
    (8, "Qwen/Qwen2.5-1.5B-Instruct"),
    (16, "Qwen/Qwen2.5-7B-Instruct"),
    (32, "Qwen/Qwen2.5-14B-Instruct"),
]

_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"

_POLL_INTERVAL = 2.0
_STARTUP_TIMEOUT = 300.0


def _select_model_by_ram() -> str:
    """Pick a model based on available system RAM."""
    import psutil  # type: ignore

    ram_gb = psutil.virtual_memory().total / (1024**3)
    logger.info(f"System RAM: {ram_gb:.1f} GB")

    for threshold, model in _MODEL_TIERS:
        if ram_gb <= threshold:
            logger.info(f"Selected model for {ram_gb:.0f}GB RAM: {model}")
            return model

    logger.info(f"Selected model for {ram_gb:.0f}GB RAM: {_DEFAULT_MODEL}")
    return _DEFAULT_MODEL


def _port_is_open(host: str, port: int) -> bool:
    """Check if a TCP port is already listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


class VllmServer:
    """Manages a local vLLM server subprocess.

    The server is started lazily on the first call to :meth:`start` and
    is automatically cleaned up on interpreter exit.
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._config = get_section("llm").get("vllm", {})
        self._model_name: str = ""
        self._lock = threading.Lock()
        atexit.register(self.stop)

    @property
    def api_base(self) -> str:
        host = self._config.get("host", "localhost")
        port = self._config.get("port", 8000)
        return f"http://{host}:{port}/v1"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _build_args(self) -> list[str]:
        """Build the ``vllm serve`` command-line arguments."""
        configured_model = self._config.get("model", "auto")
        model = (
            _select_model_by_ram()
            if configured_model == "auto"
            else configured_model
        )
        self._model_name = model

        host = self._config.get("host", "localhost")
        port = self._config.get("port", 8000)

        args = [
            "vllm",
            "serve",
            model,
            "--host",
            str(host),
            "--port",
            str(port),
        ]

        max_model_len = self._config.get("max_model_len")
        if max_model_len is not None:
            args.extend(["--max-model-len", str(max_model_len)])

        gpu_mem = self._config.get("gpu_memory_utilization")
        if gpu_mem is not None:
            args.extend(["--gpu-memory-utilization", str(gpu_mem)])

        tp = self._config.get("tensor_parallel")
        if tp is not None:
            args.extend(["--tensor-parallel-size", str(tp)])

        if self._config.get("enable_auto_tool_choice", True):
            args.append("--enable-auto-tool-choice")

        tool_parser = self._config.get("tool_call_parser")
        if tool_parser:
            args.extend(["--tool-call-parser", str(tool_parser)])

        trust_remote = self._config.get("trust_remote_code", True)
        if trust_remote:
            args.append("--trust-remote-code")

        return args

    def start(self) -> str:
        """Start the vLLM server subprocess.

        Returns:
            The ``api_base`` URL once the server is ready.

        Raises:
            RuntimeError: If the server fails to start or becomes ready.
        """
        with self._lock:
            if self._process is not None:
                logger.info("vLLM server already running")
                return self.api_base

            host = self._config.get("host", "localhost")
            port = self._config.get("port", 8000)

            if _port_is_open(host, port):
                logger.warning(
                    f"Port {port} is already in use — assuming external vLLM server"
                )
                return self.api_base

            args = self._build_args()
            logger.info(f"Starting vLLM server: {' '.join(args)}")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )

            logger.info(
                f"Waiting for vLLM server (PID {self._process.pid}) "
                f"to be ready at {self.api_base} ..."
            )

            ready = self._wait_for_ready(host, port)
            if not ready:
                self.stop()
                raise RuntimeError(
                    f"vLLM server did not become ready within "
                    f"{_STARTUP_TIMEOUT:.0f}s"
                )

            logger.info(f"vLLM server ready at {self.api_base}")
            return self.api_base

    def _wait_for_ready(self, host: str, port: int) -> bool:
        """Poll the /v1/models endpoint until the server responds."""
        url = f"http://{host}:{port}/v1/models"
        deadline = time.monotonic() + _STARTUP_TIMEOUT

        while time.monotonic() < deadline:
            try:
                resp = urllib.request.urlopen(url, timeout=5)
                if resp.status == 200:
                    return True
            except (urllib.error.URLError, ConnectionError, OSError):
                pass

            time.sleep(_POLL_INTERVAL)

        return False

    def stop(self) -> None:
        """Terminate the vLLM server subprocess."""
        with self._lock:
            if self._process is None:
                return
            logger.info("Stopping vLLM server ...")
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except Exception:
                try:
                    self._process.kill()
                    self._process.wait(timeout=5)
                except Exception:
                    pass
            self._process = None
            self._model_name = ""

    def is_alive(self) -> bool:
        """Check if the server process is running."""
        if self._process is None:
            return False
        ret = self._process.poll()
        return ret is None

    def __enter__(self) -> VllmServer:
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()


_server: VllmServer | None = None


def get_server() -> VllmServer:
    """Get or create the singleton VllmServer instance."""
    global _server
    if _server is None:
        _server = VllmServer()
    return _server
