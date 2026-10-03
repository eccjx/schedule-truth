"""Windows process ownership without a stale on-disk lock marker."""

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import threading

_owned_roots = set()
_guard = threading.Lock()


@contextmanager
def own_archive(root: Path):
    if os.name != 'nt':
        raise RuntimeError('Archive ownership currently requires Windows.')
    key = os.path.normcase(str(root.resolve()))
    with _guard:
        if key in _owned_roots:
            raise RuntimeError(f'Archive root already owned: {root}')
        _owned_roots.add(key)
    handle = None
    acquired = False
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.ReleaseMutex.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        name = 'Global\\schedule-truth-vp-' + hashlib.sha256(key.encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        status = kernel.WaitForSingleObject(handle, 0)
        if status == 258:  # WAIT_TIMEOUT: another owner is alive.
            raise RuntimeError(f'Archive root already owned: {root}')
        if status not in (0, 128):  # Acquired normally or abandoned by a dead owner.
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        if handle:
            kernel.CloseHandle(handle)
        with _guard:
            _owned_roots.remove(key)
