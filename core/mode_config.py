"""Performance Mode Configurations

Defines predefined performance profiles that control model size,
response speed vs quality, hardware utilization, and parallel processing.
"""

from typing import Any


MODE_PROFILES: dict[str, dict[str, Any]] = {
    "cloud_standard": {
        "label": "☁️ Cloud Standard",
        "icon": "☁️",
        "model_size": "Provider default (typically 7B-70B)",
        "quality_priority": "high",
        "temperature": 0.2,
        "max_tokens": 2048,
        "gpu_layers": 0,
        "cpu_threads": 0,
        "context_size": 4096,
        "parallel_workers": 0,
        "timeout_multiplier": 1.0,
        "quantization": "N/A (cloud)",
        "min_vram_gb": 0,
        "min_ram_gb": 0,
        "description": "Balanced cloud API usage with default provider settings",
        "mode_type": "cloud",
    },
    "cloud_extended": {
        "label": "☁️ Cloud Extended",
        "icon": "☁️",
        "model_size": "Provider default (extended context)",
        "quality_priority": "maximum",
        "temperature": 0.1,
        "max_tokens": 4096,
        "gpu_layers": 0,
        "cpu_threads": 0,
        "context_size": 8192,
        "parallel_workers": 0,
        "timeout_multiplier": 1.5,
        "quantization": "N/A (cloud)",
        "min_vram_gb": 0,
        "min_ram_gb": 0,
        "description": "Extended token limits for complex cloud analysis",
        "mode_type": "cloud",
    },
    "local_standard": {
        "label": "💻 Local Standard",
        "icon": "💻",
        "model_size": "7B-13B",
        "quality_priority": "medium",
        "temperature": 0.2,
        "max_tokens": 2048,
        "gpu_layers": -1,
        "cpu_threads": 4,
        "context_size": 4096,
        "parallel_workers": 4,
        "timeout_multiplier": 1.0,
        "quantization": "Q4_K_M",
        "min_vram_gb": 4,
        "min_ram_gb": 8,
        "description": "Balanced local LLM performance for typical hardware",
        "mode_type": "local",
    },
    "local_server": {
        "label": "🖥️ Server",
        "icon": "🖥️",
        "model_size": "70B+ or largest available",
        "quality_priority": "maximum",
        "temperature": 0.05,
        "max_tokens": 8192,
        "gpu_layers": -1,
        "cpu_threads": 16,
        "context_size": 32768,
        "parallel_workers": 16,
        "timeout_multiplier": 3.0,
        "quantization": "Q8_0 or uncompressed",
        "min_vram_gb": 6,
        "min_ram_gb": 64,
        "description": "Maximum performance for server-grade hardware (128GB RAM, RTX A1000+)",
        "mode_type": "local",
    },
}

LOCAL_PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "name": "Ollama",
        "default_base_url": "http://localhost:11434/v1",
        "type": "openai_compatible",
        "description": "Easy to use, supports many models",
        "setup_url": "https://ollama.com",
    },
    "llama_cpp": {
        "name": "llama-cpp-python",
        "default_base_url": None,  
        "type": "native",
        "description": "Direct GGUF model loading, more control",
        "setup_url": "https://github.com/abetlen/llama-cpp-python",
    },
    "vllm": {
        "name": "vLLM",
        "default_base_url": "http://localhost:8000/v1",
        "type": "openai_compatible",
        "description": "High-performance local serving",
        "setup_url": "https://github.com/vllm-project/vllm",
    },
}


def get_mode_profile(mode: str) -> dict[str, Any]:
    """Get a performance mode profile by name."""
    if mode not in MODE_PROFILES:
        raise ValueError(
            f"Unknown mode: {mode}. Available: {list(MODE_PROFILES.keys())}"
        )
    return MODE_PROFILES[mode]


def get_local_provider_config(provider: str) -> dict[str, Any]:
    """Get local provider configuration by name."""
    if provider not in LOCAL_PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider}. Available: {list(LOCAL_PROVIDERS.keys())}"
        )
    return LOCAL_PROVIDERS[provider]


def get_all_modes() -> list[dict[str, Any]]:
    """Get all available performance modes."""
    return [
        {"key": key, **value} for key, value in MODE_PROFILES.items()
    ]


def get_all_local_providers() -> list[dict[str, Any]]:
    """Get all available local providers."""
    return [
        {"key": key, **value} for key, value in LOCAL_PROVIDERS.items()
    ]


def detect_hardware() -> str:
    """Auto-detect hardware capabilities.
    
    Returns:
        Hardware profile: "gpu_nvidia", "apple_silicon", or "cpu"
    """
    import platform
    import subprocess
    
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return "gpu_nvidia"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    
    if platform.system() == "Darwin":
        machine = platform.machine()
        if "arm" in machine.lower() or machine == "arm64":
            return "apple_silicon"
    
    try:
        result = subprocess.run(
            ["rocm-smi"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return "gpu_amd"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    
    return "cpu"


def get_hardware_info() -> dict[str, Any]:
    """Get detailed hardware information."""
    import platform
    import psutil
    
    hw_info: dict[str, Any] = {
        "profile": detect_hardware(),
        "cpu_threads": psutil.cpu_count(logical=True) or 1,
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "machine": platform.machine(),
        "system": platform.system(),
        "processor": platform.processor(),
    }
    
    if hw_info["profile"] == "gpu_nvidia":
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                gpu_info = result.stdout.strip().split("\n")[0]
                parts = gpu_info.split(",")
                hw_info["gpu_name"] = parts[0].strip()
                hw_info["gpu_vram_gb"] = round(float(parts[1].strip().replace(" MiB", "")) / 1024, 1)
        except Exception:
            pass
    elif hw_info["profile"] == "apple_silicon":
        hw_info["gpu_name"] = "Apple GPU (Metal)"
        hw_info["gpu_vram_gb"] = hw_info["total_ram_gb"]  
    
    return hw_info


def validate_mode_for_hardware(mode: str, hardware: str | None = None) -> tuple[bool, str]:
    """Validate if a mode is compatible with the detected hardware.

    Returns:
        Tuple of (is_valid, warning_message)
    """
    if hardware is None:
        hardware = detect_hardware()

    profile = get_mode_profile(mode)
    mode_type = profile.get("mode_type", "local")

    # Cloud modes don't need hardware validation
    if mode_type == "cloud":
        return True, f"✅ {profile['label']} mode uses cloud resources."

    # Local modes need hardware validation (but show warnings, don't block)
    import psutil

    available_ram_gb = psutil.virtual_memory().total / (1024**3)
    warnings = []

    # Check RAM requirement
    if available_ram_gb < profile["min_ram_gb"]:
        warnings.append(
            f"⚠️ {profile['label']} mode recommends {profile['min_ram_gb']}GB RAM, "
            f"but only {available_ram_gb:.1f}GB detected."
        )

    # Check VRAM requirement for local modes
    if profile["min_vram_gb"] > 0 and hardware == "cpu":
        warnings.append(
            f"⚠️ {profile['label']} mode requires GPU. "
            f"Switch to a GPU or use CPU-only mode with smaller models."
        )
    elif hardware == "gpu_nvidia":
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                vram_mb = float(result.stdout.strip())
                vram_gb = vram_mb / 1024
                if vram_gb < profile["min_vram_gb"]:
                    warnings.append(
                        f"⚠️ {profile['label']} mode recommends {profile['min_vram_gb']}GB VRAM, "
                        f"but only {vram_gb:.1f}GB detected."
                    )
        except Exception:
            pass

    if warnings:
        return True, "\n".join(warnings)

    return True, f"✅ {profile['label']} mode is supported on your hardware."
