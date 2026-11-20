"""Nhúng parity vào hệ số AC của kênh sáng JPEG baseline Huffman.

Không thêm dữ liệu sau EOI hoặc giấu trong metadata. Chỉ đổi bit biên độ
cuối của hệ số có |v| >= 2; không đổi category/Huffman, DC hoặc bảng lượng tử.
Các JPEG đầu vào không thuộc tập con này được chuẩn hóa baseline trước nhúng.
"""
from array import array
from dataclasses import dataclass
import hashlib
import io
import math
import random
import struct
from PIL import Image
from core.payload import HEADER_SIZE,pack,length,unpack


class UnsupportedJPEG(ValueError):
    pass


class BitReader:
    def __init__(self,data):
        self.data=data
        self.pos=0

    def read(self,count):
        if self.pos+count>len(self.data)*8:
            raise ValueError('JPEG thiếu bit entropy.')
        result=0
        for _ in range(count):
            result=(result<<1)|((self.data[self.pos//8]>>(7-self.pos%8))&1)
            self.pos+=1
        return result

    def symbol(self,table):
        code=0
        for size in range(1,17):
            code=(code<<1)|self.read(1)
            if (size,code) in table:
                return table[size,code]
        raise ValueError('Mã Huffman JPEG không hợp lệ.')


def signed(bits,size):
    if size==0:
        return 0
    return bits if bits >= (1<<(size-1)) else bits-((1<<size)-1)


def huffman_tables(data,tables):
    offset=0
    while offset<len(data):
        if offset+17>len(data):
            raise ValueError('Bảng Huffman bị cắt.')
        info=data[offset]
        counts=data[offset+1:offset+17]
        offset+=17
        count=sum(counts)
        if offset+count>len(data) or info>>4 not in (0,1) or info&15>3:
            raise ValueError('Bảng Huffman không hợp lệ.')
        values=data[offset:offset+count]
        offset+=count
        code=0
        index=0
        table={}
        for size,number in enumerate(counts,1):
            if code+number>1<<size:
                raise ValueError('Bảng Huffman quá số mã.')
            for _ in range(number):
                table[size,code]=values[index]
                index+=1
                code+=1
            code<<=1
        tables[info>>4,info&15]=table


@dataclass
class JPEGData:
    prefix: bytes
    chunks: list
    restart_markers: list
    tail: bytes
    bit_positions: array
    chunk_indices: array
    values: array
    block_indices: array
    block_scores: list
    edge_scores: list


def parse(raw):
    if not raw.startswith(b'\xff\xd8'):
        raise ValueError('Không phải JPEG.')
    offset=2
    frame=None
    tables={}
    interval=0
    while offset<len(raw):
        if raw[offset]!=255:
            raise ValueError('Marker JPEG không hợp lệ.')
        while offset<len(raw) and raw[offset]==255:
            offset+=1
        if offset>=len(raw):
            raise ValueError('JPEG bị cắt.')
        marker=raw[offset]
        offset+=1
        if marker==0xD9:
            raise ValueError('JPEG không có scan.')
        if offset+2>len(raw):
            raise ValueError('JPEG thiếu độ dài segment.')
        size=int.from_bytes(raw[offset:offset+2],'big')
        if size<2 or offset+size>len(raw):
            raise ValueError('Segment JPEG vượt ranh giới tệp.')
        data=raw[offset+2:offset+size]
        offset+=size
        if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            if marker!=0xC0:
                raise UnsupportedJPEG('Cần JPEG baseline Huffman 8-bit.')
            if len(data)<6:
                raise ValueError('SOF thiếu dữ liệu.')
            precision,height,width,n=struct.unpack('>BHHB',data[:6])
            if precision!=8 or n not in (1,3):
                raise UnsupportedJPEG('Chỉ hỗ trợ JPEG sáng hoặc YCbCr/RGB 3 thành phần.')
            if not width or not height or width*height>4_000_000 or len(data)!=6+3*n:
                raise ValueError('Kích thước hoặc SOF không hợp lệ.')
            components={}
            for i in range(n):
                cid,hv,qt=data[6+3*i:9+3*i]
                h,v=hv>>4,hv&15
                if cid in components or not 1<=h<=4 or not 1<=v<=4:
                    raise UnsupportedJPEG('Sampling factor không hỗ trợ.')
                components[cid]=(h,v)
            if n==1:
                # Scan một thành phần dùng MCU một block 8x8, kể cả khi
                # header có sampling factor khác 1 (non-interleaved scan).
                components={next(iter(components)):(1,1)}
            frame=(width,height,components)
        elif marker==0xC4:
            huffman_tables(data,tables)
        elif marker==0xDD:
            if len(data)!=2:
                raise ValueError('DRI không hợp lệ.')
            interval=int.from_bytes(data,'big')
        elif marker==0xDA:
            if frame is None or not data:
                raise ValueError('SOS thiếu SOF.')
            width,height,components=frame
            n=data[0]
            if n!=len(components) or len(data)!=1+2*n+3 or data[-3:]!=bytes((0,63,0)):
                raise UnsupportedJPEG('Chỉ hỗ trợ một scan sequential đầy đủ.')
            scan=[]
            for i in range(n):
                cid,selectors=data[1+2*i:3+2*i]
                if cid not in components or any(cid==old[0] for old in scan):
                    raise ValueError('Thành phần SOS không hợp lệ.')
                dc=tables.get((0,selectors>>4))
                ac=tables.get((1,selectors&15))
                if dc is None or ac is None:
                    raise ValueError('Thiếu bảng Huffman.')
                scan.append((cid,dc,ac))
            prefix=raw[:offset]
            break
    else:
        raise ValueError('Không tìm thấy SOS.')

    # Bỏ byte stuffing trong entropy; giữ riêng các restart marker.
    chunks=[]
    restarts=[]
    chunk=bytearray()
    while offset<len(raw):
        value=raw[offset]
        if value!=255:
            chunk.append(value)
            offset+=1
            continue
        marker_start=offset
        offset+=1
        while offset<len(raw) and raw[offset]==255:
            offset+=1
        if offset>=len(raw):
            raise ValueError('JPEG thiếu EOI.')
        marker=raw[offset]
        offset+=1
        if marker==0:
            chunk.append(255)
        elif 0xD0<=marker<=0xD7:
            chunks.append(chunk)
            chunk=bytearray()
            restarts.append(bytes((255,marker)))
        elif marker==0xD9:
            chunks.append(chunk)
            tail=raw[marker_start:]
            break
        else:
            raise UnsupportedJPEG('JPEG nhiều scan/marker giữa scan cần chuẩn hóa.')
    else:
        raise ValueError('Không có EOI.')

    hmax=max(h for h,v in components.values())
    vmax=max(v for h,v in components.values())
    columns=math.ceil(width/(8*hmax))
    rows=math.ceil(height/(8*vmax))
    total_mcus=columns*rows
    expected=math.ceil(total_mcus/interval) if interval else 1
    if len(chunks)!=expected or (restarts and not interval):
        raise ValueError('Số restart segment không khớp DRI.')
    for i,marker in enumerate(restarts):
        if marker[1]!=0xD0+(i%8):
            raise ValueError('Thứ tự restart marker không hợp lệ.')
    positions=array('I')
    chunk_ids=array('I')
    values=array('h')
    block_ids=array('I')
    scores=[]
    edge_scores=[]
    dc_grid={}
    luminance=next(iter(components))
    processed=0
    for segment,chunk in enumerate(chunks):
        reader=BitReader(chunk)
        predictors={cid:0 for cid in components}
        count=min(interval or total_mcus,total_mcus-processed)
        for _ in range(count):
            my,mx=divmod(processed,columns)
            for cid,dc_table,ac_table in scan:
                h,v=components[cid]
                for by in range(v):
                    for bx in range(h):
                        dc_size=reader.symbol(dc_table)
                        if dc_size>11:
                            raise ValueError('DC category vượt baseline.')
                        predictors[cid]+=signed(reader.read(dc_size),dc_size)
                        dc_value=predictors[cid]
                        block=len(scores)
                        score=0
                        coefficient=1
                        while coefficient<64:
                            symbol=reader.symbol(ac_table)
                            run,amplitude_size=symbol>>4,symbol&15
                            if amplitude_size==0:
                                if run==0:
                                    break
                                if run!=15:
                                    raise ValueError('AC run không hợp lệ.')
                                coefficient+=16
                                if coefficient>64:
                                    raise ValueError('AC run vượt block.')
                                continue
                            coefficient+=run
                            if coefficient>=64 or amplitude_size>10:
                                raise ValueError('AC coefficient vượt baseline.')
                            value=signed(reader.read(amplitude_size),amplitude_size)
                            if cid==luminance:
                                score+=abs(value)//2
                                if amplitude_size>=2:
                                    positions.append(reader.pos-1)
                                    chunk_ids.append(segment)
                                    values.append(value)
                                    block_ids.append(block)
                            coefficient+=1
                        if cid==luminance:
                            gx,gy=mx*h+bx,my*v+by
                            edge=0
                            if (gx-1,gy) in dc_grid:
                                edge+=abs(dc_value-dc_grid[gx-1,gy])
                            if (gx,gy-1) in dc_grid:
                                edge+=abs(dc_value-dc_grid[gx,gy-1])
                            dc_grid[gx,gy]=dc_value
                            scores.append(score)
                            edge_scores.append(edge)
            processed+=1
        padding=len(chunk)*8-reader.pos
        if padding>7 or (padding and reader.read(padding)!=(1<<padding)-1):
            raise ValueError('Padding entropy không hợp lệ.')
    return JPEGData(prefix,chunks,restarts,tail,positions,chunk_ids,values,block_ids,scores,edge_scores)


def baseline(raw):
    try:
        return raw,parse(raw)
    except UnsupportedJPEG:
        # Chuẩn hóa trước nhúng; tuyệt đối không nén pixel lại sau nhúng.
        with Image.open(io.BytesIO(raw)) as source:
            image=source.convert('L' if source.mode=='L' else 'RGB')
            buffer=io.BytesIO()
            image.save(buffer,format='JPEG',quality=95,progressive=False)
            converted=buffer.getvalue()
        return converted,parse(converted)


def order(parsed,mode='sequential',key='',threshold=12):
    if mode not in ('sequential','keyed','adaptive','edge') or not 1<=threshold<=255:
        raise ValueError('Chế độ vị trí hoặc ngưỡng JPEG không hợp lệ.')
    if mode=='keyed' and (not key.strip() or len(key.encode('utf-8'))>256):
        raise ValueError('JPEG theo khóa cần khóa không rỗng, tối đa 256 byte UTF-8.')
    if mode in ('sequential','keyed'):
        result=array('I',range(len(parsed.values)))
    else:
        scores=parsed.block_scores if mode=='adaptive' else parsed.edge_scores
        # Score ổn định: parity không đổi floor(abs(AC)/2), DC giữ nguyên.
        selected=[i for i,block in enumerate(parsed.block_indices) if scores[block]>=threshold]
        selected.sort(key=lambda i:(-scores[parsed.block_indices[i]],parsed.block_indices[i],i))
        result=array('I',selected)
    if mode=='keyed':
        seed=hashlib.sha256(b'JPEG-DCT-STW1-v1\0'+key.encode('utf-8')).digest()
        random.Random(int.from_bytes(seed,'big')).shuffle(result)
    return result


def read_bytes(parsed,sites,count):
    output=bytearray()
    byte=bits=0
    for site in sites:
        byte=(byte<<1)|(parsed.values[site]&1)
        bits+=1
        if bits==8:
            output.append(byte)
            byte=bits=0
            if len(output)==count:
                break
    return bytes(output)


def read_frame(parsed,sites):
    header=read_bytes(parsed,sites,HEADER_SIZE)
    size,_=length(header)
    if (size+HEADER_SIZE)*8>len(sites):
        raise ValueError('Độ dài payload JPEG vượt sức chứa.')
    return unpack(read_bytes(parsed,sites,size+HEADER_SIZE))


def capacity(raw,mode='sequential',key='',threshold=12):
    _,parsed=baseline(raw)
    return max(0,len(order(parsed,mode,key,threshold))//8-HEADER_SIZE)


def encode(raw,data,mode='sequential',key='',threshold=12):
    _,parsed=baseline(raw)
    sites=order(parsed,mode,key,threshold)
    frame=pack(data)
    if len(frame)*8>len(sites):
        raise ValueError(f'JPEG chỉ chứa tối đa {max(0,len(sites)//8-HEADER_SIZE)} byte theo cấu hình này. Chọn ảnh nhiều chi tiết hơn hoặc giảm nội dung/ngưỡng.')
    for bit_number in range(len(frame)*8):
        site=sites[bit_number]
        bit=(frame[bit_number//8]>>(7-bit_number%8))&1
        if (parsed.values[site]&1)!=bit:
            chunk=parsed.chunks[parsed.chunk_indices[site]]
            position=parsed.bit_positions[site]
            chunk[position//8]^=1<<(7-position%8)
    result=bytearray(parsed.prefix)
    for i,chunk in enumerate(parsed.chunks):
        result.extend(bytes(chunk).replace(b'\xff',b'\xff\x00'))
        if i<len(parsed.restart_markers):
            result.extend(parsed.restart_markers[i])
    result.extend(parsed.tail)
    output=bytes(result)
    # Không trả ảnh nếu không đọc lại được nội dung hoặc JPEG không mở được.
    if decode(output,mode,key,threshold)!=data:
        raise ValueError('JPEG không vượt qua kiểm tra trích xuất sau nhúng.')
    with Image.open(io.BytesIO(output)) as check:
        check.load()
    return output


def decode(raw,mode='sequential',key='',threshold=12):
    parsed=parse(raw)
    return read_frame(parsed,order(parsed,mode,key,threshold))
