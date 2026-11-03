"""Benchmark inputs, prompt preparation, and exact evidence validation."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
STATUSES = {'pass', 'fail', 'unresolved', 'not_applicable'}
CAPABILITIES = {'GA': 127, 'RA': 166, 'UP': 72, 'EF': 186, 'PV': 139, 'DS': 70}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()

def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def agent_prompt():
    text = (ROOT / 'prompt/agent.md').read_text(encoding='utf-8')
    if not text.strip():
        raise ValueError('Agent prompt must be nonempty.')
    return text

def decoded(message):
    try:
        return json.loads(message['content'])
    except json.JSONDecodeError:
        return message['content']

def source_text(messages, span):
    source = span.get('source')
    if source == 'documents':
        documents = decoded(messages[-1])['documents']
        matches = [d for d in documents if d['doc_id'] == span.get('doc_id')]
        if len(matches) != 1:
            raise ValueError('Document evidence must identify one supplied document.')
        value = matches[0]['content']
    else:
        match = re.fullmatch(r'messages\[(\d+)\]\.(content|query|timestamp)', source or '')
        if not match or int(match[1]) >= len(messages):
            raise ValueError('Evidence source does not identify a supplied message.')
        item = decoded(messages[int(match[1])])
        value = item.get(match[2]) if isinstance(item, dict) else (
            item if match[2] == 'content' else None)
        if 'timestamp' in span and (not isinstance(item, dict)
                                   or span['timestamp'] != item.get('timestamp')):
            raise ValueError('Evidence timestamp differs from its message.')
    if not isinstance(value, str):
        raise ValueError('Evidence source must resolve to text.')
    return value

def validate_span(messages, span):
    if not isinstance(span, dict):
        raise ValueError('Each evidence entry must be an object.')
    quote = span.get('quote')
    if not isinstance(quote, str) or not quote or quote not in source_text(messages, span):
        raise ValueError('Evidence quotes must occur verbatim in the specified source.')

def tier(rubric):
    if rubric['dimension'] == 'Safety':
        return 'Safety'
    return 'Excellence' if rubric.get('evaluation_tier', 'core') == 'enhancement' else 'Core'

def validate_dataset(cases):
    if not isinstance(cases, list) or len(cases) != 169:
        raise ValueError('Expected the complete 169-case dataset.')
    case_ids, rubric_ids, counts, capabilities = set(), set(), Counter(), Counter()
    for case in cases:
        if set(case) != {'query_id', 'messages', 'input_sha256', 'rubrics'}:
            raise ValueError('Unexpected case schema.')
        case_id = case['query_id']
        if not isinstance(case_id, str) or case_id in case_ids:
            raise ValueError('Case identifiers must be unique strings.')
        case_ids.add(case_id)
        messages = case['messages']
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError('A case needs system context and a current user message.')
        if messages[0]['role'] != 'system' or messages[-1]['role'] != 'user':
            raise ValueError('System and final user message positions must be preserved.')
        if any(set(m) != {'role', 'content'} or not isinstance(m['content'], str)
               or m['role'] not in {'system', 'user', 'assistant'} for m in messages):
            raise ValueError('Invalid Chat Completions message schema.')
        final = decoded(messages[-1])
        if not isinstance(final, dict) or not {'timestamp', 'query', 'user_profile', 'documents'} <= final.keys():
            raise ValueError('The final message needs timestamp, query, user_profile and documents.')
        documents = final['documents']
        if not isinstance(documents, list) or len({d['doc_id'] for d in documents}) != len(documents):
            raise ValueError('Product document identifiers must be unique within each case.')
        for doc in documents:
            if not all(isinstance(doc.get(k), str) for k in ('doc_id', 'title', 'content')):
                raise ValueError('Product records need doc_id, title and content strings.')
        if fingerprint(messages) != case['input_sha256']:
            raise ValueError('Input hash does not match the supplied messages.')
        for rubric in case['rubrics']:
            required = {'rubric_id', 'dimension', 'criterion', 'pass_condition', 'fail_condition',
                        'source_spans', 'applicability', 'unresolved_condition',
                        'acceptable_alternatives', 'bound_input_sha256'}
            if not required <= rubric.keys():
                raise ValueError('Incomplete rubric contract.')
            rubric_id = rubric['rubric_id']
            if not isinstance(rubric_id, str) or rubric_id in rubric_ids:
                raise ValueError('Rubric identifiers must be unique strings.')
            rubric_ids.add(rubric_id)
            if rubric['bound_input_sha256'] != case['input_sha256']:
                raise ValueError('Rubric binding differs from the case input hash.')
            if rubric.get('evaluation_tier', 'core') not in {'core', 'enhancement'}:
                raise ValueError('Unknown evaluation tier.')
            for field in ('criterion', 'pass_condition', 'fail_condition'):
                if not isinstance(rubric[field], str) or not rubric[field]:
                    raise ValueError('Rubric conditions must be nonempty text.')
            if not isinstance(rubric['applicability'], dict) or not rubric['source_spans']:
                raise ValueError('Rubric applicability and source evidence are required.')
            for span in rubric['source_spans']:
                validate_span(messages, span)
            group = tier(rubric)
            counts[group] += 1
            if group == 'Core':
                capability = rubric.get('core_capability')
                if capability not in CAPABILITIES:
                    raise ValueError('Every Core rubric needs its assigned capability.')
                capabilities[capability] += 1
            elif 'core_capability' in rubric:
                raise ValueError('Only Core rubrics may carry a Core capability.')
    if counts != Counter({'Core': 760, 'Excellence': 553, 'Safety': 15}):
        raise ValueError('Dataset rubric counts do not match the benchmark.')
    if capabilities != Counter(CAPABILITIES):
        raise ValueError('Core capability mapping does not match the benchmark.')
    return {'cases': len(cases), 'rubrics': len(rubric_ids), 'tiers': dict(counts),
            'core_capabilities': dict(capabilities)}

def prepare_case(case):
    case = deepcopy(case)
    case['messages'][0]['content'] = agent_prompt()
    case['input_sha256'] = fingerprint(case['messages'])
    for rubric in case['rubrics']:
        rubric['bound_input_sha256'] = case['input_sha256']
    return case
