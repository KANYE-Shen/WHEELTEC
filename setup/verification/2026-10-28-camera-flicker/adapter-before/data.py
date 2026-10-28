import math


def finite_ranges(ranges, minimum, maximum):
    return [float(x) if math.isfinite(x) and minimum <= x <= maximum else None for x in ranges]


def grid_payload(width, height, data):
    if width*height != len(data) or width <= 0 or height <= 0:
        raise ValueError('Invalid OccupancyGrid shape')
    return list(data)


def jpeg_from_image(msg):
    if msg.encoding not in ('rgb8', 'bgr8', 'mono8', 'rgba8', 'bgra8'):
        raise ValueError('Unsupported image encoding')
    import cv2
    import numpy as np
    channels = {'rgb8': 3, 'bgr8': 3, 'mono8': 1,
                'rgba8': 4, 'bgra8': 4}[msg.encoding]
    a = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(
        msg.height, msg.step)[:, :msg.width*channels]
    a = a.reshape(msg.height, msg.width, channels) if channels > 1 else a.reshape(
        msg.height, msg.width)
    if msg.encoding == 'rgb8':
        a = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    elif msg.encoding == 'rgba8':
        a = cv2.cvtColor(a, cv2.COLOR_RGBA2BGR)
    elif msg.encoding == 'bgra8':
        a = cv2.cvtColor(a, cv2.COLOR_BGRA2BGR)
    h, w = a.shape[:2]
    if w > 960:
        a = cv2.resize(a, (960, int(h*960/w)))
    ok, jpeg = cv2.imencode('.jpg', a, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ok:
        raise ValueError('JPEG conversion failed')
    return jpeg.tobytes()


def fresh_measurement(stamp, ros_now, received, wall_now, limit):
    return stamp is not None and stamp > 0 and received is not None and 0 <= wall_now-received <= limit and -.1 <= ros_now-stamp <= limit


def tf_chain_fresh(edges, source, target, wall_now, limit=1.):
    visited = {source}
    pending = [source]
    while pending:
        frame = pending.pop()
        if frame == target:
            return True
        for (a, b), (received, static) in edges.items():
            if not static and not 0 <= wall_now-received <= limit:
                continue
            other = b if a == frame else a if b == frame else None
            if other is not None and other not in visited:
                visited.add(other)
                pending.append(other)
    return False
