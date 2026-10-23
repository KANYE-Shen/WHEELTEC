"""Sample a visible Gazebo X11 window for disappearing 3D frames (run in WSL)."""
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from PIL import Image


class XImage(ct.Structure):
    _fields_ = [
        ('width', ct.c_int), ('height', ct.c_int), ('xoffset', ct.c_int),
        ('format', ct.c_int), ('data', ct.c_void_p), ('byte_order', ct.c_int),
        ('bitmap_unit', ct.c_int), ('bitmap_bit_order', ct.c_int),
        ('bitmap_pad', ct.c_int), ('depth', ct.c_int),
        ('bytes_per_line', ct.c_int), ('bits_per_pixel', ct.c_int),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-id', help='X11 id from xwininfo -root -tree')
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--interval', type=float, default=.025)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.frames < 1 or args.interval < 0:
        parser.error('frames must be positive and interval nonnegative')
    tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
    windows = re.findall(r'(0x[\da-f]+) "Gazebo":.*? (\d+)x(\d+)[+-]', tree)
    candidates = [w for w in windows if not args.window_id or w[0] == args.window_id]
    if len(candidates) != 1:
        parser.error('Expected one Gazebo window; specify --window-id when several are open')
    window, width, height = candidates[0]
    width, height = int(width), int(height)
    args.output.mkdir(parents=True, exist_ok=True)
    x11 = ct.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ct.c_char_p]
    x11.XOpenDisplay.restype = ct.c_void_p
    x11.XGetImage.argtypes = [ct.c_void_p, ct.c_ulong, ct.c_int, ct.c_int,
                             ct.c_uint, ct.c_uint, ct.c_ulong, ct.c_int]
    x11.XGetImage.restype = ct.POINTER(XImage)
    x11.XDestroyImage.argtypes = [ct.POINTER(XImage)]
    x11.XCloseDisplay.argtypes = [ct.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('Cannot open the X11 display')
    records, saved = [], set()
    unique_images = set()
    started = time.monotonic()
    try:
        for index in range(args.frames):
            frame = x11.XGetImage(display, int(window, 16), 0, 0, width, height,
                                 0xffffffff, 2)
            if not frame:
                raise RuntimeError('Cannot read Gazebo frame; keep the window open')
            try:
                raw = frame.contents
                if raw.bits_per_pixel != 32 or raw.byte_order != 0:
                    raise RuntimeError('This check requires little-endian 32-bit X11 pixels')
                image = Image.frombytes('RGB', (width, height),
                                        ct.string_at(raw.data, raw.bytes_per_line * height),
                                        'raw', 'BGRX', raw.bytes_per_line)
            finally:
                x11.XDestroyImage(frame)
            # Omit toolbar and statistics. At the default room view this region
            # contains floor, walls and furniture; a missing scene is solid color.
            region = image.crop((int(width*.1), int(height*.25),
                                 int(width*.9), int(height*.9))).resize((160, 100))
            unique_images.add(hashlib.sha256(region.tobytes()).hexdigest())
            colors = region.getcolors(16000)
            dominant = max(count for count, _ in colors) / 16000
            blank = dominant > .97
            pixels = list(region.getdata())
            material_pixels = {
                'floor': sum(min(r, g, b) > 220 for r, g, b in pixels),
                'cabinet': sum(g > r*1.2 and g > b*1.05 for r, g, b in pixels),
                'furniture': sum(r > g*1.2 and g > b*1.2 for r, g, b in pixels),
            }
            # Check distinct room objects as well as a solid-color failure:
            # MSAA=0 alone can hide the latter while models still disappear.
            incomplete = any(count < 20 for count in material_pixels.values())
            kind = 'blank' if blank else 'incomplete' if incomplete else 'scene'
            if kind not in saved:
                image.save(args.output / (kind + '.png'))
                saved.add(kind)
            records.append({'frame': index, 'seconds': time.monotonic()-started,
                            'colors': len(colors), 'dominant_fraction': dominant,
                            'blank': blank, 'incomplete': incomplete,
                            'material_pixels': material_pixels})
            time.sleep(args.interval)
    finally:
        x11.XCloseDisplay(display)
    result = {'window_id': window, 'frames': len(records),
              'blank_frames': sum(r['blank'] for r in records),
              'incomplete_frames': sum(r['incomplete'] for r in records),
              'duration_seconds': time.monotonic()-started,
              'unique_scene_images': len(unique_images),
              'method': 'XGetImage; solid color and default-view floor/cabinet/furniture presence',
              'min_colors': min(r['colors'] for r in records),
              'max_colors': max(r['colors'] for r in records),
              'records': records}
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}))
    return 1 if result['blank_frames'] or result['incomplete_frames'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
