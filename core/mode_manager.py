"""Mode Manager - Runtime mode switching and validation.

Provides utilities for detecting hardware, validating mode compatibility,
and applying mode settings across the application.
"""

import json
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.mode_config import (
    get_hardware_info,
    get_mode_profile,
    validate_mode_for_hardware,
)

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "app_config.json"


class ModeManager:
    """Manages performance modes and local/cloud switching."""

    def __init__(self):
        self._hardware_info = get_hardware_info()
        logger.info(
            f"ModeManager initialized. Hardware: {self._hardware_info['profile']}"
        )

    @property
    def hardware_info(self) -> dict[str, Any]:
        """Get detected hardware information."""
        return self._hardware_info

    def get_current_mode(self) -> dict[str, Any]:
        """Get current active mode configuration."""
        from core.settings import LLM_MODE, PERFORMANCE_MODE, LOCAL_PROVIDER

        mode_profile = get_mode_profile(PERFORMANCE_MODE)

        return {
            "llm_mode": LLM_MODE,
            "performance_mode": PERFORMANCE_MODE,
            "local_provider": LOCAL_PROVIDER if LLM_MODE == "local" else None,
            "hardware": self._hardware_info["profile"],
            "profile": mode_profile,
            "is_local": LLM_MODE == "local",
        }

    def validate_mode(self, mode: str, hardware: str | None = None) -> tuple[bool, str]:
        """Validate if a mode is compatible with hardware."""
        return validate_mode_for_hardware(mode, hardware)

    def apply_mode(
        self,
        llm_mode: str,
        performance_mode: str,
        local_provider: str | None = None,
    ) -> tuple[bool, str]:
        """Apply mode settings to configuration.

        Args:
            llm_mode: "cloud" or "local"
            performance_mode: "cloud_standard", "cloud_extended", "local_standard", "local_server"
            local_provider: "ollama", "llama_cpp", "vllm" (if llm_mode is "local")

        Returns:
            Tuple of (success, message)
        """
        if llm_mode not in ("cloud", "local"):
            return False, f"Invalid LLM mode: {llm_mode}. Must be 'cloud' or 'local'."

        try:
            get_mode_profile(performance_mode)
        except ValueError as e:
            return False, str(e)

        is_valid, warning = self.validate_mode(performance_mode)
        if not is_valid:
            return False, warning

        try:
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)

            config.setdefault("llm", {})["mode"] = llm_mode
            config["llm"]["performance_mode"] = performance_mode

            if llm_mode == "local" and local_provider:
                config["llm"].setdefault("local", {})["provider"] = local_provider

            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)

            logger.info(
                f"Mode applied: {llm_mode}/{performance_mode}"
                + (f" ({local_provider})" if local_provider else "")
            )

            if is_valid and "✅" not in warning:
                return True, warning

            return True, f"✅ Mode applied successfully: {llm_mode}/{performance_mode}"

        except Exception as e:
            error_msg = f"Failed to apply mode: {e}"
            logger.error(error_msg)
            return False, error_msg

    def test_local_provider(self, provider: str | None = None) -> tuple[bool, str]:
        """Test if a local provider is accessible.

        Args:
            provider: Provider name ("ollama", "llama_cpp", "vllm")
                     If None, uses current config

        Returns:
            Tuple of (is_available, message)
        """
        import requests

        from core.settings import LOCAL_BASE_URL, LOCAL_PROVIDER

        provider = provider or LOCAL_PROVIDER

        if provider == "ollama":
            try:
                from core.settings import LOCAL_BASE_URL

                base_url = LOCAL_BASE_URL.replace("/v1", "")
                response = requests.get(f"{base_url}", timeout=5)

                if response.status_code == 200:
                    return True, "✅ Ollama is running and accessible"
                else:
                    return False, f"⚠️ Ollama returned status {response.status_code}"

            except requests.exceptions.ConnectionError:
                return False, "❌ Cannot connect to Ollama. Is it running? (Default: http://localhost:11434)"
            except requests.exceptions.Timeout:
                return False, "❌ Ollama connection timed out"
            except Exception as e:
                return False, f"❌ Ollama test failed: {e}"

        elif provider == "vllm":
            try:
                from core.settings import LOCAL_BASE_URL

                response = requests.get(f"{LOCAL_BASE_URL}/models", timeout=5)

                if response.status_code == 200:
                    return True, "✅ vLLM is running and accessible"
                else:
                    return False, f"⚠️ vLLM returned status {response.status_code}"

            except requests.exceptions.ConnectionError:
                return False, "❌ Cannot connect to vLLM. Is it running? (Default: http://localhost:8000)"
            except requests.exceptions.Timeout:
                return False, "❌ vLLM connection timed out"
            except Exception as e:
                return False, f"❌ vLLM test failed: {e}"

        elif provider == "llama_cpp":
            return True, "✅ llama-cpp-python is a Python library (no server test needed)"

        else:
            return False, f"❌ Unknown provider: {provider}"

    def get_mode_recommendations(self) -> dict[str, str]:
        """Get mode recommendations based on detected hardware."""
        hardware = self._hardware_info["profile"]
        recommendations = {}

        if hardware == "gpu_nvidia":
            vram_gb = self._hardware_info.get("gpu_vram_gb", 0)
            ram_gb = self._hardware_info.get("total_ram_gb", 0)
            
            # Server mode: 64GB+ RAM and 6GB+ VRAM
            if ram_gb >= 64 and vram_gb >= 6:
                recommendations["recommended"] = "local_server"
                recommendations["message"] = f"🖥️ Server-grade hardware detected ({ram_gb}GB RAM, {vram_gb}GB VRAM) - Server mode recommended!"
            elif vram_gb >= 4:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"💻 GPU with {vram_gb}GB VRAM - Local Standard mode recommended"
            else:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"⚠️ Limited VRAM ({vram_gb}GB) - Local Standard mode with smaller models recommended"

        elif hardware == "apple_silicon":
            ram_gb = self._hardware_info.get("total_ram_gb", 0)
            if ram_gb >= 64:
                recommendations["recommended"] = "local_server"
                recommendations["message"] = f"🖥️ Apple Silicon with {ram_gb}GB RAM - Server mode supported!"
            elif ram_gb >= 16:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"💻 Apple Silicon with {ram_gb}GB RAM - Local Standard mode recommended"
            else:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"⚠️ Apple Silicon with {ram_gb}GB RAM - Local Standard mode with smaller models"

        else:
            # CPU-only mode
            ram_gb = self._hardware_info.get("total_ram_gb", 0)
            if ram_gb >= 16:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"💻 CPU-only with {ram_gb}GB RAM - Local Standard mode possible with quantized models"
            else:
                recommendations["recommended"] = "local_standard"
                recommendations["message"] = f"⚠️ CPU-only with limited RAM ({ram_gb}GB) - Consider cloud mode or upgrade hardware"

        return recommendations


_mode_manager = None


def get_mode_manager() -> ModeManager:
    """Get or create the mode manager singleton."""
    global _mode_manager
    if _mode_manager is None:
        _mode_manager = ModeManager()
    return _mode_manager
