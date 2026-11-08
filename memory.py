"""Keeps the whole app under 512 MB (Render's smaller plans).

The two big things, the voice model and the text embedder, never sit in memory at the same time:
whoever needs one takes `heavy`, uses it, drops it and calls `free()` before letting go.
"""
import asyncio
import ctypes
import gc

heavy = asyncio.Lock()


def free() -> None:
    """Gives memory that Python no longer uses back to the operating system."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)       # Linux (glibc); elsewhere there is nothing to trim
    except (OSError, AttributeError):
        pass
