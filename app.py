from flask import Flask, render_template, request
from routes.embed import bp as embed_bp
from routes.extract import bp as extract_bp
from routes.analyze import bp as analyze_bp

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.register_blueprint(embed_bp)
app.register_blueprint(extract_bp)
app.register_blueprint(analyze_bp)

@app.errorhandler(ValueError)
def invalid(error):
    back = request.path if request.path in ('/', '/extract', '/analyze') else '/'
    return render_template('error.html', error=str(error), back=back), 400

@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', error='Tổng dung lượng tải lên vượt giới hạn 16 MiB.', back='/'), 413



# Dấu phiên bản để phân biệt với tiến trình Flask cũ.
@app.get('/api/health')
def health():
    return {'status':'ok','build':'format-v10-no-ai'}

@app.after_request
def build_header(response):
    response.headers['X-Stego-Build']='format-v10-no-ai'
    return response


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
