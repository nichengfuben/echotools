from __future__ import annotations

"""Linux XCB/Xlib screenshot backends with CLI fallback."""

import ctypes
import os
import shutil
import subprocess
import time
from ctypes import POINTER, Structure, byref, c_int, c_uint, c_void_p, sizeof

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.shared.bmp import write_bmp
from echotools.plat.capture.shared.platform import load_lib

XCB_IMAGE_FORMAT_Z_PIXMAP = 2
SHM_RDONLY = 0o10000
IPC_PRIVATE = 0
IPC_RMID = 0

_xcb = load_lib("xcb", "libxcb.so.1", "libxcb.so")
_xcb_shm = load_lib("xcb-shm", "libxcb-shm.so.1", "libxcb-shm.so")
_xlib = load_lib("X11", "libX11.so.6", "libX11.so")
_libc = load_lib("c", "libc.so.6", "libc.so")


class xcb_screen_t(Structure):
    _fields_ = [
        ("root", c_uint), ("default_colormap", c_uint),
        ("white_pixel", c_uint), ("black_pixel", c_uint),
        ("current_input_masks", c_uint),
        ("width_in_pixels", ctypes.c_uint16), ("height_in_pixels", ctypes.c_uint16),
        ("width_in_millimeters", ctypes.c_uint16),
        ("height_in_millimeters", ctypes.c_uint16),
        ("min_installed_maps", ctypes.c_uint16),
        ("max_installed_maps", ctypes.c_uint16),
        ("root_visual", c_uint),
        ("backing_stores", ctypes.c_uint8), ("save_unders", ctypes.c_uint8),
        ("root_depth", ctypes.c_uint8), ("allowed_depths_len", ctypes.c_uint8),
    ]


class _setup_head(Structure):
    _fields_ = [
        ("status", ctypes.c_uint8), ("pad0", ctypes.c_uint8),
        ("protocol_major", ctypes.c_uint16), ("protocol_minor", ctypes.c_uint16),
        ("length", ctypes.c_uint16), ("release_number", c_uint),
        ("resource_id_base", c_uint), ("resource_id_mask", c_uint),
        ("motion_buffer", c_uint), ("vendor_len", ctypes.c_uint16),
        ("max_req_len", ctypes.c_uint16), ("roots_len", ctypes.c_uint8),
        ("pixmap_formats_len", ctypes.c_uint8),
        ("image_byte_order", ctypes.c_uint8), ("bitmap_format", ctypes.c_uint8),
        ("bitmap_scanline_unit", ctypes.c_uint8),
        ("bitmap_scanline_pad", ctypes.c_uint8),
        ("min_keycode", ctypes.c_uint8), ("max_keycode", ctypes.c_uint8),
        ("pad1", ctypes.c_uint8 * 4),
    ]


class XImage_head(Structure):
    _fields_ = [
        ("width", c_int), ("height", c_int), ("xoffset", c_int), ("format", c_int),
        ("data", c_void_p), ("byte_order", c_int), ("bitmap_unit", c_int),
        ("bitmap_bit_order", c_int), ("bitmap_pad", c_int), ("depth", c_int),
        ("bytes_per_line", c_int), ("bits_per_pixel", c_int),
    ]


_XLIB_ALL_PLANES = ctypes.c_ulong(-1).value
_XLIB_ZPIXMAP = 2


def _bind_xlib_prototypes() -> None:
    if not _xlib:
        return
    _xlib.XOpenDisplay.restype = c_void_p
    _xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    _xlib.XDefaultScreen.restype = c_int
    _xlib.XDefaultScreen.argtypes = [c_void_p]
    _xlib.XRootWindow.restype = ctypes.c_ulong
    _xlib.XRootWindow.argtypes = [c_void_p, c_int]
    _xlib.XDisplayWidth.restype = c_int
    _xlib.XDisplayWidth.argtypes = [c_void_p, c_int]
    _xlib.XDisplayHeight.restype = c_int
    _xlib.XDisplayHeight.argtypes = [c_void_p, c_int]
    _xlib.XGetImage.restype = c_void_p
    _xlib.XGetImage.argtypes = [
        c_void_p, ctypes.c_ulong, c_int, c_int, c_uint, c_uint, ctypes.c_ulong, c_int,
    ]
    _xlib.XDestroyImage.restype = c_int
    _xlib.XDestroyImage.argtypes = [c_void_p]
    _xlib.XCloseDisplay.argtypes = [c_void_p]


_bind_xlib_prototypes()


