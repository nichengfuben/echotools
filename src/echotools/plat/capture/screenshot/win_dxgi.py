from __future__ import annotations

"""Windows DXGI Desktop Duplication screenshot backend."""

import ctypes
import ctypes.wintypes as wt
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_int,
    c_uint,
    c_void_p,
    sizeof,
)

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.shared.bmp import write_bmp
from echotools.plat.capture.shared.win_com import (
    com_call,
    com_qi,
    com_release,
    make_guid,
)

D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_SDK_VERSION = 7
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1
DXGI_ERROR_WAIT_TIMEOUT = 0x887A0027
HRESULT = ctypes.c_long
PTR_SIZE = sizeof(c_void_p)

IID_IDXGIDevice = make_guid("54ec77fa-1377-44e6-8c32-88fd5f44c84c")
IID_ID3D11Texture2D = make_guid("6f15aaf2-d208-4e89-9ab4-489535d34f9c")
IID_IDXGIOutput1 = make_guid("00cddea8-939b-4b83-a340-a685226666cc")

_d3d11 = ctypes.WinDLL("d3d11")
_d3d11.D3D11CreateDevice.restype = HRESULT
_d3d11.D3D11CreateDevice.argtypes = [
    c_void_p, c_uint, c_void_p, c_uint,
    POINTER(c_uint), c_uint, c_uint,
    POINTER(c_void_p), POINTER(c_uint), POINTER(c_void_p),
]


class _POINT(Structure):
    _fields_ = [("x", c_int), ("y", c_int)]


class _DXGI_OUTDUPL_PTR_POS(Structure):
    _fields_ = [("Position", _POINT), ("Visible", wt.BOOL)]


class DXGI_OUTDUPL_FRAME_INFO(Structure):
    _fields_ = [
        ("LastPresentTime", ctypes.c_int64), ("LastMouseUpdateTime", ctypes.c_int64),
        ("AccumulatedFrames", c_uint), ("RectsCoalesced", wt.BOOL),
        ("ProtectedContentMaskedOut", wt.BOOL),
        ("PointerPosition", _DXGI_OUTDUPL_PTR_POS),
        ("TotalMetadataBufferSize", c_uint), ("PointerShapeBufferSize", c_uint),
    ]


class DXGI_SAMPLE_DESC(Structure):
    _fields_ = [("Count", c_uint), ("Quality", c_uint)]


class D3D11_TEXTURE2D_DESC(Structure):
    _fields_ = [
        ("Width", c_uint), ("Height", c_uint), ("MipLevels", c_uint),
        ("ArraySize", c_uint), ("Format", c_uint), ("SampleDesc", DXGI_SAMPLE_DESC),
        ("Usage", c_uint), ("BindFlags", c_uint),
        ("CPUAccessFlags", c_uint), ("MiscFlags", c_uint),
    ]


class D3D11_MAPPED_SUBRESOURCE(Structure):
    _fields_ = [("pData", c_void_p), ("RowPitch", c_uint), ("DepthPitch", c_uint)]


class DXGI_OUTPUT_DESC(Structure):
    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32), ("DesktopCoordinates", wt.RECT),
        ("AttachedToDesktop", wt.BOOL), ("Rotation", c_uint), ("Monitor", wt.HANDLE),
    ]


def dxgi_create(monitor_idx: int):
    device = c_void_p()
    context = c_void_p()
    fl = c_uint()
    hr = _d3d11.D3D11CreateDevice(
        None, D3D_DRIVER_TYPE_HARDWARE, None, 0,
        None, 0, D3D11_SDK_VERSION,
        byref(device), byref(fl), byref(context),
    )
    if hr != 0:
        raise OSError(f"D3D11CreateDevice hr=0x{hr & 0xFFFFFFFF:08X}")

    dxgi_dev = com_qi(device, IID_IDXGIDevice)
    adapter = c_void_p()
    hr = com_call(dxgi_dev, 7, HRESULT, [POINTER(c_void_p)], byref(adapter))
    if hr != 0:
        raise OSError(f"GetAdapter hr=0x{hr & 0xFFFFFFFF:08X}")

    output = c_void_p()
    hr = com_call(adapter, 7, HRESULT, [c_uint, POINTER(c_void_p)], monitor_idx, byref(output))
    if hr != 0:
        raise OSError(f"EnumOutputs hr=0x{hr & 0xFFFFFFFF:08X}")

    output1 = com_qi(output, IID_IDXGIOutput1)
    desc = DXGI_OUTPUT_DESC()
    com_call(output1, 7, HRESULT, [POINTER(DXGI_OUTPUT_DESC)], byref(desc))
    cap_left = desc.DesktopCoordinates.left
    cap_top = desc.DesktopCoordinates.top

    dupl = c_void_p()
    hr = com_call(output1, 22, HRESULT, [c_void_p, POINTER(c_void_p)], device, byref(dupl))
    if hr != 0:
        raise OSError(f"DuplicateOutput hr=0x{hr & 0xFFFFFFFF:08X}")

    com_release(dxgi_dev)
    com_release(adapter)
    com_release(output)
    return device, context, output1, dupl, cap_left, cap_top


