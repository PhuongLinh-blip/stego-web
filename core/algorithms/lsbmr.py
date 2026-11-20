"""LSBMR trên cặp giá trị RGB, có xử lý biên 0/255 và nhóm 8."""
from secrets import choice


def pair_bits(x, y):
    return x & 1, ((x // 2) + y) & 1


def neighbors(value, stable):
    values = [value+delta for delta in (-1,1) if 0 <= value+delta <= 255]
    if stable:
        values = [candidate for candidate in values if (candidate & 248) == (value & 248)]
    return values


def encode_pair(x, y, first, second, stable=False):
    if (x & 1) == first:
        if pair_bits(x,y)[1] == second:
            return x,y
        return x,choice(neighbors(y,stable))
    candidates = neighbors(x,stable)
    for changed_x in candidates:
        if pair_bits(changed_x,y)[1] == second:
            return changed_x,y
    # Khi hướng sửa cần thiết vượt 0..255 hoặc đổi 5 bit cao,
    # sửa cả hai giá trị đi 1. Không gọi đây là bản gốc không đổi.
    return candidates[0],choice(neighbors(y,stable))


def encode(image, data, mode='sequential', key='', threshold=12):
    from .engine import encode as run
    return run(image, data, 'lsbmr', 1, mode, key, threshold)


def decode(image, mode='sequential', key='', threshold=12):
    from .engine import decode as run
    return run(image, 'lsbmr', 1, mode, key, threshold)


def capacity(image, mode='sequential', key='', threshold=12):
    from .engine import capacity as run
    return run(image, 'lsbmr', 1, mode, key, threshold)
