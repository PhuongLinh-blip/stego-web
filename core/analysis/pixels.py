def pixel_info(image, x, y):
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError('Tọa độ nằm ngoài ảnh.')
    return [(name, value, f'{value:02X}', f'{value:08b}') for name, value in zip(image.mode, image.getpixel((x, y)))]
