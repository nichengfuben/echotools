from __future__ import annotations

"""macOS AudioQueue audio recording."""

import ctypes
import ctypes.util
import threading
import time
from ctypes import POINTER, Structure, byref, c_double, c_uint, c_void_p, sizeof

from echotools.plat.capture.audio_record.config import AudioRecordConfig

_at_path = (
    ctypes.util.find_library("AudioToolbox")
    or "/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox"
)
_ca_path = (
    ctypes.util.find_library("CoreAudio")
    or "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
)
_AT = ctypes.CDLL(_at_path)
_CA = ctypes.CDLL(_ca_path)

kAudioFormatLinearPCM = 0x6C70636D
kLinearPCMFormatFlagIsSignedInteger = 0x4
kLinearPCMFormatFlagIsPacked = 0x8
kAudioObjectPropertyScopeGlobal = 0x676C6F62
kAudioObjectPropertyElementMaster = 0
kAudioHardwarePropertyDevices = 0x64657623
kAudioDevicePropertyDeviceName = 0x6E616D65
kAudioObjectSystemObject = 1

OSStatus = ctypes.c_int32
AudioQueueRef = c_void_p
AudioObjectID = c_uint


class AudioStreamBasicDescription(Structure):
    _fields_ = [
        ("mSampleRate", c_double), ("mFormatID", c_uint),
        ("mFormatFlags", c_uint), ("mBytesPerPacket", c_uint),
        ("mFramesPerPacket", c_uint), ("mBytesPerFrame", c_uint),
        ("mChannelsPerFrame", c_uint), ("mBitsPerChannel", c_uint),
        ("mReserved", c_uint),
    ]


class AudioQueueBuffer(Structure):
    _fields_ = [
        ("mAudioDataBytesCapacity", c_uint), ("mAudioData", c_void_p),
        ("mAudioDataByteSize", c_uint), ("mUserData", c_void_p),
        ("mPacketDescriptionCapacity", c_uint),
        ("mPacketDescriptions", c_void_p), ("mPacketDescriptionCount", c_uint),
    ]


class AudioObjectPropertyAddress(Structure):
    _fields_ = [("mSelector", c_uint), ("mScope", c_uint), ("mElement", c_uint)]


AudioQueueBufferRef = POINTER(AudioQueueBuffer)

_AT.AudioQueueNewInput.restype = OSStatus
_AT.AudioQueueNewInput.argtypes = [
    POINTER(AudioStreamBasicDescription), c_void_p, c_void_p,
    c_void_p, c_void_p, c_uint, POINTER(AudioQueueRef),
]
_AT.AudioQueueAllocateBuffer.restype = OSStatus
_AT.AudioQueueAllocateBuffer.argtypes = [AudioQueueRef, c_uint, POINTER(AudioQueueBufferRef)]
_AT.AudioQueueEnqueueBuffer.restype = OSStatus
_AT.AudioQueueEnqueueBuffer.argtypes = [AudioQueueRef, AudioQueueBufferRef, c_uint, c_void_p]
_AT.AudioQueueStart.restype = OSStatus
_AT.AudioQueueStart.argtypes = [AudioQueueRef, c_void_p]
_AT.AudioQueueStop.restype = OSStatus
_AT.AudioQueueStop.argtypes = [AudioQueueRef, ctypes.c_bool]
_AT.AudioQueueDispose.restype = OSStatus
_AT.AudioQueueDispose.argtypes = [AudioQueueRef, ctypes.c_bool]
_CA.AudioObjectGetPropertyData.restype = OSStatus
_CA.AudioObjectGetPropertyData.argtypes = [
    AudioObjectID, POINTER(AudioObjectPropertyAddress),
    c_uint, c_void_p, POINTER(c_uint), c_void_p,
]
_CA.AudioObjectGetPropertyDataSize.restype = OSStatus
_CA.AudioObjectGetPropertyDataSize.argtypes = [
    AudioObjectID, POINTER(AudioObjectPropertyAddress),
    c_uint, c_void_p, POINTER(c_uint),
]


def _ca_get_all_devices() -> list[tuple[int, str]]:
    prop = AudioObjectPropertyAddress(
        kAudioHardwarePropertyDevices,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMaster,
    )
    sz = c_uint(0)
    _CA.AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, byref(prop), 0, None, byref(sz))
    n = sz.value // sizeof(AudioObjectID)
    ids = (AudioObjectID * n)()
    _CA.AudioObjectGetPropertyData(kAudioObjectSystemObject, byref(prop), 0, None, byref(sz), ids)
    result: list[tuple[int, str]] = []
    for did in ids:
        np = AudioObjectPropertyAddress(
            kAudioDevicePropertyDeviceName,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMaster,
        )
        buf = ctypes.create_string_buffer(256)
        bufsz = c_uint(256)
        _CA.AudioObjectGetPropertyData(did, byref(np), 0, None, byref(bufsz), buf)
        result.append((did, buf.value.decode("utf-8", errors="replace")))
    return result


