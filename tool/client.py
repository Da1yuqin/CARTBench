"""OpenAI-compatible requests and credential-safe runtime configuration."""
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .data import load_json


class Client:
    def __init__(self, runtime):
        self.timeout = float(runtime.get('timeout', 300))
        self.retries = int(runtime.get('max_retries', 2))
        rpm = float(runtime.get('requests_per_minute', 5))
        if self.timeout <= 0 or not 0 <= self.retries <= 10 or rpm <= 0:
            raise ValueError('Timeout, retry count or request rate is invalid.')
        self.interval = 60 / rpm
        self.last_request = 0

    def complete(self, endpoint, messages):
        key = os.environ.get(endpoint['api_key_env'])
        if not key:
            raise ValueError('Set the API key environment variable named in the config.')
        base = endpoint['base_url'].rstrip('/')
        if not base.startswith(('https://', 'http://')) or endpoint['model'] == 'MODEL_NAME':
            raise ValueError('Configure an endpoint URL and model name before an API run.')
        payload = dict(endpoint.get('extra_body', {}))
        if {'messages', 'model', 'api_key', 'authorization'} & {k.lower() for k in payload}:
            raise ValueError('extra_body cannot override request messages, model or credentials.')
        payload.update(model=endpoint['model'], messages=messages,
                       temperature=endpoint.get('temperature', 0),
                       max_tokens=int(endpoint.get('max_tokens', 8192)))
        request = Request(base + '/chat/completions', data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with urlopen(request, timeout=self.timeout) as reply:
                    output = json.load(reply)
                choice = output['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ValueError('API output reached its token limit; increase max_tokens.')
                content = choice['message']['content']
                if isinstance(content, list):
                    content = ''.join(part.get('text', '') for part in content if part.get('type') == 'text')
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('API returned no text response.')
                return content
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt == self.retries:
                    raise RuntimeError('API request failed with HTTP ' + str(exc.code) + '.') from None
            except (URLError, TimeoutError):
                if attempt == self.retries:
                    raise RuntimeError('API request failed after bounded network retries.') from None
            time.sleep(min(30, 2 ** attempt))
        raise RuntimeError('API request did not complete.')

def read_config(config_path):
    config = load_json(config_path)
    output_dir = Path(config.get('output_dir', 'outputs'))
    if not output_dir.is_absolute():
        output_dir = config_path.resolve().parent / output_dir
    return config, output_dir

def config_metadata(config_path):
    if not config_path.is_file():
        return {'available': False, 'ready': False,
                'message': 'Copy config.example.json to config.json, configure your endpoints, '
                           'and export the two API key environment variables before starting a run.'}
    try:
        config, output_dir = read_config(config_path)
        Client(config.get('runtime', {}))
        metadata = {'available': True, 'endpoints': {}, 'ready': True,
                    'output_directory': output_dir.name}
        for name in ('agent', 'judge'):
            endpoint = config[name]
            url = urlsplit(endpoint['base_url'])
            hostname = url.hostname or ''
            if ':' in hostname:
                hostname = '[' + hostname + ']'
            if url.port:
                hostname += ':' + str(url.port)
            safe_url = urlunsplit((url.scheme, hostname, url.path, '', ''))
            key_set = bool(os.environ.get(endpoint['api_key_env']))
            configured = url.scheme in {'http', 'https'} and bool(url.hostname) and bool(
                endpoint['model']) and endpoint['model'] != 'MODEL_NAME'
            metadata['endpoints'][name] = {'base_url': safe_url, 'model': endpoint['model'],
                                           'api_key_env': endpoint['api_key_env'],
                                           'key_configured': key_set}
            metadata['ready'] = metadata['ready'] and configured and key_set
        return metadata
    except (ValueError, KeyError, TypeError, OSError):
        return {'available': True, 'ready': False,
                'message': 'The configuration is incomplete or invalid. Check config.json.'}
