"""Tương thích import cũ: phần Gemini đã tắt, không mạng hoặc worker nền."""

def explain(facts):
    return {'status':'disabled','message':'Chức năng AI đã được bỏ. Chỉ sử dụng kết quả kiểm tra Python.'}


def explain_bounded(facts, wait_seconds=0):
    return explain(facts)
