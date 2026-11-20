from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint,request,render_template,send_file,jsonify
from core.image_io import read_image,write_lossless
from core.algorithms import encode,capacity,decode
from core import jpeg_dct
from .settings import options

bp=Blueprint('embed',__name__)


def ensure_method(source_format,config):
    if source_format=='JPEG' and config['method']!='jpeg_dct':
        raise ValueError('Ảnh JPEG phải chọn JPEG DCT để giữ đúng định dạng và lấy lại dữ liệu.')
    if source_format=='JPEG' and config['k']!=1:
        raise ValueError('JPEG DCT dùng cố định 1 bit mỗi hệ số, không có tùy chọn 2/3 LSB pixel.')
    if source_format!='JPEG' and config['method']=='jpeg_dct':
        raise ValueError('JPEG DCT chỉ dùng với ảnh JPG/JPEG.')


def jpeg_options(config):
    return {'mode':config['mode'],'key':config['key'],'threshold':config['threshold']}


@bp.route('/',methods=['GET','POST'])
def page():
    if request.method=='GET':
        return render_template('embed.html')
    if 'image' not in request.files:
        raise ValueError('Hãy chọn ảnh chứa.')
    uploaded=request.files['image']
    raw=uploaded.read()
    image=read_image(raw)
    source_format=image.info['source_format']
    config=options()
    ensure_method(source_format,config)
    payload=request.files.get('payload')
    data=payload.read() if payload and payload.filename else request.form.get('message','').encode('utf-8')
    if source_format=='JPEG':
        import io
        output=io.BytesIO(jpeg_dct.encode(raw,data,**jpeg_options(config)))
        mime='image/jpeg'
    else:
        result=encode(image,data,**config)
        output=write_lossless(result,source_format)
        # Kiểm tra đúng nội dung từ tệp đã lưu, không chỉ từ mảng pixel.
        check=read_image(output.getvalue())
        if decode(check,**config)!=data:
            raise ValueError('Tệp đầu ra không vượt qua kiểm tra trích xuất.')
        mime='image/png' if source_format=='PNG' else 'image/bmp'
    filename=secure_filename(uploaded.filename or 'image') or 'image'
    path=Path(filename)
    suffix={'PNG':'.png','BMP':'.bmp','JPEG':'.jpg'}[source_format]
    if source_format=='JPEG' and path.suffix.lower() in ('.jpg','.jpeg'):
        suffix=path.suffix
    return send_file(output,mimetype=mime,as_attachment=True,download_name=path.stem+'_stego'+suffix)


@bp.post('/capacity')
def inspect_capacity():
    if 'image' not in request.files:
        raise ValueError('Hãy chọn ảnh để tính sức chứa.')
    raw=request.files['image'].read()
    image=read_image(raw)
    source_format=image.info['source_format']
    config=options()
    ensure_method(source_format,config)
    amount=jpeg_dct.capacity(raw,**jpeg_options(config)) if source_format=='JPEG' else capacity(image,**config)
    return jsonify(capacity_bytes=amount,output_format=source_format)
