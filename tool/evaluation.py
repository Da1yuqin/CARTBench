"""Agent generation, rubric judging, tier scores, and saved evaluation runs."""
from collections import Counter
import json
import os
import re

from .client import Client, read_config
from .data import CAPABILITIES, ROOT, STATUSES, tier, validate_span
from .reporting import save_result_pages


def judge_messages(case, target_response):
    data = {'query_id': case['query_id'], 'input_sha256': case['input_sha256'],
            'input_messages': case['messages'], 'rubrics': case['rubrics'],
            'target_response': target_response}
    return [{'role': 'system', 'content': (ROOT / 'prompt/judge.md').read_text(encoding='utf-8')},
            {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}]

def parse_judgment(text):
    text = text.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, flags=re.S)
    if fenced:
        text = fenced[1].strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError('Judge output must be one JSON object.')
    return result

def validate_judgment(case, response, result):
    if set(result) != {'query_id', 'input_sha256', 'scores'}:
        raise ValueError('Judge output has unexpected top-level fields.')
    if result['query_id'] != case['query_id'] or result['input_sha256'] != case['input_sha256']:
        raise ValueError('Judge output is bound to a different input.')
    scores = result['scores']
    if not isinstance(scores, list):
        raise ValueError('Judge scores must be a list.')
    rubrics = {r['rubric_id']: r for r in case['rubrics']}
    ids = [s.get('rubric_id') if isinstance(s, dict) else None for s in scores]
    if len(ids) != len(rubrics) or set(ids) != set(rubrics):
        raise ValueError('Judge must return every rubric identifier exactly once.')
    required = {'rubric_id', 'status', 'response_quote', 'input_evidence', 'reason'}
    for score in scores:
        if not required <= score.keys() or not score.keys() <= required | {'applicability_quote'}:
            raise ValueError('A judge score has missing or unexpected fields.')
        if score['status'] not in STATUSES:
            raise ValueError('Unknown judgment status.')
        quote = score['response_quote']
        if not isinstance(quote, str) or (quote and quote not in response):
            raise ValueError('Response quote must be a contiguous verbatim substring.')
        if not isinstance(score['reason'], str) or not score['reason'].strip():
            raise ValueError('Each judgment needs a concise reason.')
        evidence = score['input_evidence']
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Each judgment needs input evidence.')
        for span in evidence:
            validate_span(case['messages'], span)
        if score['status'] == 'not_applicable':
            rubric = rubrics[score['rubric_id']]
            kind = rubric['applicability'].get('kind', '')
            trigger = score.get('applicability_quote')
            candidates = [rubric[k] for k in ('criterion', 'pass_condition', 'fail_condition')]
            if kind in {'conditional', 'response_conditional', 'response_triggered'}:
                candidates.append(rubric['applicability'].get('trigger', ''))
            if kind in {'always', 'required'} or not isinstance(trigger, str) or not trigger:
                raise ValueError('Not-applicable needs an explicit permitted conditional trigger.')
            if not any(trigger in candidate for candidate in candidates):
                raise ValueError('Applicability quote does not occur in the declared conditions.')
            if kind not in {'conditional', 'response_conditional', 'response_triggered'} and not re.search(
                    r'\u82e5|\u5982\u679c|\u4ec5\u5728|\u5982\u9700|\u5f53.{1,100}\u65f6|\u65f6[\uff0c,]|\b(if|when|only)\b', trigger, re.I):
                raise ValueError('A required rubric cannot be waived without a specific condition.')
    return result

def aggregate(case, result):
    rubrics = {r['rubric_id']: r for r in case['rubrics']}
    groups = {name: Counter() for name in ('Core', 'Excellence', 'Safety', *CAPABILITIES)}
    for score in result['scores']:
        rubric = rubrics[score['rubric_id']]
        groups[tier(rubric)][score['status']] += 1
        if 'core_capability' in rubric:
            groups[rubric['core_capability']][score['status']] += 1
    summary = {}
    for group, counts in groups.items():
        resolved = counts['pass'] + counts['fail']
        summary[group] = {status: counts[status] for status in sorted(STATUSES)}
        summary[group]['resolved_pass_rate'] = counts['pass'] / resolved if resolved else None
    return summary

def pooled_rates(case_rates):
    pooled = {}
    for group in ('Core', 'Excellence', 'Safety', *CAPABILITIES):
        counts = {status: sum(r[group][status] for r in case_rates) for status in sorted(STATUSES)}
        resolved = counts['pass'] + counts['fail']
        counts['resolved_pass_rate'] = counts['pass'] / resolved if resolved else None
        pooled[group] = counts
    return pooled

def evaluate_case(case, config, client):
    response = client.complete(config['agent'], case['messages'])
    # Invalid structured judge output is retried with the same complete input.
    for attempt in range(client.retries + 1):
        output = client.complete(config['judge'], judge_messages(case, response))
        try:
            judgment = validate_judgment(case, response, parse_judgment(output))
            break
        except (ValueError, TypeError, KeyError):
            if attempt == client.retries:
                raise ValueError('Judge output failed the JSON/evidence contract after bounded retries.') from None
    return {'query_id': case['query_id'], 'input_sha256': case['input_sha256'],
            'agent_model': config['agent']['model'], 'judge_model': config['judge']['model'],
            'target_response': response, 'judgment': judgment, 'rates': aggregate(case, judgment)}

def run_cases(selected, config_path, on_result, on_progress=None):
    config, output_dir = read_config(config_path)
    client = Client(config.get('runtime', {}))
    for name in ('agent', 'judge'):
        endpoint = config[name]
        if not os.environ.get(endpoint['api_key_env']):
            raise ValueError('Set both API key environment variables named in the config.')
        if (not endpoint['base_url'].startswith(('https://', 'http://'))
                or endpoint['model'] == 'MODEL_NAME'):
            raise ValueError('Configure both endpoint URLs and model names before an API run.')
    if any((output_dir / (case['query_id'] + suffix)).exists()
           for case in selected for suffix in ('.json', '.html')):
        raise ValueError('An output already exists; choose a separate output_dir to preserve it.')
    case_rates = []
    for case in selected:
        if on_progress:
            on_progress(case['query_id'])
        result = evaluate_case(case, config, client)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also preserves an output created by another process.
        with (output_dir / (case['query_id'] + '.json')).open('x', encoding='utf-8') as file:
            file.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        save_result_pages(output_dir, case, result)
        case_rates.append(result['rates'])
        on_result(result)
    return pooled_rates(case_rates)
