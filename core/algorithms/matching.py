"""LSB Matching; giữ nguyên 5 bit cao nếu dùng vị trí thích nghi/biên."""
from secrets import choice


def match_value(value, bit, stable=False):
    if (value & 1) == bit:
        return value
    candidates = [value+delta for delta in (-1,1) if 0 <= value+delta <= 255]
    if stable:
        candidates = [candidate for candidate in candidates if (candidate & 248) == (value & 248)]
    return value + choice([candidate-value for candidate in candidates])


def encode(image, data, mode='sequential', key='', threshold=12):
    from .engine import encode as run
    return run(image, data, 'matching', 1, mode, key, threshold)


def decode(image, mode='sequential', key='', threshold=12):
    from .engine import decode as run
    return run(image, 'matching', 1, mode, key, threshold)


def capacity(image, mode='sequential', key='', threshold=12):
    from .engine import capacity as run
    return run(image, 'matching', 1, mode, key, threshold)
