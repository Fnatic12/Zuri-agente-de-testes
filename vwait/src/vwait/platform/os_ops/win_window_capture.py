from __future__ import annotations

import os
from typing import Any

from PIL import Image

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    USER32 = ctypes.windll.user32
    GDI32 = ctypes.windll.gdi32
    PW_RENDERFULLCONTENT = 0x00000002
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class RGBQUAD(ctypes.Structure):
        _fields_ = [
            ("rgbBlue", ctypes.c_ubyte),
            ("rgbGreen", ctypes.c_ubyte),
            ("rgbRed", ctypes.c_ubyte),
            ("rgbReserved", ctypes.c_ubyte),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]

else:
    ctypes = None
    wintypes = None
    USER32 = None
    GDI32 = None
    PW_RENDERFULLCONTENT = 0x00000002
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    POINT = None
    RECT = None
    BITMAPINFOHEADER = None
    BITMAPINFO = None


def _window_rect(hwnd: Any) -> tuple[int, int, int, int] | None:
    if not USER32 or not hwnd or RECT is None:
        return None
    rect = RECT()
    if not USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left = int(rect.left)
    top = int(rect.top)
    right = int(rect.right)
    bottom = int(rect.bottom)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _window_client_bbox(hwnd: Any) -> tuple[int, int, int, int] | None:
    if not USER32 or not hwnd or RECT is None or POINT is None:
        return None
    rect = RECT()
    if not USER32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    top_left = POINT(0, 0)
    bottom_right = POINT(rect.right, rect.bottom)
    if not USER32.ClientToScreen(hwnd, ctypes.byref(top_left)):
        return None
    if not USER32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
        return None
    left = int(top_left.x)
    top = int(top_left.y)
    right = int(bottom_right.x)
    bottom = int(bottom_right.y)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def capture_window_client_image(hwnd: Any) -> Image.Image | None:
    if os.name != "nt" or USER32 is None or GDI32 is None or not hwnd:
        return None

    window_rect = _window_rect(hwnd)
    if not window_rect:
        return None
    window_width = max(0, int(window_rect[2] - window_rect[0]))
    window_height = max(0, int(window_rect[3] - window_rect[1]))
    if window_width <= 0 or window_height <= 0:
        return None

    hwnd_dc = USER32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None

    mem_dc = GDI32.CreateCompatibleDC(hwnd_dc)
    bitmap = GDI32.CreateCompatibleBitmap(hwnd_dc, window_width, window_height)
    old_bitmap = None
    try:
        if not mem_dc or not bitmap:
            return None
        old_bitmap = GDI32.SelectObject(mem_dc, bitmap)
        rendered = USER32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
        if not rendered:
            rendered = USER32.PrintWindow(hwnd, mem_dc, 0)
        if not rendered:
            return None

        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = window_width
        bitmap_info.bmiHeader.biHeight = -window_height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB
        buffer = ctypes.create_string_buffer(window_width * window_height * 4)
        scanlines = GDI32.GetDIBits(
            mem_dc,
            bitmap,
            0,
            window_height,
            buffer,
            ctypes.byref(bitmap_info),
            DIB_RGB_COLORS,
        )
        if int(scanlines or 0) != window_height:
            return None
        image = Image.frombuffer(
            "RGBA",
            (window_width, window_height),
            buffer,
            "raw",
            "BGRA",
            0,
            1,
        ).copy()
    finally:
        if old_bitmap:
            GDI32.SelectObject(mem_dc, old_bitmap)
        if bitmap:
            GDI32.DeleteObject(bitmap)
        if mem_dc:
            GDI32.DeleteDC(mem_dc)
        USER32.ReleaseDC(hwnd, hwnd_dc)

    client_bbox = _window_client_bbox(hwnd)
    if not client_bbox:
        return image

    crop_left = max(0, int(client_bbox[0] - window_rect[0]))
    crop_top = max(0, int(client_bbox[1] - window_rect[1]))
    crop_right = min(window_width, int(client_bbox[2] - window_rect[0]))
    crop_bottom = min(window_height, int(client_bbox[3] - window_rect[1]))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        return image
    return image.crop((crop_left, crop_top, crop_right, crop_bottom))
