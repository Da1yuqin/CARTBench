"""Run CARTBench through OpenAI-compatible Chat Completions endpoints."""
import argparse
import json
from pathlib import Path

from .data import ROOT, fingerprint, load_json, prepare_case, validate_dataset
from .evaluation import judge_messages, run_cases
from .server import serve


def execute(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--case', help='A case identifier, such as H08.')
    selection.add_argument('--all', action='store_true', help='Select all 169 cases.')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true', help='Validate inputs and prompts without API calls.')
    action.add_argument('--run', action='store_true', help='Generate and judge the selected cases through APIs.')
    action.add_argument('--serve', action='store_true', help='Open the local data browser and API run pages.')
    parser.add_argument('--port', type=int, default=8765, help='Local web server port (default: 8765).')
    parser.add_argument('--config', default='config.json', help='Config path, relative to this runner directory.')
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if args.serve:
        if args.case or args.all:
            parser.error('--serve selects cases in the browser; omit --case and --all.')
        if not 0 <= args.port <= 65535:
            parser.error('The port must be between 0 and 65535.')
        return serve(config_path, args.port)
    if not args.case and not args.all:
        parser.error('Select --case or --all for a command-line run.')
    cases = load_json(ROOT / 'data/data.json')
    summary = validate_dataset(cases)
    selected = [prepare_case(c) for c in cases if args.all or c['query_id'] == args.case]
    if not selected:
        parser.error('The requested case identifier is not in the dataset.')
    if args.all:
        validate_dataset(selected)
    for case in selected:
        payload = json.loads(judge_messages(case, '')[1]['content'])
        if payload['input_sha256'] != fingerprint(payload['input_messages']):
            raise ValueError('Judge payload does not match the agent input.')
    if args.dry_run:
        print(json.dumps({'validated': summary, 'selected_cases': len(selected),
                          'api_requests': 0}, ensure_ascii=False))
        return 0
    def print_result(result):
        print(json.dumps({'query_id': result['query_id'], 'rates': result['rates']}, ensure_ascii=False))
    rates = run_cases(selected, config_path, print_result)
    if len(selected) > 1:
        print(json.dumps({'completed_cases': len(selected), 'pooled_rates': rates},
                         ensure_ascii=False))
    return 0


def main(argv=None):
    """Call the command interface with concise user-facing errors."""
    try:
        return execute(argv)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        raise SystemExit("Error: " + str(error)) from None
