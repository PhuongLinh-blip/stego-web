"""Chạy: python -m unittest discover -s tests -v"""
import io
import unittest
from unittest.mock import patch
from PIL import Image
from app import app
from core.algorithms import encode, decode, capacity
from core.algorithms.matching import match_value
from core.algorithms.lsbmr import encode_pair, pair_bits
from core.image_io import read_image, write_png


class AlgorithmsTest(unittest.TestCase):
    def test_lsbmr_all_pairs_and_messages(self):
        # Kiểm tra toàn bộ 65.536 cặp màu x 4 cặp bit, bao gồm biên.
        for x in range(256):
            for y in range(256):
                for first, second in ((0,0),(0,1),(1,0),(1,1)):
                    a, b = encode_pair(x,y,first,second)
                    self.assertEqual(pair_bits(a,b),(first,second))
                    self.assertTrue(0 <= a <= 255 and 0 <= b <= 255)
                    self.assertTrue(abs(a-x) <= 1 and abs(b-y) <= 1)
                    if 0 < x < 255:
                        self.assertLessEqual((a != x) + (b != y), 1)

    def test_matching_directions_and_bounds(self):
        for value in range(256):
            for bit in (0,1):
                out = match_value(value,bit)
                self.assertEqual(out & 1,bit)
                self.assertLessEqual(abs(out-value),1)
                self.assertTrue(0 <= out <= 255)
        with patch('core.algorithms.matching.choice', return_value=-1):
            self.assertEqual(match_value(150,1),149)
        with patch('core.algorithms.matching.choice', return_value=1):
            self.assertEqual(match_value(150,1),151)

    def test_roundtrip_and_preserve_alpha(self):
        for method,k in [('replacement',1),('replacement',2),('replacement',3),('matching',1),('lsbmr',1)]:
            for color in [(0,0,0,17),(255,255,255,199),(150,201,100,77)]:
                image=Image.new('RGBA',(41,41),color)
                for data in [b'', 'Xin chào Việt Nam'.encode(), bytes(range(256))]:
                    with self.subTest(method=method,k=k,color=color,data=len(data)):
                        result=encode(image,data,method,k)
                        saved=read_image(write_png(result).getvalue())
                        self.assertEqual(decode(saved,method,k),data)
                        self.assertEqual(saved.getchannel('A').tobytes(),image.getchannel('A').tobytes())
                        self.assertEqual(image.getpixel((0,0)),color)
                        self.assertEqual(saved.getpixel((40,40)),color)

    def test_capacity_and_rejection(self):
        image=Image.new('RGB',(16,16),(150,200,100))
        for method,k in [('replacement',1),('replacement',2),('replacement',3),('matching',1),('lsbmr',1)]:
            size=capacity(image,method,k)
            self.assertEqual(decode(encode(image,b'x'*size,method,k),method,k),b'x'*size)
            with self.assertRaises(ValueError):
                encode(image,b'x'*(size+1),method,k)
            damaged=encode(image,b'hello',method,k)
            value=list(damaged.getpixel((0,0)))
            value[0] ^= 1
            damaged.putpixel((0,0),tuple(value))
            with self.assertRaises(ValueError):
                decode(damaged,method,k)
        with self.assertRaises(ValueError):
            encode(image,b'a','other',1)
        for method in ('matching','lsbmr'):
            with self.assertRaises(ValueError):
                encode(image,b'a',method,3)
        for method in ('replacement','matching','lsbmr'):
            with self.assertRaises(ValueError):
                encode(Image.new('RGB',(1,1)),b'',method)


class WebTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        self.client=app.test_client()
        self.image=Image.new('RGB',(32,32),(150,201,100))

    def test_pages_show_three_methods(self):
        for path in ('/','/extract'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            for method in ('replacement','matching','lsbmr'):
                self.assertIn(f'value="{method}"'.encode(),response.data)

    def test_text_and_binary_api_roundtrips(self):
        for method in ('replacement','matching','lsbmr'):
            for fmt in ('PNG','BMP'):
                source=io.BytesIO()
                self.image.save(source,format=fmt)
                source.seek(0)
                response=self.client.post('/',data={'image':(source,'image.'+fmt.lower()),'method':method,'message':'Xin chào'},content_type='multipart/form-data')
                self.assertEqual(response.status_code,200)
                result=self.client.post('/extract',data={'image':(io.BytesIO(response.data),'stego.png'),'method':method,'output':'text'},content_type='multipart/form-data')
                self.assertEqual(result.status_code,200)
                self.assertIn('Xin chào'.encode(),result.data)
            data=bytes(range(256))
            response=self.client.post('/',data={'image':(write_png(self.image),'image.png'),'payload':(io.BytesIO(data),'file.bin'),'method':method},content_type='multipart/form-data')
            self.assertEqual(response.status_code,200)
            result=self.client.post('/extract',data={'image':(io.BytesIO(response.data),'stego.png'),'method':method,'output':'file'},content_type='multipart/form-data')
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.data,data)

    def test_legacy_default_and_invalid_method(self):
        response=self.client.post('/',data={'image':(write_png(self.image),'image.png'),'message':'old image','k':'2'},content_type='multipart/form-data')
        result=self.client.post('/extract',data={'image':(io.BytesIO(response.data),'stego.png'),'output':'text','k':'2'},content_type='multipart/form-data')
        self.assertEqual(result.status_code,200)
        self.assertIn(b'old image',result.data)
        for fields in ({'method':'bad'},{'method':'matching','k':'3'},{'method':'lsbmr','k':'2'}):
            response=self.client.post('/',data={'image':(write_png(self.image),'image.png'),'message':'test',**fields},content_type='multipart/form-data')
            self.assertEqual(response.status_code,400)
            self.assertIn(b'error-panel',response.data)

if __name__ == '__main__':
    unittest.main()
