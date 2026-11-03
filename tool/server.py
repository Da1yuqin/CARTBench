"""Loopback-only benchmark review and explicit API run controls."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import threading
from urllib.parse import urlsplit

from .client import config_metadata, read_config
from .data import ROOT, load_json, prepare_case, validate_dataset
from .evaluation import run_cases


def serve(config_path, port):
    """Serve read-only data inspection and explicit API runs on the loopback interface."""
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    job = {'status': 'idle', 'total': 0, 'completed': 0, 'current_case': None,
           'results': [], 'pooled_rates': None, 'error': None}

    def run_job(selected):
        def progress(case_id):
            with lock:
                job['current_case'] = case_id

        def complete(result):
            with lock:
                job['completed'] += 1
                job['results'].append({key: result[key] for key in
                                       ('query_id', 'target_response', 'rates')})
                job['results'][-1]['page'] = '/results/' + result['query_id'] + '.html'

        try:
            rates = run_cases(selected, config_path, complete, progress)
            with lock:
                job.update(status='completed', current_case=None, pooled_rates=rates)
        except Exception as error:
            message = str(error)
            # Provider credentials must not reach the browser, including through errors.
            for name in ('agent', 'judge'):
                try:
                    env_name = load_json(config_path)[name]['api_key_env']
                    key = os.environ.get(env_name)
                    if key:
                        message = message.replace(key, '[redacted]')
                except (ValueError, KeyError, TypeError, OSError):
                    pass
            with lock:
                job.update(status='failed', current_case=None, error=message)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def reply(self, status, content, content_type='application/json; charset=utf-8', headers=None):
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False).encode('utf-8')
            elif isinstance(content, str):
                content = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

        def valid_host(self):
            return self.headers.get('Host') in {'127.0.0.1:' + str(self.server.server_port),
                                               'localhost:' + str(self.server.server_port)}

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {'error': 'Use the local server address.'})
            path = urlsplit(self.path).path
            redirects = {
                '/examples': '/examples/index.html', '/examples/': '/examples/index.html',
                '/results': '/results/index.html', '/results/': '/results/index.html',
            }
            if path in redirects:
                return self.reply(302, '', headers={'Location': redirects[path]})
            pages = {
                '/': 'review/check.html', '/check': 'review/check.html',
                '/review': 'review/check.html', '/review/check.html': 'review/check.html',
                '/run': 'runner/run.html', '/runner/run.html': 'runner/run.html',
                '/examples/index.html': 'examples/index.html',
            }
            if path in pages:
                return self.reply(200, (ROOT / pages[path]).read_bytes(), 'text/html; charset=utf-8')
            example = re.fullmatch(r'/examples/([A-Za-z][A-Za-z0-9_-]{0,63})\.html', path)
            if example:
                allowed = {case['query_id'] for case in load_json(ROOT / 'data/data.json')}
                page = ROOT / 'examples' / (example[1] + '.html')
                if example[1] in allowed and page.is_file():
                    return self.reply(200, page.read_bytes(), 'text/html; charset=utf-8')
                return self.reply(404, {'error': 'Example not found.'})
            if re.fullmatch(r'/assets/(?:example/)?[A-Za-z][A-Za-z0-9_-]*\.(?:png|svg)', path):
                image = ROOT / path.lstrip('/')
                if image.is_file():
                    content_type = 'image/svg+xml' if image.suffix == '.svg' else 'image/png'
                    return self.reply(200, image.read_bytes(), content_type)
                return self.reply(404, {'error': 'Image not found.'})
            if path == '/api/data':
                return self.reply(200, load_json(ROOT / 'data/data.json'))
            if path == '/api/validate':
                try:
                    summary = validate_dataset(load_json(ROOT / 'data/data.json'))
                    return self.reply(200, {'valid': True, 'summary': summary})
                except (ValueError, KeyError, TypeError, OSError) as error:
                    return self.reply(422, {'valid': False, 'error': str(error)})
            if path == '/api/config':
                return self.reply(200, {'config': config_metadata(config_path), 'token': token})
            if path == '/api/job':
                with lock:
                    state = deepcopy(job)
                return self.reply(200, state)
            if re.fullmatch(r'/results/(?:index|[A-Za-z][A-Za-z0-9_-]{0,63})\.(?:html|json)', path):
                try:
                    _, output_dir = read_config(config_path)
                except (ValueError, KeyError, TypeError, OSError):
                    return self.reply(404, {'error': 'Configure an output directory and run an evaluation first.'})
                name = path.rsplit('/', 1)[-1]
                allowed = {case['query_id'] for case in load_json(ROOT / 'data/data.json')}
                if name != 'index.html' and name.rsplit('.', 1)[0] not in allowed:
                    return self.reply(404, {'error': 'Evaluation result not found.'})
                page = output_dir / name
                if page.is_file():
                    content_type = ('text/html' if name.endswith('.html') else 'application/json')
                    return self.reply(200, page.read_bytes(), content_type + '; charset=utf-8')
                return self.reply(404, {'error': 'Run an evaluation to create result pages.'})
            return self.reply(404, {'error': 'Page not found.'})

        def do_POST(self):
            if (not self.valid_host() or self.headers.get('Origin') !=
                    'http://' + self.headers.get('Host', '') or not secrets.compare_digest(
                        self.headers.get('X-CARTBench-Token', ''), token)):
                return self.reply(403, {'error': 'Run requests must come from this local page.'})
            if urlsplit(self.path).path != '/api/run':
                return self.reply(404, {'error': 'Page not found.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('A short JSON selection is required.')
                selection = json.loads(self.rfile.read(length))
                if not isinstance(selection, dict) or set(selection) != {'case_id'}:
                    raise ValueError('Select one case identifier or all.')
                cases = load_json(ROOT / 'data/data.json')
                validate_dataset(cases)
                selected = [prepare_case(case) for case in cases if
                            selection['case_id'] == 'all' or case['query_id'] == selection['case_id']]
                if not selected:
                    raise ValueError('The selected case identifier is not in the dataset.')
                if not config_metadata(config_path)['ready']:
                    raise ValueError('Configure both endpoints and API key environment variables before running.')
                with lock:
                    if job['status'] == 'running':
                        return self.reply(409, {'error': 'A run is already in progress.'})
                    job.update(status='running', total=len(selected), completed=0, current_case=None,
                               results=[], pooled_rates=None, error=None)
                    state = deepcopy(job)
                threading.Thread(target=run_job, args=(selected,), daemon=True).start()
                return self.reply(202, state)
            except (ValueError, KeyError, TypeError, OSError) as error:
                return self.reply(400, {'error': str(error)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    address = 'http://127.0.0.1:' + str(server.server_port)
    print('Expert review: ' + address + '/review', flush=True)
    print('API runner:   ' + address + '/run', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
