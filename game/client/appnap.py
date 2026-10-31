"""Keep macOS from napping the game while it hosts or joins a co-op game (no pygame).

macOS "App Nap" throttles apps whose window is in the background: timers and network waits can be
delayed by up to ~10 seconds. The co-op host runs the game server inside the game's process, so a napping
host freezes every player. NSProcessInfo.beginActivityWithOptions:reason: tells macOS this is
user-initiated, latency-critical work. Called through the Objective-C runtime with ctypes (no extra
packages). Does nothing on Windows/Linux, and never raises.
"""
import ctypes
import ctypes.util
import sys

_NS_ACTIVITY_USER_INITIATED_ALLOWING_IDLE_SYSTEM_SLEEP = 0x00FFFFFF & ~(1 << 20)
_NS_ACTIVITY_LATENCY_CRITICAL = 0xFF00000000

_activity = None   # keep the activity object alive for the whole process


def prevent_app_nap(reason="Hosting a co-op game"):
    """Returns a truthy token if macOS accepted the request, None otherwise (other OS or failure)."""
    global _activity
    if _activity is not None:
        return _activity
    if sys.platform != "darwin":
        return None
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

        def msg(restype, *argtypes):
            return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(send)

        sel = objc.sel_registerName
        info = msg(ctypes.c_void_p)(objc.objc_getClass(b"NSProcessInfo"), sel(b"processInfo"))
        text = msg(ctypes.c_void_p, ctypes.c_char_p)(objc.objc_getClass(b"NSString"),
                                                     sel(b"stringWithUTF8String:"), reason.encode("utf-8"))
        options = _NS_ACTIVITY_USER_INITIATED_ALLOWING_IDLE_SYSTEM_SLEEP | _NS_ACTIVITY_LATENCY_CRITICAL
        activity = msg(ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p)(
            info, sel(b"beginActivityWithOptions:reason:"), options, text)
        if activity:
            msg(ctypes.c_void_p)(activity, sel(b"retain"))   # held until the process exits
            _activity = activity
        return _activity
    except Exception:   # never break the game over this
        return None
