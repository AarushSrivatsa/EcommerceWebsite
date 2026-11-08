"""Keeps the whole app under 512 MB (Render's smaller plans).

The two big things, the voice model and the text embedder, never sit in memory at the same time:
whoever needs one takes `heavy`, uses it, drops it and calls `free()` before letting go.
"""
import asyncio
import ctypes
import gc

heavy = asyncio.Lock()


def rss_mb() -> int:
    """How much RAM this process uses right now (0 where /proc does not exist)."""
    try:
        with open("/proc/self/status") as status:
            return int(next(line for line in status if line.startswith("VmRSS:")).split()[1]) // 1024
    except (OSError, StopIteration, ValueError):
        return 0


def report(where: str) -> None:
    """One line in the Render logs: where the RAM stands (search the logs for 'memory:')."""
    print(f"memory: {rss_mb()} MB at {where}", flush=True)


def free() -> None:
    """Gives memory that Python no longer uses back to the operating system."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)       # Linux (glibc); elsewhere there is nothing to trim
    except (OSError, AttributeError):
        pass
