"""Chọn vị trí nhúng; dùng cùng quy tắc khi encode và decode."""

from array import array             # Mảng số nguyên gọn hơn list số nguyên Python.
from dataclasses import dataclass   # Tự tạo hàm khởi tạo cho lớp lưu dữ liệu.
import hashlib                      # Tạo giá trị băm SHA-256 từ khóa.
import random                       # Xáo trộn vị trí theo seed.


# Bốn chế độ chọn vị trí được hỗ trợ.
MODES = ('sequential', 'keyed', 'adaptive', 'edge')


@dataclass
class PositionPlan:
    """Lưu kích thước ảnh và danh sách/thứ tự vị trí được phép nhúng."""

    width: int
    height: int

    # Danh sách chỉ số pixel.
    # Mỗi pixel được chọn sẽ sử dụng cả ba kênh R, G, B.
    pixels: object = None

    # Danh sách chỉ số kênh màu trên toàn ảnh.
    # Khác với pixels, samples có thể sắp thứ tự từng kênh riêng biệt.
    samples: object = None

    # Cờ cho biết kế hoạch dựa vào các bit cao.
    # Vị trí chỉ ổn định nếu thuật toán nhúng giữ nguyên các bit đó.
    stable: bool = False

    @property
    def count(self):
        """Tổng số kênh màu có thể sử dụng, không phải số bit."""

        if self.samples is not None:
            return len(self.samples)

        if self.pixels is not None:
            # Mỗi pixel được chọn có ba kênh RGB.
            return len(self.pixels) * 3

        # Không có danh sách riêng thì dùng toàn bộ RGB của ảnh.
        return self.width * self.height * 3

    def sites(self):
        """Lần lượt sinh vị trí dạng (x, y, channel).

        channel: 0 = R, 1 = G, 2 = B.
        """

        if self.samples is not None:
            # Trường hợp có thứ tự riêng cho từng kênh màu.
            for sample in self.samples:
                # Ví dụ sample = 7:
                # divmod(7, 3) = (2, 1)
                # → pixel số 2, kênh G.
                pixel, channel = divmod(sample, 3)

                # Chuyển chỉ số pixel một chiều thành tọa độ ảnh.
                yield (
                    pixel % self.width,   # Tọa độ x.
                    pixel // self.width,  # Tọa độ y.
                    channel
                )

        else:
            # Dùng danh sách pixel đã chọn.
            # Nếu chưa có danh sách thì duyệt toàn bộ pixel theo thứ tự.
            pixels = (
                self.pixels
                if self.pixels is not None
                else range(self.width * self.height)
            )

            for pixel in pixels:
                # Với mỗi pixel, lần lượt sử dụng R → G → B.
                for channel in range(3):
                    yield (
                        pixel % self.width,
                        pixel // self.width,
                        channel
                    )


