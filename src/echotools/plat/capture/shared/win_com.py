from __future__ import annotations

"""Windows COM vtable helpers shared by capture backends."""

from ctypes import (
    POINTER,
    WINFUNCTYPE,
    Structure,
    byref,
    c_int,
    c_ubyte,
    c_ulong,
    c_ushort,
    c_void_p,
    cast,
    sizeof,
)

HRESULT = c_int
PTR_SIZE = sizeof(c_void_p)


class GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


def make_guid(s: str) -> GUID:
    parts = s.strip("{}").split("-")
    d1, d2, d3 = int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
    hi, lo = int(parts[3], 16), int(parts[4], 16)
    d4 = (c_ubyte * 8)()
    d4[0], d4[1] = (hi >> 8) & 0xFF, hi & 0xFF
    for i in range(6):
        d4[2 + i] = (lo >> (40 - 8 * i)) & 0xFF
    return GUID(d1, d2, d3, d4)


def com_call(ptr, idx: int, restype, argtypes, *args):
    vtable = cast(ptr, POINTER(c_void_p)).contents.value
    if not vtable:
        raise OSError("null COM vtable")
    fn_addr = cast(vtable + idx * PTR_SIZE, POINTER(c_void_p))[0]
    fn = WINFUNCTYPE(restype, c_void_p, *argtypes)(fn_addr)
    return fn(ptr, *args)


def com_release(ptr) -> None:
    if ptr:
        com_call(ptr, 2, c_ulong, [])


def com_qi(ptr, iid: GUID):
    out = c_void_p()
    hr = com_call(
        ptr,
        0,
        HRESULT,
        [POINTER(GUID), POINTER(c_void_p)],
        byref(iid),
        byref(out),
    )
    if hr != 0 or not out:
        raise OSError(f"QueryInterface hr=0x{hr & 0xFFFFFFFF:08X}")
    return out