def _xlib_grab_pixels(dpy) -> tuple[int, int, bytes]:
    if _xlib is None:
        raise OSError("libX11 不可用")
    scr = _xlib.XDefaultScreen(dpy)
    root = _xlib.XRootWindow(dpy, scr)
    w = _xlib.XDisplayWidth(dpy, scr)
    h = _xlib.XDisplayHeight(dpy, scr)
    img_ptr = _xlib.XGetImage(dpy, root, 0, 0, w, h, _XLIB_ALL_PLANES, _XLIB_ZPIXMAP)
    if not img_ptr:
        raise OSError("XGetImage 返回 NULL")
    img = XImage_head.from_address(img_ptr)
    bpl = img.bytes_per_line
    dp = img.data
    rows = [ctypes.string_at(dp + y * bpl, w * 4) for y in range(h)]
    raw = b"".join(rows)
    _xlib.XDestroyImage(img_ptr)
    return w, h, raw


if _xcb:
    _xcb.xcb_connect.restype = c_void_p
    _xcb.xcb_connect.argtypes = [ctypes.c_char_p, POINTER(c_int)]
    _xcb.xcb_disconnect.argtypes = [c_void_p]
    _xcb.xcb_get_setup.restype = c_void_p
    _xcb.xcb_get_setup.argtypes = [c_void_p]
    _xcb.xcb_generate_id.restype = c_uint
    _xcb.xcb_generate_id.argtypes = [c_void_p]

if _libc:
    _libc.shmget.restype = c_int
    _libc.shmget.argtypes = [c_int, ctypes.c_size_t, c_int]
    _libc.shmat.restype = c_void_p
    _libc.shmat.argtypes = [c_int, c_void_p, c_int]
    _libc.shmdt.restype = c_int
    _libc.shmdt.argtypes = [c_void_p]
    _libc.shmctl.restype = c_int
    _libc.shmctl.argtypes = [c_int, c_int, c_void_p]


def _xcb_connect():
    if not _xcb:
        raise OSError("libxcb 不可用")
    screen_num = c_int(0)
    conn = _xcb.xcb_connect(None, byref(screen_num))
    if not conn:
        raise OSError("xcb_connect 失败")
    return conn, screen_num.value


def _xcb_get_root_screen(conn, screen_num: int) -> xcb_screen_t:
    if _xcb is None:
        raise OSError("libxcb 不可用")
    setup = _xcb.xcb_get_setup(conn)
    head = _setup_head.from_address(setup)
    vendor_len_padded = (head.vendor_len + 3) & ~3
    formats_size = head.pixmap_formats_len * 8
    screens_offset = sizeof(_setup_head) + vendor_len_padded + formats_size
    for i in range(screen_num + 1):
        scr = xcb_screen_t.from_address(setup + screens_offset)
        if i == screen_num:
            return scr
        break
    return xcb_screen_t.from_address(setup + screens_offset)


def _fill_alpha(raw: bytes) -> bytes:
    buf = bytearray(raw)
    for i in range(3, len(buf), 4):
        buf[i] = 0xFF
    return bytes(buf)


def xcb_shm_screenshot(out_path: str) -> None:
    if not _xcb or not _xcb_shm or not _libc:
        raise OSError("XCB/SHM 库不可用")
    conn, _ = _xcb_connect()
    try:
        scr = _xcb_get_root_screen(conn, 0)
        w, h = scr.width_in_pixels, scr.height_in_pixels
        sz = w * h * 4
        shmid = _libc.shmget(IPC_PRIVATE, sz, 0o600)
        if shmid < 0:
            raise OSError(f"shmget 失败 errno={ctypes.get_errno()}")
        addr = _libc.shmat(shmid, None, 0)
        if addr == ctypes.c_size_t(-1).value:
            _libc.shmctl(shmid, IPC_RMID, None)
            raise OSError("shmat 失败")

        shmseg = _xcb.xcb_generate_id(conn)
        _xcb_shm.xcb_shm_attach.restype = c_uint
        _xcb_shm.xcb_shm_attach.argtypes = [c_void_p, c_uint, c_uint, ctypes.c_uint8]
        _xcb_shm.xcb_shm_get_image.restype = c_void_p
        _xcb_shm.xcb_shm_get_image.argtypes = [
            c_void_p, c_uint, c_int, c_int, ctypes.c_uint16, ctypes.c_uint16,
            c_uint, ctypes.c_uint8, c_uint, c_uint,
        ]
        _xcb_shm.xcb_shm_get_image_reply.restype = c_void_p
        _xcb_shm.xcb_shm_get_image_reply.argtypes = [c_void_p, c_void_p, c_void_p]
        _xcb_shm.xcb_shm_detach.restype = c_uint
        _xcb_shm.xcb_shm_detach.argtypes = [c_void_p, c_uint]

        _xcb_shm.xcb_shm_attach(conn, shmseg, shmid, 0)
        cookie = _xcb_shm.xcb_shm_get_image(
            conn, scr.root, 0, 0, w, h, 0xFFFFFFFF, XCB_IMAGE_FORMAT_Z_PIXMAP, shmseg, 0
        )
        reply = _xcb_shm.xcb_shm_get_image_reply(conn, cookie, None)
        if not reply:
            raise OSError("xcb_shm_get_image_reply 返回 NULL")
        _libc.free(reply)

        raw = ctypes.string_at(addr, sz)
        _xcb_shm.xcb_shm_detach(conn, shmseg)
        _libc.shmdt(addr)
        _libc.shmctl(shmid, IPC_RMID, None)
        write_bmp(out_path, w, h, _fill_alpha(raw), top_down=True)
    finally:
        _xcb.xcb_disconnect(conn)


