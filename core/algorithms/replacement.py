"""Replacement: thay trực tiếp 1/2/3 bit cuối mỗi mẫu màu."""

def check_k(k):
    if k not in (1,2,3):
        raise ValueError('Replacement chỉ hỗ trợ 1, 2 hoặc 3 LSB.')


def encode(image, data, k=1, mode='sequential', key='', threshold=12):
    from .engine import encode as run
    return run(image, data, 'replacement', k, mode, key, threshold)


def decode(image, k=1, mode='sequential', key='', threshold=12):
    from .engine import decode as run
    return run(image, 'replacement', k, mode, key, threshold)


def capacity(image, k=1, mode='sequential', key='', threshold=12):
    from .engine import capacity as run
    return run(image, 'replacement', k, mode, key, threshold)
