"""Process and container memory telemetry for small Render instances."""
import asyncio
import ctypes
import gc
from pathlib import Path

heavy = asyncio.Lock()

_CGROUP_V2 = Path("/sys/fs/cgroup")
_CGROUP_V1 = Path("/sys/fs/cgroup/memory")


def _read_number(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="ascii").strip()
        if value == "max":
            return None
        number = int(value)
        return None if number >= (1 << 60) else number
    except (OSError, ValueError):
        return None


def rss_mb() -> int:
    """Resident memory for the API process only."""
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            return int(next(line for line in status if line.startswith("VmRSS:")).split()[1]) // 1024
    except (OSError, StopIteration, ValueError):
        return 0


def container_memory() -> dict[str, int | None]:
    """Read cgroup memory so child renderer/FFmpeg processes are included."""
    candidates = (
        (_CGROUP_V2 / "memory.current", _CGROUP_V2 / "memory.max", _CGROUP_V2 / "memory.peak"),
        (_CGROUP_V1 / "memory.usage_in_bytes", _CGROUP_V1 / "memory.limit_in_bytes", _CGROUP_V1 / "memory.max_usage_in_bytes"),
    )
    for usage_path, limit_path, peak_path in candidates:
        usage = _read_number(usage_path)
        if usage is None:
            continue
        limit = _read_number(limit_path)
        peak = _read_number(peak_path)
        return {
            "used_mb": usage // (1024 * 1024),
            "limit_mb": None if limit is None else limit // (1024 * 1024),
            "peak_mb": None if peak is None else peak // (1024 * 1024),
        }
    return {"used_mb": None, "limit_mb": None, "peak_mb": None}


def report(where: str) -> None:
    """Log process RSS and container-wide memory, including subprocesses."""
    stats = container_memory()
    print(
        "memory: "
        f"{where}; process_rss_mb={rss_mb()}; "
        f"container_used_mb={stats['used_mb']}; "
        f"container_limit_mb={stats['limit_mb']}; "
        f"container_peak_mb={stats['peak_mb']}",
        flush=True,
    )


def free() -> None:
    """Return freed Python/native allocations to the Linux allocator where possible."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass
