"""Đọc payload chung từ luồng bit; không cần biết chiều dài trước."""
from core.payload import HEADER_SIZE, length, unpack


def bits_from_bytes(data):
    for byte in data:
        for shift in range(7, -1, -1):
            yield (byte >> shift) & 1


def read_payload(bits, available_bits):
    frame = bytearray()
    value = count = 0
    needed = HEADER_SIZE
    for bit in bits:
        value = (value << 1) | bit
        count += 1
        if count != 8:
            continue
        frame.append(value)
        value = count = 0
        if len(frame) == HEADER_SIZE:
            size, _ = length(bytes(frame))
            needed = HEADER_SIZE + size
            if needed * 8 > available_bits:
                raise ValueError('Độ dài không hợp lệ. Kiểm tra thuật toán hoặc ảnh đã bị thay đổi.')
        if len(frame) == needed:
            return unpack(bytes(frame))
    raise ValueError('Ảnh thiếu dữ liệu hoặc không chứa thông điệp STW1.')


def set_channel(image, position, value):
    x, y, channel = position
    pixel = list(image.getpixel((x, y)))
    pixel[channel] = value
    image.putpixel((x, y), tuple(pixel))


def get_channel(image, position):
    x, y, channel = position
    return image.getpixel((x, y))[channel]
