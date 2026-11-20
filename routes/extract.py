import io
import base64
from flask import Blueprint,request,render_template,send_file
from core.image_io import read_image,write_png
from core.algorithms import decode
from core import jpeg_dct
from core.analysis.cache import load
from .settings import options

bp=Blueprint('extract',__name__)


def handoff_context():
    token=request.values.get('analysis_token')
    candidate_id=request.values.get('candidate')
    if not token:
        return None,None,None
    entry=load(token)
    candidate=next((c for c in entry['candidates'] if c['id']==candidate_id),None)
    if candidate is None:
        raise ValueError('Cấu hình chuyển tiếp không hợp lệ. Hãy phân tích lại.')
    return token,entry,candidate


@bp.route('/extract',methods=['GET','POST'])
def page():
    token,entry,candidate=handoff_context()
    values=request.form
    preview=None
    if candidate:
        config=candidate['config']
        values={'method':config['method'],'k':str(config['k']),'position_mode':config['mode'],'threshold':str(config['threshold'])}
        image=read_image(entry['raw'])
        preview='data:image/png;base64,'+base64.b64encode(write_png(image).getvalue()).decode('ascii')
    context={'values':values,'handoff':bool(candidate),'analysis_token':token,
             'candidate_id':candidate['id'] if candidate else None,'cached_preview':preview}
    if request.method=='GET':
        return render_template('extract.html',**context)
    if candidate:
        config=candidate['config']
        data=jpeg_dct.decode(entry['raw'],mode=config['mode'],key=config['key'],threshold=config['threshold']) if config['method']=='jpeg_dct' else decode(image,**config)
    else:
        if 'image' not in request.files:
            raise ValueError('Hãy chọn ảnh chứa dữ liệu.')
        raw=request.files['image'].read()
        image=read_image(raw)
        config=options()
        data=jpeg_dct.decode(raw,mode=config['mode'],key=config['key'],threshold=config['threshold']) if config['method']=='jpeg_dct' else decode(image,**config)
    if request.form.get('output')=='text':
        try:
            return render_template('extract.html',message=data.decode('utf-8'),**context)
        except UnicodeError as error:
            raise ValueError('Nội dung là tệp nhị phân. Chọn đầu ra Tệp tin để tải xuống.') from error
    return send_file(io.BytesIO(data),mimetype='application/octet-stream',as_attachment=True,download_name='recovered.bin')