def _ca_find_device_id(name_hint: str) -> int | None:
    if name_hint.lower() == "default":
        return None
    hint = name_hint.lower()
    for did, nm in _ca_get_all_devices():
        if hint in nm.lower():
            return did
    return None


def _build_asbd(cfg: AudioRecordConfig) -> AudioStreamBasicDescription:
    asbd = AudioStreamBasicDescription()
    asbd.mSampleRate = float(cfg.sample_rate)
    asbd.mFormatID = kAudioFormatLinearPCM
    asbd.mFormatFlags = kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked
    asbd.mBytesPerPacket = cfg.frame_bytes
    asbd.mFramesPerPacket = 1
    asbd.mBytesPerFrame = cfg.frame_bytes
    asbd.mChannelsPerFrame = cfg.channels
    asbd.mBitsPerChannel = cfg.bit_depth
    asbd.mReserved = 0
    return asbd


def _set_aq_device(aq_ref: AudioQueueRef, did: int) -> None:
    kAudioQueueProperty_CurrentDevice = 0x63737264
    _AT.AudioQueueSetProperty.restype = OSStatus
    _AT.AudioQueueSetProperty.argtypes = [AudioQueueRef, c_uint, c_void_p, c_uint]
    dev_id = AudioObjectID(did)
    _AT.AudioQueueSetProperty(
        aq_ref, kAudioQueueProperty_CurrentDevice, byref(dev_id), sizeof(AudioObjectID)
    )


def _enqueue_aq_buffers(aq_ref: AudioQueueRef, cfg: AudioRecordConfig) -> None:
    buf_size = cfg.buffer_frames * cfg.frame_bytes
    for _ in range(3):
        br = AudioQueueBufferRef()
        _AT.AudioQueueAllocateBuffer(aq_ref, buf_size, byref(br))
        _AT.AudioQueueEnqueueBuffer(aq_ref, br, 0, None)


def aq_record_device(name_hint: str, cfg: AudioRecordConfig) -> bytes:
    asbd = _build_asbd(cfg)
    chunks: list[bytes] = []
    lock = threading.Lock()
    aq_ref = AudioQueueRef()

    CALLBACK_TYPE = ctypes.CFUNCTYPE(
        None, c_void_p, AudioQueueRef, AudioQueueBufferRef, c_void_p, c_uint, c_void_p,
    )

    def _callback(user_data, aq, buf_ref, start_time, n_pkts, pkt_descs):
        buf = buf_ref.contents
        if buf.mAudioDataByteSize > 0:
            data = ctypes.string_at(buf.mAudioData, buf.mAudioDataByteSize)
            with lock:
                chunks.append(data)
        _AT.AudioQueueEnqueueBuffer(aq, buf_ref, 0, None)

    c_callback = CALLBACK_TYPE(_callback)
    st = _AT.AudioQueueNewInput(byref(asbd), c_callback, None, None, None, 0, byref(aq_ref))
    if st != 0:
        raise OSError(f"AudioQueueNewInput 失败 st={st}")

    did = _ca_find_device_id(name_hint)
    if did is not None:
        _set_aq_device(aq_ref, did)

    _enqueue_aq_buffers(aq_ref, cfg)
    _AT.AudioQueueStart(aq_ref, None)
    time.sleep(cfg.record_seconds)
    _AT.AudioQueueStop(aq_ref, True)
    _AT.AudioQueueDispose(aq_ref, True)
    with lock:
        return b"".join(chunks)


def mac_record_session(cfg: AudioRecordConfig) -> list[bytes]:
    names = cfg.device_names if cfg.device_names else ["default"]
    streams: list[bytes] = []
    for name in names:
        print(f"[*] macOS 开始录制设备: '{name}'  ({cfg.record_seconds}s)")
        try:
            pcm = aq_record_device(name, cfg)
            streams.append(pcm)
            print(f"[+] AudioQueue 录制完成: '{name}'  {len(pcm)} bytes")
        except Exception as exc:
            raise RuntimeError(f"macOS 设备 '{name}' 录制失败: {exc}") from exc
    return streams
