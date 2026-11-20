import struct  # Chuyển các số thành byte và đọc byte trở lại thành số.
import zlib    # Dùng hàm CRC32 để tính mã kiểm tra dữ liệu.


# Phần đầu gói dữ liệu dài 12 byte:
# 4 byte dấu nhận diện + 4 byte độ dài + 4 byte CRC32.
HEADER_SIZE = 12


def pack(data):
    """Đóng gói dữ liệu byte trước khi nhúng vào ảnh."""

    # Cấu trúc gói:
    # [STW1: 4 byte] [Độ dài: 4 byte] [CRC32: 4 byte] [Nội dung]
    #
    # b'STW1': dấu nhận diện định dạng do ứng dụng quy ước.
    # len(data): số byte của nội dung, không phải số ký tự.
    # zlib.crc32(data): mã kiểm tra dùng để phát hiện dữ liệu bị thay đổi.
    #
    # '>II':
    #   > : big-endian, ghi byte có trọng số lớn trước.
    #   I : số nguyên không dấu 4 byte.
    #   II: hai số, tổng cộng 8 byte.
    return (
        b'STW1'
        + struct.pack('>II', len(data), zlib.crc32(data))
        + data
    )


def length(header):
    """Kiểm tra header và đọc ra độ dài nội dung cùng CRC32."""

    # Header phải đủ 12 byte và bắt đầu bằng dấu nhận diện STW1.
    # Nếu không đúng, dữ liệu không khớp định dạng ứng dụng.
    if len(header) != HEADER_SIZE or header[:4] != b'STW1':
        raise ValueError(
            'Không tìm thấy dữ liệu STW1 của ứng dụng.'
        )

    # Bỏ 4 byte STW1, đọc 8 byte còn lại thành hai số:
    # (độ dài nội dung, CRC32 dự kiến).
    # Lưu ý: tên hàm là length nhưng trả về cả hai giá trị.
    return struct.unpack('>II', header[4:])


def unpack(frame):
    """Lấy nội dung từ gói dữ liệu và kiểm tra tính toàn vẹn."""

    # Lấy 12 byte đầu làm header.
    # Hàm length kiểm tra dấu STW1, rồi trả về độ dài và CRC32.
    size, crc = length(frame[:HEADER_SIZE])

    # Những byte sau header là nội dung thông điệp.
    data = frame[HEADER_SIZE:]

    # Kiểm tra:
    # 1. Số byte nội dung có khớp độ dài trong header không?
    # 2. CRC32 tính lại có khớp CRC32 đã lưu không?
    #
    # Nếu sai, có thể dữ liệu trích xuất bị hỏng hoặc cấu hình
    # đọc không đúng, chẳng hạn chọn sai số bit LSB.
    if len(data) != size or zlib.crc32(data) != crc:
        raise ValueError(
            'Dữ liệu bị hỏng hoặc chọn sai số LSB.'
        )

    # Trả về nội dung dạng byte.
    # Nếu nội dung là văn bản UTF-8, bên gọi có thể dùng:
    # data.decode('utf-8')
    return data