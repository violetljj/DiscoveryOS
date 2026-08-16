from __future__ import annotations

import os
import sys


def current_rss_bytes() -> int:
    """Best-effort resident memory for the current worker process."""
    if sys.platform == "win32":
        return _windows_rss_bytes(os.getpid())
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, OSError, ValueError):
        return 0


def process_rss_bytes(process_id: int) -> int:
    if sys.platform == "win32":
        return _windows_rss_bytes(process_id)
    try:
        status = open(f"/proc/{process_id}/status", encoding="utf-8").read().splitlines()
    except (FileNotFoundError, PermissionError, OSError):
        return 0
    for line in status:
        if line.startswith(("VmHWM:", "VmRSS:")):
            return int(line.split()[1]) * 1024
    return 0


def _windows_rss_bytes(process_id: int) -> int:
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        query_information = 0x0400
        read_memory = 0x0010
        handle = ctypes.windll.kernel32.OpenProcess(query_information | read_memory, False, process_id)
        if not handle:
            return 0
        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return 0
            return int(counters.PeakWorkingSetSize)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return 0
