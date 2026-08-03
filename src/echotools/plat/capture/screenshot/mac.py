from __future__ import annotations

"""macOS CoreGraphics screenshot backend."""

import ctypes
import ctypes.util
import os
import subprocess
import time
from ctypes import POINTER, byref, c_ubyte, c_void_p

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.shared.bmp import write_bmp

_cg_path = ctypes.util.find_library("CoreGraphics") or (
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
)
_cf_path = ctypes.util.find_library("CoreFoundation") or (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_CG = ctypes.CDLL(_cg_path)
_CF = ctypes.CDLL(_cf_path)

CGDirectDisplayID = ctypes.c_uint32
CGError = ctypes.c_int32

_CG.CGGetActiveDisplayList.restype = CGError
_CG.CGGetActiveDisplayList.argtypes = [
    ctypes.c_uint32, POINTER(CGDirectDisplayID), POINTER(ctypes.c_uint32),
]
_CG.CGDisplayCreateImage.restype = c_void_p
_CG.CGDisplayCreateImage.argtypes = [CGDirectDisplayID]
_CG.CGImageGetWidth.restype = ctypes.c_size_t
_CG.CGImageGetWidth.argtypes = [c_void_p]
_CG.CGImageGetHeight.restype = ctypes.c_size_t
_CG.CGImageGetHeight.argtypes = [c_void_p]
_CG.CGImageGetBytesPerRow.restype = ctypes.c_size_t
_CG.CGImageGetBytesPerRow.argtypes = [c_void_p]
_CG.CGImageGetDataProvider.restype = c_void_p
_CG.CGImageGetDataProvider.argtypes = [c_void_p]
_CG.CGDataProviderCopyData.restype = c_void_p
_CG.CGDataProviderCopyData.argtypes = [c_void_p]
_CF.CFDataGetLength.restype = ctypes.c_long
_CF.CFDataGetLength.argtypes = [c_void_p]
_CF.CFDataGetBytePtr.restype = POINTER(c_ubyte)
_CF.CFDataGetBytePtr.argtypes = [c_void_p]
_CF.CFRelease.restype = None
_CF.CFRelease.argtypes = [c_void_p]


def _cg_get_display_id(idx: int) -> int:
    max_d = 32
    ids = (CGDirectDisplayID * max_d)()
    cnt = ctypes.c_uint32(0)
    _CG.CGGetActiveDisplayList(max_d, ids, byref(cnt))
    if idx >= cnt.value:
        raise OSError(f"显示器索引 {idx} 超出范围（共 {cnt.value} 台）")
    return ids[idx]


def cg_screenshot(out_path: str, monitor_index: int) -> None:
    disp_id = _cg_get_display_id(monitor_index)
    img_ref = _CG.CGDisplayCreateImage(disp_id)
    if not img_ref:
        raise OSError("CGDisplayCreateImage 返回 NULL")

    w = _CG.CGImageGetWidth(img_ref)
    h = _CG.CGImageGetHeight(img_ref)
    bpr = _CG.CGImageGetBytesPerRow(img_ref)
    provider = _CG.CGImageGetDataProvider(img_ref)
    cf_data = _CG.CGDataProviderCopyData(provider)
    if not cf_data:
        raise OSError("CGDataProviderCopyData 返回 NULL")

    length = _CF.CFDataGetLength(cf_data)
    byte_ptr = _CF.CFDataGetBytePtr(cf_data)
    raw = bytes(byte_ptr[:length])
    _CF.CFRelease(cf_data)
    rows = [raw[y * bpr : y * bpr + w * 4] for y in range(h)]
    pix = b"".join(rows)
    write_bmp(out_path, w, h, pix, top_down=True)


def screencapture_screenshot(out_path: str, monitor_index: int, output_ext: str) -> None:
    png_path = out_path.replace(f".{output_ext}", ".png")
    ret = subprocess.run(
        ["screencapture", "-x", "-D", str(monitor_index + 1), png_path],
        timeout=10,
    )
    if ret.returncode != 0:
        raise OSError(f"screencapture 失败，returncode={ret.returncode}")
    if not os.path.exists(png_path):
        raise OSError("screencapture 未生成文件")
    if png_path != out_path:
        os.replace(png_path, out_path)


def mac_capture_session(cfg: ScreenshotConfig) -> None:
    for i in range(cfg.capture_count):
        out_path = cfg.output_path(i)
        captured = False
        try:
            cg_screenshot(out_path, cfg.monitor_index)
            print(f"[+] CG    第{i + 1}/{cfg.capture_count}张: {out_path}")
            captured = True
        except Exception as exc:
            print(f"[!] CoreGraphics 失败: {exc}\n    => 回退 screencapture")

        if not captured:
            try:
                out_path = cfg.output_path(i, ext="png")
                screencapture_screenshot(out_path, cfg.monitor_index, cfg.output_ext)
                print(f"[+] SC    第{i + 1}/{cfg.capture_count}张: {out_path}")
                captured = True
            except Exception as exc:
                print(f"[!] screencapture 失败: {exc}")

        if not captured:
            raise RuntimeError(f"macOS 第{i + 1}张截图所有方案均失败")

        if cfg.capture_interval_sec > 0 and i < cfg.capture_count - 1:
            time.sleep(cfg.capture_interval_sec)
