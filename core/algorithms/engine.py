"""Điều phối thuật toán và vị trí, dùng payload STW1 tương thích bản cũ."""
from core.positions import prepare
from core.payload import pack, HEADER_SIZE
from .common import bits_from_bytes, read_payload, get_channel, set_channel
from .matching import match_value
from .lsbmr import encode_pair, pair_bits
from .replacement import check_k


def validate(method,k):
    if method not in ('replacement','matching','lsbmr'):
        raise ValueError('Chọn Replacement, Matching hoặc LSBMR.')
    if method == 'replacement':
        check_k(k)
    elif k != 1:
        raise ValueError('Matching và LSBMR không có tùy chọn 2/3 LSB mỗi kênh.')


def bit_capacity(plan,method,k):
    return (plan.count//2)*2 if method == 'lsbmr' else plan.count*k


def capacity(image,method='replacement',k=1,mode='sequential',key='',threshold=12):
    validate(method,k)
    plan=prepare(image,mode,key,threshold,ordered=False)
    return max(0,bit_capacity(plan,method,k)//8-HEADER_SIZE)


def encode(image,data,method='replacement',k=1,mode='sequential',key='',threshold=12):
    validate(method,k)
    plan=prepare(image,mode,key,threshold)
    frame=pack(data)
    if len(frame)*8 > bit_capacity(plan,method,k):
        available=max(0,bit_capacity(plan,method,k)//8-HEADER_SIZE)
        raise ValueError(f'Chế độ vị trí này chứa tối đa {available} byte nội dung. Chọn ảnh lớn hơn, giảm ngưỡng hoặc đổi vị trí.')
    output=image.copy()
    sites=iter(plan.sites())
    if method == 'lsbmr':
        bits=iter(bits_from_bytes(frame))
        for first,second in zip(bits,bits):
            a,b=next(sites),next(sites)
            x,y=encode_pair(get_channel(output,a),get_channel(output,b),first,second,plan.stable)
            set_channel(output,a,x)
            set_channel(output,b,y)
    elif method == 'matching':
        for site,bit in zip(sites,bits_from_bytes(frame)):
            set_channel(output,site,match_value(get_channel(output,site),bit,plan.stable))
    else:
        bits=iter(bits_from_bytes(frame))
        mask=(1<<k)-1
        remaining=len(frame)*8
        while remaining:
            value=0
            for _ in range(k):
                bit=next(bits,0)
                value=(value<<1)|bit
            site=next(sites)
            set_channel(output,site,(get_channel(output,site)&(255^mask))|value)
            remaining=max(0,remaining-k)
    return output


def decode(image,method='replacement',k=1,mode='sequential',key='',threshold=12):
    validate(method,k)
    plan=prepare(image,mode,key,threshold)
    sites=iter(plan.sites())
    def stream():
        if method == 'lsbmr':
            for a,b in zip(sites,sites):
                yield from pair_bits(get_channel(image,a),get_channel(image,b))
        else:
            for site in sites:
                value=get_channel(image,site)
                for shift in range(k-1,-1,-1):
                    yield (value>>shift)&1
    try:
        return read_payload(stream(),bit_capacity(plan,method,k))
    except ValueError as error:
        raise ValueError('Không đọc được dữ liệu STW1: kiểm tra thuật toán, số LSB, chế độ vị trí, khóa/ngưỡng hoặc ảnh đã bị thay đổi. '+str(error)) from error
