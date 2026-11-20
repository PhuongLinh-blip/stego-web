import base64
from flask import Blueprint,request,render_template
from core.image_io import read_image,write_png
from core.analysis.hex_view import hex_rows
from core.analysis.pixels import pixel_info
from core.analysis.probe import scan,measurements
from core.analysis.cache import save

bp=Blueprint('analyze',__name__)


@bp.route('/analyze',methods=['GET','POST'])
def page():
    if request.method=='GET':
        return render_template('analyze.html')
    if 'image' not in request.files:
        raise ValueError('Hãy chọn ảnh để phân tích.')
    raw=request.files['image'].read()
    image=read_image(raw)
    try:
        x=int(request.form.get('x',0))
        y=int(request.form.get('y',0))
        threshold=int(request.form.get('probe_threshold',12))
    except ValueError as error:
        raise ValueError('Tọa độ và ngưỡng phải là số nguyên.') from error
    if not 1<=threshold<=255:
        raise ValueError('Ngưỡng phải từ 1 đến 255.')
    pixels=pixel_info(image,x,y)
    report=scan(image,key=request.form.get('probe_key',''),thresholds=(threshold,12,24,48),raw=raw)
    evidence=measurements(image,raw)
    token=save(raw,report['candidates']) if report['candidates'] else None
    preview='data:image/png;base64,'+base64.b64encode(write_png(image).getvalue()).decode('ascii')
    return render_template('analyze.html',rows=hex_rows(raw),pixels=pixels,size=image.size,total=len(raw),x=x,y=y,
        image_preview=preview,report=report,evidence=evidence,analysis_token=token)
