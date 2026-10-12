"""HTTP integration checks for the local engine and batch naming."""
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zipfile

import any2any as a
from web_app import Engine, PAGES


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(0)
        cls.thread = threading.Thread(target=cls.engine.serve_forever, daemon=True)
        cls.thread.start()
        cls.token = cls.engine.token

    @classmethod
    def tearDownClass(cls):
        cls.engine.shutdown()
        cls.engine.close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None, token=True):
        connection = HTTPConnection('127.0.0.1', self.engine.server_port, timeout=30)
        sent = {'Origin': PAGES}
        if token:
            sent['X-Any2Any-Token'] = self.token
        sent.update(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            sent['Content-Type'] = 'application/json'
        connection.request(method, path, body, sent)
        response = connection.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), data)
        connection.close()
        return result

    def batch(self):
        code, _, body = self.request('POST', '/api/batches')
        self.assertEqual(code, 201)
        return '/api/batches/' + json.loads(body)['id']

    def upload(self, batch, name, data, group='1', expected=201):
        code, _, body = self.request('POST', batch + '/files', data,
            {'X-File-Name': quote(name), 'X-File-Group': group})
        self.assertEqual(code, expected, body)
        return json.loads(body)

    def convert(self, batch, target, sources=None):
        request = {'target': target}
        if sources is not None:
            request['sources'] = sources
        code, _, body = self.request('POST', batch + '/convert', request)
        self.assertEqual(code, 202, body)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            code, _, body = self.request('GET', batch)
            self.assertEqual(code, 200)
            state = json.loads(body)
            if state['state'] != 'running':
                return state
            time.sleep(.02)
        self.fail('Conversion timed out')

    def test_origin_host_token_and_paths(self):
        code, headers, data = self.request('GET', '/api/health', token=False)
        self.assertEqual(code, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
        self.assertEqual(json.loads(data)['app'], 'Any2Any')
        for headers in ({'Origin': 'https://example.com'}, {'Origin': 'null'}, {'Host': 'evil.test'}):
            self.assertEqual(self.request('GET', '/api/health', headers=headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/batches', token=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/batches', headers={'X-Any2Any-Token': 'wrong'})[0], 403)
        code, headers, _ = self.request('OPTIONS', '/api/batches', token=False)
        self.assertEqual(code, 204)
        self.assertEqual(headers['Access-Control-Allow-Private-Network'], 'true')
        self.assertEqual(self.request('GET', '/../../README.md')[0], 404)
        self.assertEqual(self.request('GET', '/%2e%2e/README.md')[0], 404)
        for asset in ('/', '/app.js', '/style.css', '/icon.svg'):
            self.assertEqual(self.request('GET', asset)[0], 200)
        batch = self.batch()
        for name in ('../outside.png', '..', 'a/b.png', 'a\\b.png', 'a:stream', 'bad.png.', 'CON', 'NUL.txt', 'COM1.png'):
            self.upload(batch, name, b'x', expected=400)
        self.upload(batch, 'file.png', b'x', group='../2', expected=400)
        self.assertEqual(self.request('POST', batch + '/convert', {'target': '../jpg'})[0], 400)
        self.assertEqual(self.request('GET', batch + '/download')[0], 409)
        self.assertEqual(self.request('DELETE', batch)[0], 200)
        self.assertEqual(self.request('GET', batch)[0], 404)

    def test_collision_download_preservation(self):
        batch = self.batch()
        digest = {}
        for ext, color in [('png', (10, 20, 30, 0)), ('tiff', (40, 50, 60, 100))]:
            stream = io.BytesIO()
            a.Image.new('RGBA', (12, 9), color).save(stream, format='PNG' if ext == 'png' else 'TIFF')
            data = stream.getvalue()
            digest[ext] = hashlib.sha256(data).hexdigest()
            result = self.upload(batch, f'sample.{ext}', data, group=str(len(digest)))
            self.assertIn('jpg', result['targets'])
        state = self.convert(batch, 'jpg')
        self.assertEqual(state['state'], 'complete')
        self.assertEqual(state['download'], 'Any2Any.zip')
        code, _, data = self.request('GET', batch + '/download')
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            self.assertIn('sample_png.jpg', names)
            self.assertIn('sample_tiff.jpg', names)
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all('/' not in name and '\\' not in name for name in names))
            self.assertIsNone(archive.testzip())
            for name in names:
                if name.endswith('.json'):
                    metadata = json.loads(archive.read(name))
                    for item in metadata.get('preserved_files', []):
                        self.assertIn(item['file'], names)
            for name in ('sample_png.jpg', 'sample_tiff.jpg'):
                with a.Image.open(io.BytesIO(archive.read(name))) as image:
                    image.load()
                    self.assertEqual(image.size, (12, 9))
        actual = self.engine.batches[batch.rsplit('/', 1)[-1]]
        for item in actual.files.values():
            self.assertEqual(hashlib.sha256(item['path'].read_bytes()).hexdigest(), digest[item['path'].suffix[1:]])
        self.assertEqual(self.request('POST', batch + '/files', b'x')[0], 409)

    def test_single_output_partial_errors_and_duplicate_folders(self):
        batch = self.batch()
        content = b'1\n00:00:00,000 --> 00:00:01,000\nHello\n'
        self.upload(batch, 'caption.srt', content)
        state = self.convert(batch, 'vtt')
        self.assertEqual(state['download'], 'caption.vtt')
        self.assertTrue(self.request('GET', batch + '/download')[2].startswith(b'WEBVTT'))
        batch = self.batch()
        stream = io.BytesIO()
        a.Image.new('RGB', (8, 8), 'red').save(stream, format='PNG')
        self.upload(batch, 'same.png', stream.getvalue(), '1')
        self.upload(batch, 'same.png', stream.getvalue(), '1', expected=400)
        self.upload(batch, 'same.png', stream.getvalue(), '2')
        self.upload(batch, 'broken.png', b'not an image', '3')
        state = self.convert(batch, 'png')
        self.assertEqual(state['state'], 'partial')
        self.assertEqual(len(state['errors']), 1)
        with zipfile.ZipFile(io.BytesIO(self.request('GET', batch + '/download')[2])) as archive:
            self.assertIn('same.png', archive.namelist())
            self.assertIn('same_1.png', archive.namelist())
            self.assertFalse(any(name.startswith('broken') for name in archive.namelist()))

    def test_companions_removal_and_cancellation(self):
        batch = self.batch()
        source = self.upload(batch, 'record.srt', b'subtitles', '5')
        companion = self.upload(batch, 'record.eeg', b'raw signals', '5')
        self.assertEqual(companion['targets'], [])
        self.assertEqual(self.request('DELETE', batch + '/files/' + companion['id'])[0], 200)
        self.upload(batch, 'record.eeg', b'raw signals', '5')
        entered = threading.Event()
        def slow_convert(path, target, output, cancel, output_stem=None):
            self.assertTrue(path.with_suffix('.eeg').is_file())
            entered.set()
            if not cancel.wait(5):
                raise AssertionError('Cancel was not delivered')
            a.check_cancel(cancel)
        with patch('any2any.convert', slow_convert):
            self.assertEqual(self.request('POST', batch + '/convert', {'target': 'vtt'})[0], 202)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.request('POST', batch + '/cancel')[0], 200)
            actual = self.engine.batches[batch.rsplit('/', 1)[-1]]
            deadline = time.monotonic() + 5
            while actual.state == 'running' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(actual.state, 'cancelled')
            self.assertEqual(list(actual.output.iterdir()), [])
        self.assertEqual(self.request('GET', batch + '/download')[0], 409)
        self.assertEqual(self.request('DELETE', batch)[0], 200)
        self.assertFalse(actual.root.exists())
        batch = self.batch()
        self.upload(batch, 'one.srt', b'subtitles')
        actual = self.engine.batches[batch.rsplit('/', 1)[-1]]
        def produce(path, target, output, cancel, output_stem=None):
            (output / 'one.vtt').write_bytes(b'first')
            (output / 'two.vtt').write_bytes(b'second')
        original_write = zipfile.ZipFile.write
        def cancel_packaging(archive, filename, arcname):
            original_write(archive, filename, arcname)
            actual.cancel.set()
        with patch('any2any.convert', produce), patch('zipfile.ZipFile.write', cancel_packaging):
            state = self.convert(batch, 'vtt')
        self.assertEqual(state['state'], 'cancelled')
        self.assertIsNone(state['download'])
        self.assertEqual(self.request('GET', batch + '/download')[0], 409)

    def test_recognized_companion_document(self):
        batch = self.batch()
        image = io.BytesIO()
        a.Image.new('RGB', (12, 9), 'green').save(image, format='PNG')
        self.upload(batch, 'diagram.png', image.getvalue())
        document = self.upload(batch, 'document.html', b'<html><body><p>Diagram</p><img src="diagram.png"></body></html>')
        self.assertEqual(self.request('POST', batch + '/convert', {'target': 'docx', 'sources': ['missing']})[0], 400)
        self.assertEqual(self.request('POST', batch + '/convert', {'target': 'docx', 'sources': []})[0], 400)
        state = self.convert(batch, 'docx', [document['id']])
        self.assertEqual(state['state'], 'complete')
        self.assertEqual(state['total'], 1)
        self.assertEqual(state['download'], 'document.docx')
        with zipfile.ZipFile(io.BytesIO(self.request('GET', batch + '/download')[2])) as archive:
            pictures = [name for name in archive.namelist() if name.startswith('word/media/')]
            self.assertEqual(len(pictures), 1)
            with a.Image.open(io.BytesIO(archive.read(pictures[0]))) as actual:
                self.assertEqual(actual.size, (12, 9))
                self.assertEqual(actual.getpixel((0, 0)), (0, 128, 0))

    def test_names_multipart_and_asset_links(self):
        self.assertEqual(a.batch_names(['a.png', 'a.tiff', 'b.jpg']), ['a_png', 'a_tiff', 'b'])
        self.assertEqual(a.batch_names(['A.PNG', 'a.tiff']), ['A_png', 'a_tiff'])
        self.assertEqual(a.batch_names(['a.fastq.gz', 'a.fasta']), ['a_fastq_gz', 'a_fasta'])
        self.assertEqual(a.batch_names(['one/a.png', 'two/a.png']), ['a', 'a'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for ext in ('srt', 'vtt'):
                (root / f'captions.{ext}').write_text(('WEBVTT\n\n' if ext == 'vtt' else '1\n') + '00:00:00.000 --> 00:00:01.000\nHello\n')
            command = subprocess.run([sys.executable, '-X', 'utf8', str(a.ROOT / 'any2any.py'),
                str(root / 'captions.srt'), str(root / 'captions.vtt'), '--to', 'ass', '--out', str(root / 'cli')],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(command.returncode, 0, command.stdout + command.stderr)
            self.assertTrue((root / 'cli/captions_srt.ass').is_file())
            self.assertTrue((root / 'cli/captions_vtt.ass').is_file())
            source = root / 'sample.pdf'
            with a.pymupdf.open() as document:
                document.new_page().insert_text((30, 30), 'First')
                document.new_page().insert_text((30, 30), 'Second')
                document.save(source)
            results = a.convert(source, 'png', root / 'output', output_stem='sample_pdf')
            self.assertEqual([item.name for item in results], ['sample_pdf_0001.png', 'sample_pdf_0002.png'])
            results = a.convert(source, 'tex-layout', root / 'tex', output_stem='sample_pdf')
            text = results[0].read_text(encoding='utf-8')
            asset = next((root / 'tex').glob('*_asset_*.pdf'))
            self.assertIn(asset.name, text)
            with a.pymupdf.open(asset) as actual, a.pymupdf.open(source) as original:
                self.assertEqual(len(actual), len(original))
                for page, expected in zip(actual, original):
                    self.assertEqual(page.get_pixmap().samples, expected.get_pixmap().samples)


if __name__ == '__main__':
    unittest.main(verbosity=2)
