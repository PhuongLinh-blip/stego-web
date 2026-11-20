"""Kiểm tra STW1 bằng Python; Kiểm chứng header, độ dài và CRC độc lập."""
from itertools import islice
import struct
import time
import zlib
from core.positions import prepare
from core.payload import HEADER_SIZE, length, unpack
from core.algorithms.common import get_channel
from core.algorithms.lsbmr import pair_bits


def read_bytes(sites, image, method, k, count):
    sites=iter(sites)
    def stream():
        if method=='lsbmr':
            for a,b in zip(sites,sites):
                yield from pair_bits(get_channel(image,a),get_channel(image,b))
        else:
            for site in sites:
                value=get_channel(image,site)
                for shift in range(k-1,-1,-1):
                    yield (value>>shift)&1
    bits=iter(stream())
    result=bytearray()
    for _ in range(count):
        group=list(islice(bits,8))
        if len(group)<8:
            break
        value=0
        for bit in group:
            value=(value<<1)|bit
        result.append(value)
    return bytes(result)


def scan(image, key='', thresholds=(12,24,48), budget=8, raw=None):
    if raw is not None and raw.startswith(b'\xff\xd8'):
        return scan_jpeg(raw,key,thresholds,budget)
    start=time.monotonic()
    candidates=[]
    attempts=[]
    limited=False
    modes=[('sequential',12)]
    for mode in ('adaptive','edge'):
        modes.extend((mode,t) for t in dict.fromkeys(thresholds))
    if key:
        modes.append(('keyed',12))
    # Matching và Replacement 1 bit cùng phép đọc; không tạo hai bằng chứng giả.
    methods=[('replacement',1),('replacement',2),('replacement',3),('lsbmr',1)]
    for mode,threshold in modes:
        if time.monotonic()-start>budget:
            limited=True
            break
        plan=prepare(image,mode,key,threshold)
        for method,k in methods:
            entry={'method':method,'k':k,'mode':mode,'threshold':threshold,'header':False,'crc':False}
            capacity_bits=(plan.count//2)*2 if method=='lsbmr' else plan.count*k
            if capacity_bits<HEADER_SIZE*8:
                entry['result']='Không đủ vị trí để đọc header'
                attempts.append(entry)
                continue
            header=read_bytes(plan.sites(),image,method,k,HEADER_SIZE)
            if header[:4]!=b'STW1':
                entry['result']='Không có header STW1'
                attempts.append(entry)
                continue
            entry['header']=True
            try:
                size,_=length(header)
                if (size+HEADER_SIZE)*8>capacity_bits:
                    raise ValueError('Độ dài vượt sức chứa')
                frame=read_bytes(plan.sites(),image,method,k,size+HEADER_SIZE)
                payload=unpack(frame)
                entry['crc']=True
                entry['result']='Header, độ dài và CRC32 hợp lệ'
                config={'method':method,'k':k,'mode':mode,'key':key if mode=='keyed' else '', 'threshold':threshold}
                candidates.append({'id':'C'+str(len(candidates)+1),'config':config,'size':len(payload),
                    'equivalent_matching':method=='replacement' and k==1})
            except ValueError as error:
                entry['result']=str(error)
            attempts.append(entry)
    return {'candidates':candidates,'attempts':attempts,'limited':limited,
            'elapsed':round(time.monotonic()-start,3),'key_tested':bool(key),
            'thresholds':list(dict.fromkeys(thresholds))}


def measurements(image, raw):
    # Lấy mẫu đều tối đa 10.000 pixel, không coi cân bằng LSB là xác nhận giấu tin.
    rgb=image.convert('RGB').tobytes()
    pixels=image.width*image.height
    stride=max(1,(pixels+9999)//10000)
    ones=[0,0,0]
    sampled=0
    for pixel in range(0,pixels,stride):
        for c in range(3):
            ones[c]+=rgb[pixel*3+c]&1
        sampled+=1
    evidence=[{'id':'E1','text':f'Ảnh {image.width}×{image.height}; lấy mẫu đều {sampled} pixel RGB.'},
              {'id':'E2','text':'Tỷ lệ LSB bằng 1 theo R/G/B: '+', '.join(f'{n/sampled:.4f}' for n in ones)+'. Đây là mô tả, không phải xác suất có giấu tin.'}]
    png_info='Không kiểm tra cấu trúc PNG vì tệp không phải PNG.'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        offset=8
        png_info='Chưa đọc được khối IEND hợp lệ.'
        while offset+12<=len(raw):
            size=struct.unpack('>I',raw[offset:offset+4])[0]
            end=offset+12+size
            if end>len(raw):
                png_info='Có khối PNG vượt ranh giới tệp.'
                break
            kind=raw[offset+4:offset+8]
            if kind==b'IEND' and size==0:
                stored=struct.unpack('>I',raw[end-4:end])[0]
                if zlib.crc32(raw[offset+4:end-4])!=stored:
                    png_info='CRC của IEND không hợp lệ.'
                else:
                    trailing=len(raw)-end
                    png_info=f'Có {trailing} byte sau khối IEND. Dữ liệu dư không tự chứng minh có tin giấu.'
                break
            offset=end
    evidence.append({'id':'E3','text':png_info})
    return evidence



def scan_jpeg(raw,key='',thresholds=(12,24,48),budget=8):
    from core import jpeg_dct
    start=time.monotonic()
    attempts=[]
    candidates=[]
    limited=False
    try:
        parsed=jpeg_dct.parse(raw)
    except ValueError as error:
        return {'candidates':[],'attempts':[{'method':'jpeg_dct','k':1,'mode':'sequential','threshold':12,'header':False,'crc':False,'result':str(error)}],
                'limited':False,'elapsed':round(time.monotonic()-start,3),'key_tested':False,'thresholds':list(thresholds)}
    modes=[('sequential',12)]
    for mode in ('adaptive','edge'):
        modes.extend((mode,t) for t in dict.fromkeys(thresholds))
    if key:
        modes.append(('keyed',12))
    for mode,threshold in modes:
        if time.monotonic()-start>budget:
            limited=True
            break
        sites=jpeg_dct.order(parsed,mode,key,threshold)
        entry={'method':'jpeg_dct','k':1,'mode':mode,'threshold':threshold,'header':False,'crc':False}
        header=jpeg_dct.read_bytes(parsed,sites,HEADER_SIZE)
        if header[:4]!=b'STW1':
            entry['result']='Không có header STW1 trong hệ số DCT'
        else:
            entry['header']=True
            try:
                payload=jpeg_dct.read_frame(parsed,sites)
                entry['crc']=True
                entry['result']='JPEG DCT: header, độ dài và CRC32 hợp lệ'
                candidates.append({'id':'C'+str(len(candidates)+1),'config':{'method':'jpeg_dct','k':1,'mode':mode,'key':key if mode=='keyed' else '', 'threshold':threshold},
                                   'size':len(payload),'equivalent_matching':False})
            except ValueError as error:
                entry['result']=str(error)
        attempts.append(entry)
    return {'candidates':candidates,'attempts':attempts,'limited':limited,'elapsed':round(time.monotonic()-start,3),
            'key_tested':bool(key),'thresholds':list(dict.fromkeys(thresholds))}
