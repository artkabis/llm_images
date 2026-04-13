"""Router /monitoring — Endpoints santé, métriques ML et système."""
import psutil, httpx
from fastapi import APIRouter, Depends
from core.security import require_role
from core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def system_health(_=Depends(require_role("operator"))):
    """Vue consolidée de la santé de tous les services."""
    health = {"api": "ok", "ml": "unknown", "video": "unknown", "redis": "unknown"}

    async with httpx.AsyncClient(timeout=3) as client:
        for svc, url in [("ml", f"{settings.ml_service_url}/health"),
                         ("video", "http://video:8002/health")]:
            try:
                r = await client.get(url)
                health[svc] = "ok" if r.status_code == 200 else "degraded"
            except Exception:
                health[svc] = "down"

    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        health["redis"] = "ok"
    except Exception:
        health["redis"] = "down"

    overall = "ok" if all(v == "ok" for v in health.values()) else "degraded"
    return {"overall": overall, "services": health}


@router.get("/ml")
async def ml_metrics(_=Depends(require_role("admin"))):
    """Métriques ML depuis le service ML."""
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(f"{settings.ml_service_url}/health")
            return r.json()
        except Exception:
            return {"error": "Service ML indisponible"}


@router.get("/system/resources")
async def system_resources(_=Depends(require_role("admin"))):
    """CPU, RAM, disque, réseau."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    result = {
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "net_sent_mb": round(net.bytes_sent / 1e6, 2),
        "net_recv_mb": round(net.bytes_recv / 1e6, 2),
    }

    # GPU si disponible
    try:
        import subprocess
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], text=True
        )
        gpu_util, mem_used, mem_total = out.strip().split(", ")
        result["gpu_percent"] = float(gpu_util)
        result["gpu_vram_used_mb"] = float(mem_used)
        result["gpu_vram_total_mb"] = float(mem_total)
    except Exception:
        result["gpu_percent"] = None

    return result


@router.get("/cameras/status")
async def cameras_status(_=Depends(require_role("operator"))):
    """Statut de toutes les caméras depuis le service vidéo."""
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get("http://video:8002/health")
            return r.json()
        except Exception:
            return {"cameras": [], "error": "Service vidéo indisponible"}
