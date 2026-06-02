import subprocess
import shutil
import logging
import psutil
from typing import Dict, Any, Optional

logger = logging.getLogger("Viernes.Telemetry")

# Cache command line tools dynamically on import
NVIDIA_SMI = shutil.which("nvidia-smi")
ROCM_SMI = shutil.which("rocm-smi")
AMD_SMI = shutil.which("amd-smi")

# Call once to initialize psutil CPU interval tracking
psutil.cpu_percent(interval=None)

def get_gpu_telemetry() -> Optional[Dict[str, Any]]:
    """
    Attempts to read GPU metrics from nvidia-smi, amd-smi, or rocm-smi.
    Returns:
        A dictionary with GPU usage percentage, temperature, and VRAM info if successful,
        else None.
    """
    # 1. Try nvidia-smi
    if NVIDIA_SMI:
        try:
            # Query GPU utilization, temperature, memory used, memory total
            res = subprocess.run(
                [
                    NVIDIA_SMI,
                    "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0
            )
            if res.returncode == 0:
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 4:
                    gpu_usage = float(parts[0])
                    temp = float(parts[1])
                    vram_used = float(parts[2])
                    vram_total = float(parts[3])
                    vram_percent = (vram_used / vram_total * 100.0) if vram_total > 0 else 0.0
                    return {
                        "provider": "nvidia",
                        "usage_percent": gpu_usage,
                        "temperature": temp,
                        "vram_used_mb": vram_used,
                        "vram_total_mb": vram_total,
                        "vram_percent": vram_percent
                    }
        except Exception as e:
            logger.debug(f"Failed to query nvidia-smi: {e}")

    # 2. Try amd-smi (modern AMD tool)
    if AMD_SMI:
        try:
            res = subprocess.run(
                [AMD_SMI, "metric", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0
            )
            if res.returncode == 0:
                import json
                data = json.loads(res.stdout)
                if isinstance(data, list) and len(data) > 0:
                    device = data[0]
                elif isinstance(data, dict):
                    device = data.get("devices", [data])[0] if data.get("devices") else data
                else:
                    device = None

                if device:
                    gpu_usage = device.get("gpu_use") or device.get("utilization", {}).get("gpu") or 0.0
                    temp = device.get("temperature") or device.get("temperature", {}).get("edge") or 0.0
                    vram_used = device.get("vram_used") or device.get("memory", {}).get("vram", {}).get("used") or 0.0
                    vram_total = device.get("vram_total") or device.get("memory", {}).get("vram", {}).get("total") or 0.0
                    
                    if vram_used > 1000000:
                        vram_used = vram_used / (1024 * 1024)
                        vram_total = vram_total / (1024 * 1024)
                    
                    vram_percent = (vram_used / vram_total * 100.0) if vram_total > 0 else 0.0
                    return {
                        "provider": "amd-smi",
                        "usage_percent": float(gpu_usage),
                        "temperature": float(temp),
                        "vram_used_mb": float(vram_used),
                        "vram_total_mb": float(vram_total),
                        "vram_percent": float(vram_percent)
                    }
        except Exception as e:
            logger.debug(f"Failed to query amd-smi: {e}")

    # 3. Try rocm-smi (legacy AMD tool)
    if ROCM_SMI:
        try:
            res = subprocess.run(
                [ROCM_SMI, "--showuse", "--showmemuse", "--showtemp", "--csv"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0
            )
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                if len(lines) >= 2:
                    headers = [h.strip().lower() for h in lines[0].split(",")]
                    values = [v.strip() for v in lines[1].split(",")]
                    metrics = dict(zip(headers, values))
                    
                    gpu_use_key = [k for k in metrics if 'use' in k and 'mem' not in k]
                    mem_use_key = [k for k in metrics if 'mem' in k or 'vram' in k]
                    temp_key = [k for k in metrics if 'temp' in k or 'celsius' in k]

                    gpu_usage = 0.0
                    if gpu_use_key:
                        try:
                            gpu_usage = float(metrics[gpu_use_key[0]].replace("%", ""))
                        except ValueError:
                            pass

                    temp = 0.0
                    if temp_key:
                        try:
                            temp_str = metrics[temp_key[0]].lower().replace("c", "").replace("celsius", "").strip()
                            temp = float(temp_str)
                        except ValueError:
                            pass

                    vram_percent = 0.0
                    if mem_use_key:
                        try:
                            vram_percent = float(metrics[mem_use_key[0]].replace("%", ""))
                        except ValueError:
                            pass

                    return {
                        "provider": "rocm-smi",
                        "usage_percent": gpu_usage,
                        "temperature": temp,
                        "vram_percent": vram_percent,
                        "vram_used_mb": 0.0,
                        "vram_total_mb": 0.0
                    }
        except Exception as e:
            logger.debug(f"Failed to query rocm-smi: {e}")

    return None

def get_system_telemetry() -> Dict[str, Any]:
    """
    Collects system performance telemetry (CPU, RAM, GPU, Disk).
    
    Returns:
        A dictionary with CPU, RAM, GPU, and Disk telemetry.
    """
    # 1. CPU Usage (non-blocking)
    cpu_percent = psutil.cpu_percent(interval=None)

    # 2. RAM Usage
    ram = psutil.virtual_memory()
    ram_percent = ram.percent

    # 3. Disk Usage (of root '/' formatted as 'used/total GB')
    try:
        disk = psutil.disk_usage('/')
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        disk_display = f"{used_gb:.1f}/{total_gb:.1f} GB"
        disk_percent = disk.percent
    except Exception as e:
        logger.error(f"Failed to read disk usage: {e}")
        disk_display = "N/A"
        disk_percent = 0.0

    # 4. GPU Usage
    gpu_stats = get_gpu_telemetry()

    return {
        "cpu": {
            "usage_percent": cpu_percent
        },
        "ram": {
            "usage_percent": ram_percent
        },
        "gpu": gpu_stats,
        "disk": {
            "usage_percent": disk_percent,
            "display": disk_display
        }
    }
