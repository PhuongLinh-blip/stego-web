"""Kiểm tra phiên bản cục bộ và endpoint AI đã gỡ."""
import unittest
from unittest.mock import patch
from app import app
from core.analysis.gemini import explain,explain_bounded


class NoAITests(unittest.TestCase):
    def test_version(self):
        response=app.test_client().get('/api/health')
        self.assertEqual(response.json['build'],'format-v10-no-ai')
        self.assertEqual(response.headers['X-Stego-Build'],'format-v10-no-ai')

    def test_ai_endpoint_removed(self):
        with patch('urllib.request.urlopen') as network:
            response=app.test_client().post('/analyze/gemini',data={'analysis_token':'anything'})
            self.assertEqual(response.status_code,404)
            network.assert_not_called()

    def test_old_imports_are_inert(self):
        with patch('urllib.request.urlopen') as network:
            self.assertEqual(explain({})['status'],'disabled')
            self.assertEqual(explain_bounded({})['status'],'disabled')
            network.assert_not_called()

if __name__=='__main__':
    unittest.main()
