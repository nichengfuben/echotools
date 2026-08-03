from __future__ import annotations

"""Windows GDI BitBlt screenshot backend and cursor overlay."""

import ctypes
import ctypes.wintypes as wt
import time
from ctypes import Structure, byref, c_int, c_void_p, sizeof

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.shared.bmp import write_bmp

SM_CXSCREEN = 0
SM_CYSCREEN = 1
DIB_RGB_COLORS = 0
BI_RGB = 0
SRCCOPY = 0x00CC0020
CURSOR_SHOWING = 0x00000001
DI_NORMAL = 0x0003

_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.GetDC.argtypes = [wt.HWND]
_user32.GetDC.restype = wt.HDC
_user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
_user32.GetDesktopWindow.restype = wt.HWND
_user32.GetSystemMetrics.argtypes = [c_int]
_user32.GetSystemMetrics.restype = c_int
_user32.GetCursorInfo.argtypes = [c_void_p]
_user32.GetCursorInfo.restype = wt.BOOL
_user32.GetIconInfo.argtypes = [wt.HICON, c_void_p]
_user32.GetIconInfo.restype = wt.BOOL
_user32.DrawIconEx.argtypes = [
    wt.HDC, c_int, c_int, wt.HICON, c_int, c_int, wt.UINT, wt.HBRUSH, wt.UINT,
]
_user32.DrawIconEx.restype = wt.BOOL


class _POINT(Structure):
    _fields_ = [("x", c_int), ("y", c_int)]


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class CURSORINFO(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("flags", wt.DWORD),
        ("hCursor", wt.HANDLE), ("ptScreenPos", _POINT),
    ]


class ICONINFO(Structure):
    _fields_ = [
        ("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
        ("hbmMask", wt.HANDLE), ("hbmColor", wt.HANDLE),
    ]


def win_draw_cursor(pixel_bytes: bytes, width: int, height: int, cap_left: int, cap_top: int) -> bytes:
    ci = CURSORINFO()
    ci.cbSize = sizeof(CURSORINFO)
    if not _user32.GetCursorInfo(byref(ci)):
        return pixel_bytes
    if ci.flags != CURSOR_SHOWING:
        return pixel_bytes

    ii = ICONINFO()
    if not _user32.GetIconInfo(ci.hCursor, byref(ii)):
        return pixel_bytes
    if ii.hbmMask:
        _gdi32.DeleteObject(ii.hbmMask)
    if ii.hbmColor:
        _gdi32.DeleteObject(ii.hbmColor)

    dx = ci.ptScreenPos.x - ii.xHotspot - cap_left
    dy = ci.ptScreenPos.y - ii.yHotspot - cap_top

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    hdc_s = _user32.GetDC(None)
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_s)
    bits = c_void_p()
    hbmp = _gdi32.CreateDIBSection(hdc_mem, byref(bmi), DIB_RGB_COLORS, byref(bits), None, 0)
    if not hbmp or not bits:
        _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(None, hdc_s)
        return pixel_bytes

    ctypes.memmove(bits, pixel_bytes, len(pixel_bytes))
    old = _gdi32.SelectObject(hdc_mem, hbmp)
    _user32.DrawIconEx(hdc_mem, dx, dy, ci.hCursor, 0, 0, 0, None, DI_NORMAL)
    result = ctypes.string_at(bits, len(pixel_bytes))

    _gdi32.SelectObject(hdc_mem, old)
    _gdi32.DeleteObject(hbmp)
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(None, hdc_s)
    return result


def gdi_screenshot(out_path: str) -> None:
    w = _user32.GetSystemMetrics(SM_CXSCREEN)
    h = _user32.GetSystemMetrics(SM_CYSCREEN)
    hwnd = _user32.GetDesktopWindow()
    hdc_s = _user32.GetDC(hwnd)
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_s)
    hbmp = _gdi32.CreateCompatibleBitmap(hdc_s, w, h)
    old = _gdi32.SelectObject(hdc_mem, hbmp)
    _gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_s, 0, 0, SRCCOPY)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    buf = (ctypes.c_ubyte * (w * h * 4))()
    _gdi32.GetDIBits(hdc_mem, hbmp, 0, h, byref(buf), byref(bmi), DIB_RGB_COLORS)
    write_bmp(out_path, w, h, bytes(buf), top_down=False)

    _gdi32.SelectObject(hdc_mem, old)
    _gdi32.DeleteObject(hbmp)
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(hwnd, hdc_s)


def gdi_run_session(cfg: ScreenshotConfig) -> None:
    for i in range(cfg.capture_count):
        out_path = cfg.output_path(i)
        gdi_screenshot(out_path)
        print(f"[+] GDI   第{i + 1}/{cfg.capture_count}张: {out_path}")
        if cfg.capture_interval_sec > 0 and i < cfg.capture_count - 1:
            time.sleep(cfg.capture_interval_sec)
