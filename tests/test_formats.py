import io,random,unittest
from PIL import Image
from app import app
from core import jpeg_dct
from core.image_io import read_image,write_lossless
from core.algorithms import decode
from core.analysis import cache


def fixture(mode='RGB',size=(96,80)):
    return Image.frombytes(mode,size,random.Random(55).randbytes(size[0]*size[1]*len(mode)))


def jpeg_bytes(image,**options):
    result=io.BytesIO()
    image.save(result,format='JPEG',**options)
    return result.getvalue()


class JPEGTests(unittest.TestCase):
    def test_dct_roundtrips_and_invariants(self):
        for color in ('RGB','L'):
            for sampling in (0,1,2):
                raw=jpeg_bytes(fixture(color),quality=90,subsampling=sampling,optimize=True)
                before=jpeg_dct.parse(raw)
                for mode in ('sequential','keyed','adaptive','edge'):
                    with self.subTest(color=color,sampling=sampling,mode=mode):
                        output=jpeg_dct.encode(raw,b'JPEG message',mode,'key',1)
                        self.assertTrue(output.startswith(b'\xff\xd8'))
                        self.assertEqual(jpeg_dct.decode(output,mode,'key',1),b'JPEG message')
                        after=jpeg_dct.parse(output)
                        self.assertEqual(before.prefix,after.prefix)
                        self.assertEqual(before.block_scores,after.block_scores)
                        self.assertEqual(before.edge_scores,after.edge_scores)
                        self.assertEqual(len(before.values),len(after.values))
                        self.assertTrue(all(abs(a-b)<=1 for a,b in zip(before.values,after.values)))
                        with Image.open(io.BytesIO(output)) as check:
                            check.load()
                            self.assertEqual(check.format,'JPEG')
                            self.assertEqual(check.size,(96,80))

    def test_progressive_cmyk_restart_and_odd_sizes(self):
        for mode in ('RGB','L','CMYK'):
            for progressive in (False,True):
                raw=jpeg_bytes(fixture(mode,(65,49)),quality=90,progressive=progressive)
                output=jpeg_dct.encode(raw,b'Hi')
                self.assertEqual(jpeg_dct.decode(output),b'Hi')
        for blocks in (1,2,5):
            raw=jpeg_bytes(fixture(size=(99,71)),quality=95,restart_marker_blocks=blocks)
            self.assertIn(b'\xff\xd0',raw)
            output=jpeg_dct.encode(raw,b'restart test')
            self.assertEqual(jpeg_dct.decode(output),b'restart test')
            self.assertTrue(jpeg_dct.parse(output).restart_markers)

    def test_capacity_key_damage_and_no_trailing_payload(self):
        raw=jpeg_bytes(fixture(),quality=90)
        for mode in ('sequential','keyed','adaptive','edge'):
            size=jpeg_dct.capacity(raw,mode,'key',1)
            payload=bytes(i%256 for i in range(size))
            output=jpeg_dct.encode(raw,payload,mode,'key',1)
            self.assertEqual(jpeg_dct.decode(output,mode,'key',1),payload)
            self.assertEqual(jpeg_dct.parse(output).tail,b'\xff\xd9')
            with self.assertRaises(ValueError):
                jpeg_dct.encode(raw,payload+b'x',mode,'key',1)
        output=jpeg_dct.encode(raw,b'message','keyed','right')
        with self.assertRaises(ValueError):
            jpeg_dct.decode(output,'keyed','wrong')
        with self.assertRaises(ValueError):
            jpeg_dct.decode(raw)
        with self.assertRaises(ValueError):
            jpeg_dct.parse(raw[:-10])
        flat=jpeg_bytes(Image.new('RGB',(64,64),(150,150,150)))
        self.assertEqual(jpeg_dct.capacity(flat),0)
        with self.assertRaises(ValueError):
            jpeg_dct.encode(flat,b'payload')


class FormatWebTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        self.client=app.test_client()
        cache.ENTRIES.clear()

    def test_preserve_png_bmp_and_alpha(self):
        for format in ('PNG','BMP'):
            for mode in ('RGB','RGBA'):
                original=fixture(mode,(49,49))
                raw=write_lossless(original,format).getvalue()
                loaded=read_image(raw)
                if mode=='RGBA':
                    self.assertEqual(loaded.getchannel('A').tobytes(),original.getchannel('A').tobytes())
                for method in ('replacement','matching','lsbmr'):
                    result=self.client.post('/',data={'image':(io.BytesIO(raw),'photo.'+format.lower()),'message':'Xin chào','method':method},content_type='multipart/form-data')
                    self.assertEqual(result.status_code,200)
                    with Image.open(io.BytesIO(result.data)) as output:
                        self.assertEqual(output.format,format)
                    self.assertIn(('_stego.'+format.lower()).encode(),result.headers['Content-Disposition'].encode())
                    image=read_image(result.data)
                    self.assertEqual(decode(image,method),'Xin chào'.encode())
                    if mode=='RGBA':
                        self.assertEqual(image.getchannel('A').tobytes(),original.getchannel('A').tobytes())

    def test_jpeg_http_and_handoff(self):
        raw=jpeg_bytes(fixture(),quality=95)
        for extension in ('jpg','jpeg','JPG'):
            for mode in ('sequential','keyed','adaptive','edge'):
                settings={'method':'jpeg_dct','position_mode':mode,'key':'right','threshold':'1'}
                capacity=self.client.post('/capacity',data={'image':(io.BytesIO(raw),'a.'+extension),**settings},content_type='multipart/form-data')
                self.assertEqual(capacity.status_code,200)
                self.assertEqual(capacity.json['output_format'],'JPEG')
                result=self.client.post('/',data={'image':(io.BytesIO(raw),'photo.'+extension),'payload':(io.BytesIO(bytes(range(100))),'data.bin'),**settings},content_type='multipart/form-data')
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.mimetype,'image/jpeg')
                self.assertIn('photo_stego.'+extension,result.headers['Content-Disposition'])
                extracted=self.client.post('/extract',data={'image':(io.BytesIO(result.data),'stego.'+extension),'output':'file',**settings},content_type='multipart/form-data')
                self.assertEqual(extracted.data,bytes(range(100)))
                analyzed=self.client.post('/analyze',data={'image':(io.BytesIO(result.data),'stego.'+extension),'probe_key':'right','probe_threshold':'1'},content_type='multipart/form-data')
                self.assertEqual(analyzed.status_code,200)
                token=next(reversed(cache.ENTRIES))
                candidate=next(c for c in cache.ENTRIES[token]['candidates'] if c['config']['method']=='jpeg_dct' and c['config']['mode']==mode)
                handoff=self.client.post('/extract',data={'analysis_token':token,'candidate':candidate['id'],'output':'file'})
                self.assertEqual(handoff.data,bytes(range(100)))

    def test_wrong_domain_rejected(self):
        raw=jpeg_bytes(fixture())
        for method in ('replacement','matching','lsbmr'):
            result=self.client.post('/',data={'image':(io.BytesIO(raw),'a.jpg'),'message':'test','method':method},content_type='multipart/form-data')
            self.assertEqual(result.status_code,400)
        raw=write_lossless(fixture(),'PNG').getvalue()
        result=self.client.post('/',data={'image':(io.BytesIO(raw),'a.png'),'method':'jpeg_dct'},content_type='multipart/form-data')
        self.assertEqual(result.status_code,400)

if __name__=='__main__':
    unittest.main()
