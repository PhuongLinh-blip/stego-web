import io
import random
import unittest
from PIL import Image
from app import app
from core.algorithms import encode,decode,capacity
from core.positions import prepare
from core.image_io import read_image,write_png
from core.algorithms.lsbmr import encode_pair,pair_bits
from core.algorithms.matching import match_value

CONFIGS=[('replacement',1),('replacement',2),('replacement',3),('matching',1),('lsbmr',1)]
MODES=['sequential','keyed','adaptive','edge']


def image_fixture():
    rng=random.Random(123)
    return Image.frombytes('RGBA',(49,49),rng.randbytes(49*49*4))


class PositionTests(unittest.TestCase):
    def test_all_algorithms_and_positions(self):
        image=image_fixture()
        for method,k in CONFIGS:
            for mode in MODES:
                for data in (b'', 'Nội dung thử nghiệm'.encode(),bytes(range(128))):
                    with self.subTest(method=method,k=k,mode=mode,length=len(data)):
                        result=encode(image,data,method,k,mode,'Khoa-Tieng-Viet',12)
                        saved=read_image(write_png(result).getvalue())
                        self.assertEqual(decode(saved,method,k,mode,'Khoa-Tieng-Viet',12),data)
                        self.assertEqual(saved.getchannel('A').tobytes(),image.getchannel('A').tobytes())
                        if mode in ('adaptive','edge'):
                            before=list(prepare(image,mode,threshold=12).sites())
                            after=list(prepare(saved,mode,threshold=12).sites())
                            self.assertEqual(before,after)
                            a=image.convert('RGB').tobytes()
                            b=saved.convert('RGB').tobytes()
                            self.assertTrue(all((x&248)==(y&248) for x,y in zip(a,b)))

    def test_stable_matching_and_lsbmr_all_values(self):
        for value in range(256):
            for bit in (0,1):
                new=match_value(value,bit,stable=True)
                self.assertEqual(new&1,bit)
                self.assertEqual(new&248,value&248)
                self.assertLessEqual(abs(new-value),1)
        for x in range(256):
            for y in range(256):
                for a,b in ((0,0),(0,1),(1,0),(1,1)):
                    new_x,new_y=encode_pair(x,y,a,b,stable=True)
                    self.assertEqual(pair_bits(new_x,new_y),(a,b))
                    self.assertEqual(new_x&248,x&248)
                    self.assertEqual(new_y&248,y&248)
                    self.assertTrue(abs(new_x-x)<=1 and abs(new_y-y)<=1)

    def test_capacity_exact_and_overflow(self):
        image=image_fixture()
        for method,k in CONFIGS:
            for mode in MODES:
                size=capacity(image,method,k,mode,'key',12)
                data=b'x'*size
                output=encode(image,data,method,k,mode,'key',12)
                self.assertEqual(decode(output,method,k,mode,'key',12),data)
                with self.assertRaises(ValueError):
                    encode(image,data+b'x',method,k,mode,'key',12)

    def test_wrong_key_threshold_and_uniform_image(self):
        image=image_fixture()
        self.assertEqual(list(prepare(image,'keyed','A').sites()),list(prepare(image,'keyed','A').sites()))
        self.assertNotEqual(list(prepare(image,'keyed','A').sites()),list(prepare(image,'keyed','B').sites()))
        for method,k in CONFIGS:
            output=encode(image,b'test',method,k,'keyed','A')
            with self.assertRaises(ValueError):
                decode(output,method,k,'keyed','B')
            for mode in ('adaptive','edge'):
                flat=Image.new('RGB',(32,32),(150,150,150))
                self.assertEqual(capacity(flat,method,k,mode),0)
                with self.assertRaises(ValueError):
                    encode(flat,b'test',method,k,mode)
        for mode in ('adaptive','edge'):
            moderate=Image.new('RGB',(40,40))
            moderate.putdata([(80 if (x+y)%2 else 112,)*3 for y in range(40) for x in range(40)])
            output=encode(moderate,b'test','lsbmr',1,mode,threshold=12)
            with self.assertRaises(ValueError):
                decode(output,'lsbmr',1,mode,threshold=255)
        with self.assertRaises(ValueError):
            encode(image,b'test',mode='keyed',key='')
        for threshold in (0,256):
            with self.assertRaises(ValueError):
                encode(image,b'test',mode='edge',threshold=threshold)
        with self.assertRaises(ValueError):
            encode(image,b'test',mode='unknown')


class PositionWebTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        self.client=app.test_client()
        self.image=image_fixture()

    def test_forms_and_capacity_endpoint(self):
        for path in ('/','/extract'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            for mode in MODES:
                self.assertIn(('value="'+mode+'"').encode(),response.data)
        for method,k in CONFIGS:
            for mode in MODES:
                options={'method':method,'k':str(k),'position_mode':mode,'key':'test-key','threshold':'12'}
                response=self.client.post('/capacity',data={'image':(write_png(self.image),'a.png'),**options},content_type='multipart/form-data')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json['capacity_bytes'],capacity(self.image,method,k,mode,'test-key',12))

    def test_all_modes_text_and_files_http(self):
        for method,k in CONFIGS:
            for mode in MODES:
                for file_payload in (False,True):
                    options={'method':method,'k':str(k),'position_mode':mode,'key':'test-key','threshold':'12'}
                    data={'image':(write_png(self.image),'a.png'),'message':'Xin chào',**options}
                    if file_payload:
                        data['payload']=(io.BytesIO(bytes(range(64))),'test.bin')
                    response=self.client.post('/',data=data,content_type='multipart/form-data')
                    self.assertEqual(response.status_code,200)
                    result=self.client.post('/extract',data={'image':(io.BytesIO(response.data),'stego.png'),'output':'file' if file_payload else 'text',**options},content_type='multipart/form-data')
                    self.assertEqual(result.status_code,200)
                    if file_payload:
                        self.assertEqual(result.data,bytes(range(64)))
                    else:
                        self.assertIn('Xin chào'.encode(),result.data)
                        # Không phản chiếu khóa vào HTML trả về.
                        self.assertNotIn(b'value="test-key"',result.data)

    def test_invalid_options_and_legacy(self):
        for extra in ({'position_mode':'keyed'},{'position_mode':'edge','threshold':'abc'},{'position_mode':'edge','threshold':'0'}):
            response=self.client.post('/',data={'image':(write_png(self.image),'a.png'),'message':'test',**extra},content_type='multipart/form-data')
            self.assertEqual(response.status_code,400)
        from core.payload import pack
        # Nhúng theo đúng vòng lặp Replacement của bản đầu, không qua engine mới.
        for k in (1,2,3):
            image=self.image.copy()
            bits=''.join(format(byte,'08b') for byte in pack(b'legacy'))
            sites=prepare(image).sites()
            for start in range(0,len(bits),k):
                x,y,c=next(sites)
                pixel=list(image.getpixel((x,y)))
                pixel[c]=(pixel[c]&(255^((1<<k)-1)))|int(bits[start:start+k].ljust(k,'0'),2)
                image.putpixel((x,y),tuple(pixel))
            self.assertEqual(decode(image,'replacement',k),b'legacy')

if __name__=='__main__':
    unittest.main()