def dxgi_acquire(dupl, device, context, staging_cache, timeout_ms: int):
    fi = DXGI_OUTDUPL_FRAME_INFO()
    res = c_void_p()
    hr = com_call(
        dupl, 8, HRESULT,
        [c_uint, POINTER(DXGI_OUTDUPL_FRAME_INFO), POINTER(c_void_p)],
        timeout_ms, byref(fi), byref(res),
    )
    if (hr & 0xFFFFFFFF) == DXGI_ERROR_WAIT_TIMEOUT:
        raise TimeoutError("AcquireNextFrame 超时")
    if hr != 0:
        raise OSError(f"AcquireNextFrame hr=0x{hr & 0xFFFFFFFF:08X}")

    tex = com_qi(res, IID_ID3D11Texture2D)
    desc = D3D11_TEXTURE2D_DESC()
    com_call(tex, 10, None, [POINTER(D3D11_TEXTURE2D_DESC)], byref(desc))

    if not staging_cache:
        sd = D3D11_TEXTURE2D_DESC()
        sd.Width, sd.Height = desc.Width, desc.Height
        sd.MipLevels = sd.ArraySize = 1
        sd.Format = desc.Format
        sd.SampleDesc.Count = sd.SampleDesc.Quality = 1
        sd.Usage = D3D11_USAGE_STAGING
        sd.BindFlags = sd.MiscFlags = 0
        sd.CPUAccessFlags = D3D11_CPU_ACCESS_READ
        stg = c_void_p()
        hr = com_call(
            device, 5, HRESULT,
            [POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p)],
            byref(sd), None, byref(stg),
        )
        if hr != 0:
            raise OSError(f"CreateTexture2D hr=0x{hr & 0xFFFFFFFF:08X}")
        staging_cache.append(stg)

    stg = staging_cache[0]
    com_call(context, 47, None, [c_void_p, c_void_p], stg, tex)
    mapped = D3D11_MAPPED_SUBRESOURCE()
    hr = com_call(
        context, 14, HRESULT,
        [c_void_p, c_uint, c_uint, c_uint, POINTER(D3D11_MAPPED_SUBRESOURCE)],
        stg, 0, D3D11_MAP_READ, 0, byref(mapped),
    )
    if hr != 0:
        raise OSError(f"Map hr=0x{hr & 0xFFFFFFFF:08X}")
    return mapped, desc.Width, desc.Height, res, tex, stg


def dxgi_release_frame(context, dupl, stg, tex, res) -> None:
    com_call(context, 15, None, [c_void_p, c_uint], stg, 0)
    com_release(tex)
    com_release(res)
    com_call(dupl, 14, HRESULT, [])


def dxgi_warmup(dupl, device, context, stg_cache, cfg: ScreenshotConfig) -> None:
    for i in range(cfg.warmup_retries):
        try:
            mapped, w, h, res, tex, stg = dxgi_acquire(
                dupl, device, context, stg_cache, cfg.acquire_timeout_ms
            )
            dxgi_release_frame(context, dupl, stg, tex, res)
            print("[+] DXGI 热身帧完成")
            return
        except TimeoutError:
            print(f"[!] DXGI 热身超时，重试 ({i + 1}/{cfg.warmup_retries})")
    print("[!] DXGI 热身多次超时，首帧可能异常")


def dxgi_run_session(cfg: ScreenshotConfig, draw_cursor_fn) -> None:
    device, context, out1, dupl, cap_left, cap_top = dxgi_create(cfg.monitor_index)
    stg_cache: list = []
    dxgi_warmup(dupl, device, context, stg_cache, cfg)
    captured = 0
    try:
        while captured < cfg.capture_count:
            try:
                mapped, w, h, res, tex, stg = dxgi_acquire(
                    dupl, device, context, stg_cache, cfg.acquire_timeout_ms
                )
            except TimeoutError as exc:
                print(f"[!] {exc}，重试...")
                continue

            rp = mapped.RowPitch
            tw = w * cfg.bytes_per_pixel
            rows = [ctypes.string_at(mapped.pData + y * rp, tw) for y in range(h)]
            pix = b"".join(rows)
            if cfg.draw_cursor:
                pix = draw_cursor_fn(pix, w, h, cap_left, cap_top)
            dxgi_release_frame(context, dupl, stg, tex, res)

            out_path = cfg.output_path(captured)
            write_bmp(out_path, w, h, pix, top_down=True)
            print(f"[+] DXGI  第{captured + 1}/{cfg.capture_count}张: {out_path} ({w}x{h})")
            captured += 1
            if cfg.capture_interval_sec > 0 and captured < cfg.capture_count:
                time.sleep(cfg.capture_interval_sec)
    finally:
        if stg_cache:
            com_release(stg_cache[0])
        com_release(dupl)
        com_release(out1)
        com_release(context)
        com_release(device)
