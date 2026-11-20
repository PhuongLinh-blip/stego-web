"""Kiểm thử phần phân tích cục bộ sau khi bỏ Gemini."""
import io
import random
import unittest
from unittest.mock import patch
from PIL import Image
from app import app
from core.algorithms import encode
from core.image_io import write_png
from core.analysis import cache


class LocalAnalysisTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        self.client=app.test_client()
        cache.ENTRIES.clear()
        self.image=Image.frombytes('RGB',(40,40),random.Random(3).randbytes(40*40*3))

    def test_no_cloud_or_ai_panel_even_with_old_form_field(self):
        with patch('urllib.request.urlopen') as network:
            response=self.client.post('/analyze',data={'image':(write_png(self.image),'a.png'),'use_ai':'yes'},content_type='multipart/form-data')
            self.assertEqual(response.status_code,200)
            network.assert_not_called()
            for removed in (b'Gemini',b'gemini-panel',b'name="use_ai"'):
                self.assertNotIn(removed,response.data)
            self.assertIn(b'Hex',response.data)
            self.assertIn(b'E1',response.data)

    def test_header_crc_and_handoff_still_work(self):
        image=encode(self.image,'Xin chào'.encode(),'lsbmr',1,'keyed','local-key')
        result=self.client.post('/analyze',data={'image':(write_png(image),'stego.png'),'probe_key':'local-key'},content_type='multipart/form-data')
        self.assertEqual(result.status_code,200)
        token=next(iter(cache.ENTRIES))
        candidate=next(c for c in cache.ENTRIES[token]['candidates'] if c['config']['mode']=='keyed')
        response=self.client.post('/extract',data={'analysis_token':token,'candidate':candidate['id'],'output':'text'})
        self.assertEqual(response.status_code,200)
        self.assertIn('Xin chào'.encode(),response.data)

    def test_clean_image_does_not_create_handoff(self):
        self.client.post('/analyze',data={'image':(write_png(self.image),'a.png')},content_type='multipart/form-data')
        self.assertFalse(cache.ENTRIES)

if __name__=='__main__':
    unittest.main()
