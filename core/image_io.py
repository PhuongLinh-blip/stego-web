import io      # Đọc/ghi dữ liệu trong bộ nhớ, không cần tạo file trên ổ đĩa.
import struct  # Đóng gói các giá trị thành byte để tạo header BMP.
from PIL import Image, UnidentifiedImageError


def read_image(raw):
    """Đọc dữ liệu ảnh dạng byte, kiểm tra và chuyển sang RGB/RGBA."""
    try:
        # Bọc dữ liệu byte thành một luồng để Pillow có thể mở ảnh.
        # "with" giúp đóng ảnh nguồn sau khi xử lý xong.
        with Image.open(io.BytesIO(raw)) as image:

            # Kiểm tra định dạng thực tế của ảnh, không dựa vào đuôi file.
            # Pillow dùng tên "JPEG" cho cả ảnh .jpg và .jpeg.
            if image.format not in ('PNG', 'BMP', 'JPEG'):
                raise ValueError('Chỉ nhận PNG, BMP, JPG/JPEG.')

            # Giới hạn tổng số pixel để giảm lượng bộ nhớ và thời gian xử lý.
            if image.width * image.height > 4_000_000:
                raise ValueError('Ảnh tối đa 4 triệu pixel.')

            # Nếu ảnh có kênh alpha thì chuyển sang RGBA.
            # Nếu không có thì chuyển sang RGB.
            # RGB: đỏ, xanh lá, xanh dương.
            # RGBA: RGB và thêm alpha để biểu diễn độ trong suốt.
            result = image.convert(
                'RGBA' if 'A' in image.getbands() else 'RGB'
            )

            # Lưu lại định dạng nguồn trước khi trả về ảnh đã chuyển đổi.
            # Ví dụ: result.info['source_format'] = 'JPEG'.
            result.info['source_format'] = image.format
            return result

    except (UnidentifiedImageError, OSError) as error:
        # Chuyển lỗi không nhận diện/đọc được ảnh thành thông báo dễ hiểu.
        # "from error" giữ lại nguyên nhân lỗi ban đầu để hỗ trợ debug.
        raise ValueError('Không đọc được ảnh.') from error


def write_png(image):
    """Lưu ảnh thành PNG trong bộ nhớ và trả về luồng byte."""

    # Tạo vùng đệm để chứa dữ liệu file PNG.
    output = io.BytesIO()

    # PNG nén không mất dữ liệu, giữ nguyên giá trị pixel đã nhúng LSB.
    image.save(output, format='PNG')

    # Sau khi ghi, con trỏ đang ở cuối luồng.
    # Đưa về đầu để bên nhận có thể đọc hoặc tải file.
    output.seek(0)
    return output


def write_lossless(image, source_format):
    """Xuất PNG hoặc BMP để giữ nguyên dữ liệu pixel đã nhúng."""

    # Nếu định dạng nguồn là PNG, sử dụng hàm ghi PNG ở trên.
    if source_format == 'PNG':
        return write_png(image)

    # Hàm này chỉ hỗ trợ xuất PNG và BMP.
    # JPEG bị từ chối vì lưu JPEG có thể làm sai LSB trên pixel.
    # Hàm này không triển khai phương pháp giấu tin JPEG DCT.
    if source_format != 'BMP':
        raise ValueError(
            'JPEG phải dùng phương pháp JPEG DCT, '
            'không lưu lại LSB pixel bằng JPEG.'
        )

    # Tạo vùng đệm chứa file BMP đầu ra.
    output = io.BytesIO()

    if image.mode != 'RGBA':
        # Với ảnh không ở chế độ RGBA, để Pillow ghi BMP.
        image.save(output, format='BMP')

    else:
        # Với RGBA, tự tạo BMP V4 để khai báo rõ kênh alpha.
        # Một số BMP thông thường không giữ/diễn giải alpha đúng.

        # BMP ở đây dùng chiều cao dương nên lưu hàng pixel từ dưới lên.
        # Vì vậy cần lật dọc thứ tự hàng trước khi lấy dữ liệu.
        # Mỗi pixel được ghi theo thứ tự B, G, R, A.
        pixels = image.transpose(
            Image.Transpose.FLIP_TOP_BOTTOM
        ).tobytes('raw', 'BGRA')

        # Tạo 40 byte đầu của DIB header.
        # Dấu "<" quy định thứ tự byte little-endian.
        header = struct.pack(
            '<IiiHHIIiiII',
            108,              # Kích thước toàn bộ DIB header BMP V4.
            image.width,      # Chiều rộng ảnh.
            image.height,     # Chiều cao dương: các hàng lưu từ dưới lên.
            1,                # Số mặt phẳng màu, luôn là 1.
            32,               # 32 bit/pixel: B, G, R, A, mỗi kênh 8 bit.
            3,                # BI_BITFIELDS: dùng mask mô tả các kênh.
            len(pixels),      # Kích thước dữ liệu pixel tính bằng byte.
            2835,             # Độ phân giải ngang, khoảng 72 DPI.
            2835,             # Độ phân giải dọc, khoảng 72 DPI.
            0,                # Không khai báo bảng màu.
            0                 # Không khai báo số màu quan trọng.
        )

        # Thêm mask xác định vị trí các kênh màu trong pixel 32 bit,
        # cùng mã khai báo không gian màu sRGB.
        header += struct.pack(
            '<IIIII',
            0x00ff0000,        # Mask kênh đỏ.
            0x0000ff00,        # Mask kênh xanh lá.
            0x000000ff,        # Mask kênh xanh dương.
            0xff000000,        # Mask kênh alpha.
            0x73524742        # Mã LCS_sRGB.
        )

        # Bổ sung 36 byte thông tin điểm màu và 12 byte gamma.
        # Các trường này đặt bằng 0; không dùng khi đã chọn sRGB.
        # Tổng DIB header: 40 + 20 + 48 = 108 byte.
        header += bytes(36 + 12)

        # Ghi BMP file header dài 14 byte.
        output.write(
            struct.pack(
                '<2sIHHI',
                b'BM',                          # Chữ ký nhận diện BMP.
                14 + 108 + len(pixels),         # Tổng kích thước file.
                0,                              # Trường dự phòng.
                0,                              # Trường dự phòng.
                14 + 108                        # Vị trí bắt đầu pixel.
            )
        )

        # File BMP gồm: file header → DIB header → dữ liệu pixel.
        output.write(header)
        output.write(pixels)

    # Đưa con trỏ về đầu luồng trước khi trả về.
    output.seek(0)
    return output