def prepare(
    image,
    mode='sequential',
    key='',
    threshold=12,
    ordered=True
):
    """Tạo kế hoạch chọn vị trí cho ảnh."""

    # Kiểm tra tên chế độ.
    if mode not in MODES:
        raise ValueError('Chế độ vị trí không hợp lệ.')

    # Ngưỡng dùng để chọn khối/pixel ở chế độ adaptive và edge.
    # Code hiện tại kiểm tra ngưỡng trong mọi chế độ.
    if not isinstance(threshold, int) or not 1 <= threshold <= 255:
        raise ValueError('Ngưỡng phải là số nguyên từ 1 đến 255.')

    # Ban đầu chưa chọn danh sách riêng:
    # mặc định có thể dùng toàn bộ kênh RGB.
    plan = PositionPlan(image.width, image.height)

    # ---------------------------------------------------------
    # CHẾ ĐỘ KEYED: chọn thứ tự kênh màu bằng khóa.
    # ---------------------------------------------------------
    if mode == 'keyed':
        if not key or not key.strip():
            raise ValueError('Chế độ có khóa cần nhập khóa.')

        # Đếm byte UTF-8 vì ký tự có dấu có thể chiếm nhiều byte.
        if len(key.encode('utf-8')) > 256:
            raise ValueError('Khóa tối đa 256 byte UTF-8.')

        if ordered:
            # Tạo seed từ chuỗi nhận diện và khóa.
            # Cùng khóa sẽ tạo cùng seed.
            seed = hashlib.sha256(
                b'STW1-position-v1\0' + key.encode('utf-8')
            ).digest()

            # Đánh số tất cả các kênh RGB:
            # 0 = R pixel 0, 1 = G pixel 0, 2 = B pixel 0,
            # 3 = R pixel 1, ...
            plan.samples = array('I', range(plan.count))

            # Xáo trộn bằng bộ sinh riêng để không làm thay đổi
            # trạng thái random chung của chương trình.
            #
            # Encode và decode cần tái tạo cùng thứ tự này.
            # Đây chỉ là xáo trộn vị trí, không mã hóa nội dung.
            random.Random(
                int.from_bytes(seed, 'big')
            ).shuffle(plan.samples)

        # Nếu ordered=False, không tạo danh sách xáo trộn.
        # Khi đó sites() vẫn trả vị trí theo thứ tự tuần tự.
        return plan

    # ---------------------------------------------------------
    # CHẾ ĐỘ SEQUENTIAL: dùng toàn bộ ảnh theo thứ tự.
    # ---------------------------------------------------------
    if mode == 'sequential':
        return plan

    # ---------------------------------------------------------
    # Chuẩn bị dữ liệu cho ADAPTIVE và EDGE.
    # ---------------------------------------------------------

    # Chuyển sang RGB để lấy ba byte màu cho mỗi pixel.
    # Kênh alpha không được dùng để chấm điểm hoặc nhúng ở đây.
    rgb = image.convert('RGB').tobytes()

    # Mỗi pixel sẽ có một giá trị độ sáng đơn giản.
    gray = bytearray(image.width * image.height)

    for pixel in range(len(gray)):
        start = pixel * 3

        # 248 = 11111000 trong nhị phân.
        # "& 248" bỏ ba bit cuối, chỉ giữ năm bit cao.
        #
        # Lấy trung bình ba kênh sau khi bỏ bit thấp.
        # Đây là độ sáng trung bình đơn giản,
        # không phải công thức độ chói có trọng số.
        gray[pixel] = (
            (rgb[start] & 248)
            + (rgb[start + 1] & 248)
            + (rgb[start + 2] & 248)
        ) // 3

    # Vì điểm được tính từ năm bit cao nên việc thay tối đa
    # ba bit thấp bằng Replacement sẽ không đổi kết quả chọn vị trí.
    #
    # Matching/LSBMR cần xử lý riêng để không làm đổi năm bit cao.
    width, height = image.size

    # Danh sách pixel được chọn để nhúng.
    selected = array('I')

    # ---------------------------------------------------------
    # CHẾ ĐỘ ADAPTIVE: chọn và sắp xếp các khối có tương phản cao.
    # ---------------------------------------------------------
    if mode == 'adaptive':
        blocks = []

        # Chia ảnh thành các khối 8×8 pixel.
        for top in range(0, height, 8):
            for left in range(0, width, 8):

                # Lấy độ sáng của các pixel trong khối.
                # min() xử lý khối sát mép ảnh có thể nhỏ hơn 8×8.
                values = [
                    gray[y * width + x]
                    for y in range(top, min(top + 8, height))
                    for x in range(left, min(left + 8, width))
                ]

                # Điểm tương phản = sáng nhất - tối nhất.
                score = max(values) - min(values)

                # Chỉ giữ khối có điểm đạt ngưỡng.
                if score >= threshold:
                    blocks.append((score, top, left))

        # Ưu tiên khối có điểm cao trước.
        # Nếu bằng điểm: ưu tiên trên trước, trái trước.
        blocks.sort(
            key=lambda block: (-block[0], block[1], block[2])
        )

        # Chọn toàn bộ pixel thuộc các khối đạt ngưỡng.
        # Trong từng khối: duyệt từ trái sang phải, trên xuống dưới.
        for score, top, left in blocks:
            for y in range(top, min(top + 8, height)):
                for x in range(left, min(left + 8, width)):
                    selected.append(y * width + x)

    # ---------------------------------------------------------
    # CHẾ ĐỘ EDGE: ưu tiên pixel có chênh lệch độ sáng lớn.
    # ---------------------------------------------------------
    else:
        # Sau khi bỏ ba bit thấp, mỗi kênh tối đa là 248.
        # gray vì thế nằm trong khoảng 0–248.
        #
        # Điểm gồm hai độ chênh lệch, nên tối đa 248 + 248 = 496.
        # Tạo nhóm điểm từ 0 đến 496.
        buckets = [array('I') for _ in range(497)]

        for y in range(height):
            for x in range(width):
                pixel = y * width + x
                score = 0

                if x:
                    # So với pixel bên trái, nếu có.
                    score += abs(gray[pixel] - gray[pixel - 1])

                if y:
                    # So với pixel bên trên, nếu có.
                    score += abs(
                        gray[pixel] - gray[pixel - width]
                    )

                # Chỉ chọn pixel đạt ngưỡng.
                if score >= threshold:
                    buckets[score].append(pixel)

        # Ghép các nhóm từ điểm cao xuống thấp.
        # Các pixel bằng điểm giữ thứ tự duyệt ban đầu.
        for score in range(496, threshold - 1, -1):
            selected.extend(buckets[score])

    # Lưu các pixel đã chọn.
    # sites() sẽ dùng cả ba kênh RGB của từng pixel.
    plan.pixels = selected

    # Đánh dấu rằng kế hoạch yêu cầu giữ nguyên năm bit cao.
    # Cờ này không tự ngăn thuật toán nhúng sửa các bit đó.
    plan.stable = True

    return plan


def positions(image, mode='sequential', key='', threshold=12):
    """Hàm tiện ích: tạo kế hoạch rồi sinh từng vị trí nhúng."""

    yield from prepare(image, mode, key, threshold).sites()