def xcb_getimage_screenshot(out_path: str) -> None:
    if not _xcb:
        raise OSError("libxcb 不可用")
    _xcb.xcb_get_image.restype = c_void_p
    _xcb.xcb_get_image.argtypes = [
        c_void_p, ctypes.c_uint8, c_uint, c_int, c_int,
        ctypes.c_uint16, ctypes.c_uint16, c_uint,
    ]
    _xcb.xcb_get_image_reply.restype = c_void_p
    _xcb.xcb_get_image_reply.argtypes = [c_void_p, c_void_p, c_void_p]
    _xcb.xcb_get_image_data.restype = POINTER(ctypes.c_ubyte)
    _xcb.xcb_get_image_data.argtypes = [c_void_p]
    _xcb.xcb_get_image_data_length.restype = c_int
    _xcb.xcb_get_image_data_length.argtypes = [c_void_p]

    conn, _ = _xcb_connect()
    try:
        scr = _xcb_get_root_screen(conn, 0)
        w, h = scr.width_in_pixels, scr.height_in_pixels
        cookie = _xcb.xcb_get_image(
            conn, XCB_IMAGE_FORMAT_Z_PIXMAP, scr.root, 0, 0, w, h, 0xFFFFFFFF
        )
        reply = _xcb.xcb_get_image_reply(conn, cookie, None)
        if not reply:
            raise OSError("xcb_get_image_reply 返回 NULL")
        length = _xcb.xcb_get_image_data_length(reply)
        data_ptr = _xcb.xcb_get_image_data(reply)
        raw = bytes(data_ptr[:length])
        if _libc:
            _libc.free(reply)
        write_bmp(out_path, w, h, _fill_alpha(raw), top_down=True)
    finally:
        _xcb.xcb_disconnect(conn)


def xlib_screenshot(out_path: str) -> None:
    if not _xlib:
        raise OSError("libX11 不可用")
    dpy = _xlib.XOpenDisplay(None)
    if not dpy:
        raise OSError("XOpenDisplay 失败（DISPLAY 未设置？）")
    try:
        w, h, raw = _xlib_grab_pixels(dpy)
        write_bmp(out_path, w, h, _fill_alpha(raw), top_down=True)
    finally:
        _xlib.XCloseDisplay(dpy)


def cmdline_screenshot(out_path: str) -> None:
    png_path = out_path.rsplit(".", 1)[0] + ".png"
    tools = [
        ["scrot", "-z", png_path],
        ["gnome-screenshot", "-f", png_path],
        ["import", "-window", "root", png_path],
    ]
    for cmd in tools:
        if not shutil.which(cmd[0]):
            continue
        try:
            ret = subprocess.run(
                cmd, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if ret.returncode == 0 and os.path.exists(png_path):
                if png_path != out_path:
                    os.replace(png_path, out_path)
                return
        except Exception:
            continue
    raise OSError("所有命令行截图工具均不可用或失败")


def linux_capture_session(cfg: ScreenshotConfig) -> None:
    methods = [
        ("XCB+SHM", xcb_shm_screenshot),
        ("XCB", xcb_getimage_screenshot),
        ("Xlib", xlib_screenshot),
        ("命令行", cmdline_screenshot),
    ]
    for i in range(cfg.capture_count):
        out_path = cfg.output_path(i)
        captured = False
        last_err: Exception | None = None
        for name, fn in methods:
            try:
                path = out_path if cfg.output_ext == "bmp" else cfg.output_path(i, "png")
                fn(path)
                print(f"[+] {name:<10} 第{i + 1}/{cfg.capture_count}张: {path}")
                captured = True
                break
            except Exception as exc:
                last_err = exc
                print(f"[!] {name} 失败: {exc}")
        if not captured:
            raise RuntimeError(f"Linux 第{i + 1}张截图所有方案均失败: {last_err}")
        if cfg.capture_interval_sec > 0 and i < cfg.capture_count - 1:
            time.sleep(cfg.capture_interval_sec)
