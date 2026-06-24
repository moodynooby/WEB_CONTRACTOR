"""Embedded vLLM Engine — runs LLMs directly in-process via CUDA.

No external server (Ollama, LM Studio) required. Models are loaded
into GPU memory on first inference call and reused across requests.

RAM-based model auto-selection:
  ≤ 8GB  → Qwen2.5-1.5B-Instruct  (~2GB VRAM)
  ≤ 16GB → Qwen2.5-7B-Instruct    (~8GB VRAM)
  > 16GB → Qwen2.5-14B-Instruct   (~14GB VRAM)

Usage:
    from infra.vllm_engine import generate as vllm_generate
    result = vllm_generate(messages=[{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import threading
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


class VllmEngine:
    """Singleton vLLM engine — loads model once, reuses for all requests."""

    _instance: VllmEngine | None = None
    _lock = threading.Lock()

    def __new__(cls) -> VllmEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._llm: Any = None
        self._model_name: str = ""
        self._config = get_section("llm").get("vllm", {})

    def _select_model_by_ram(self) -> str:
        """Pick a model based on available system RAM."""
        import psutil

        ram_gb = psutil.virtual_memory().total / (1024**3)
        logger.info(f"System RAM: {ram_gb:.1f} GB")

        for threshold, model in _MODEL_TIERS:
            if ram_gb <= threshold:
                logger.info(f"Selected model for {ram_gb:.0f}GB RAM: {model}")
                return model

        logger.info(f"Selected default model for {ram_gb:.0f}GB RAM: {_DEFAULT_MODEL}")
        return _DEFAULT_MODEL

    def _ensure_loaded(self) -> None:
        """Lazy-load the vLLM model on first call."""
        if self._llm is not None:
            return

        configured_model = self._config.get("model", "auto")
        model = (
            self._select_model_by_ram()
            if configured_model == "auto"
            else configured_model
        )
        self._model_name = model

        logger.info(f"Loading vLLM model: {model} (this may take a moment)...")

        from vllm import LLM

        self._llm = LLM(
            model=model,
            tensor_parallel_size=self._config.get("tensor_parallel", 1),
            max_model_len=self._config.get("max_model_len", 4096),
            gpu_memory_utilization=self._config.get("gpu_memory_utilization", 0.8),
            trust_remote_code=True,
        )
        logger.info(f"vLLM model loaded: {model}")

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.5,
        format_json: bool = False,
    ) -> str:
        """Generate text from messages using vLLM.

        Args:
            messages: List of {"role": "system"|"user"|"assistant", "content": "..."}.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            format_json: If True, append JSON instruction to system prompt.

        Returns:
            Generated text string.
        """
        self._ensure_loaded()

        from vllm import SamplingParams

        params = SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
        )

        chat_messages = list(messages)
        if format_json:
            json_instruction = (
                "You MUST respond with valid JSON only. No extra text, "
                "no markdown fences, no explanations. Just the JSON object."
            )
            if chat_messages and chat_messages[0].get("role") == "system":
                chat_messages[0] = {
                    "role": "system",
                    "content": chat_messages[0]["content"] + "\n\n" + json_instruction,
                }
            else:
                chat_messages.insert(0, {"role": "system", "content": json_instruction})

        outputs = self._llm.chat(messages=chat_messages, sampling_params=params)
        result = outputs[0].outputs[0].text

        if format_json:
            result = _extract_json(result)

        return result

    @property
    def model_name(self) -> str:
        """Return the currently loaded model name."""
        return self._model_name

    def unload(self) -> None:
        """Unload the model from GPU memory."""
        self._llm = None
        self._model_name = ""
        logger.info("vLLM model unloaded")


def _extract_json(text: str) -> str:
    """Extract JSON object/array from text that may contain filler."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


_engine: VllmEngine | None = None


def get_engine() -> VllmEngine:
    """Get the singleton vLLM engine instance."""
    global _engine
    if _engine is None:
        _engine = VllmEngine()
    return _engine


def generate(
    messages: list[dict[str, str]],
    max_tokens: int = 2048,
    temperature: float = 0.5,
    format_json: bool = False,
) -> str:
    """Convenience wrapper for vLLM generation."""
    return get_engine().generate(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        format_json=format_json,
    )


def is_available() -> bool:
    """Check if vLLM is importable and a CUDA GPU is present."""
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False
