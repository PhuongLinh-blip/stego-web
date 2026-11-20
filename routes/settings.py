"""Đọc các tùy chọn biểu mẫu; encode, decode và capacity dùng chung."""
from flask import request


def options():
    method=request.form.get('method','replacement')
    # Chấp nhận nhãn gõ nhầm của giao diện cũ, chuẩn hóa tên đúng.
    if method == 'lsbms':
        method='lsbmr'
    try:
        k=int(request.form.get('k',1))
        threshold=int(request.form.get('threshold',12))
    except ValueError as error:
        raise ValueError('Số LSB và ngưỡng phải là số nguyên.') from error
    return dict(method=method,k=k,mode=request.form.get('position_mode','sequential'),
                key=request.form.get('key',''),threshold=threshold)
