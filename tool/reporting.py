"""Portable shopping-guide pages with safe reply formatting and rubric evidence."""
import base64
from datetime import datetime
import hashlib
from html import escape, unescape
import json
import re
from urllib.parse import unquote, urlsplit

from .data import ROOT, decoded, load_json, tier


SCENARIOS = {
    'H06': ('Hospital-bag essentials', 'Prepare thoughtfully. Pack with purpose.',
            'A practical shopping request about existing supplies, a small bag, and decisions that depend on hospital and feeding arrangements.',
            'hospital-bag.svg', 'Care & preparation'),
    'N130': ('A weekend outfit, considered', 'One shirt. A more relaxed occasion.',
             'A dark-blue shirt stays fixed while trousers, shoes, and the earlier budget need to fit a changed occasion.',
             'weekend-outfit.png', 'Style & everyday life'),
    'S002': ('Cold-weather camera gloves', 'Warmth, dexterity, and the limits of evidence.',
             'A stationary snow-photography request balances two-hour cold exposure, camera controls, an existing fleece liner, and warmth independent of electricity.',
             'cold-weather-gloves.svg', 'Outdoors & photography'),
    'H02': ('Camera carry, measured', 'Keep the lens attached. Check the fit.',
            'A camera-bag request combines a revised CNY 800 budget with carrying a body and long lens together, while allowing alternatives to a backpack.',
            'camera-carry.svg', 'Photography & travel'),
    'H04': ('An aquarium, planned', 'Buy in the right order.',
            'A beginner already owns a tank, air pump, and airline tubing; filtration and heating choices depend on tank measurements and the eventual fish.',
            'aquarium-setup.svg', 'Home & aquatic care'),
    'N029': ('Move-in essentials', 'Buy less. Check what is already there.',
             'A dormitory shopping request separates existing supplies, school-provided items, and purchases that depend on the unmeasured mattress.',
             'dorm-essentials.svg', 'Everyday life & preparation'),
}
DEFAULT_SCENARIO = ('Shopping guidance', 'A choice shaped by the request.',
                    'Read the complete shopping reply, then inspect how it meets the case-specific requirements.',
                    'shopping-guide.svg', 'Shopping advice')
INLINE = re.compile(r'(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\n)]+\))')
WEB_ADDRESS = re.compile(r'https?://[^\s<>\"]+|(?:www\.)?(?:[a-z0-9-]+\.)+(?:com|org|net|edu|gov|io|co|us|uk|cn|ca|au|eu|de|fr|jp|shop|store)\b(?:/[^\s<>\"]*)?', re.I)
WEB_LINK = re.compile(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)', re.I)


def text(value):
    return escape(str(value), quote=True)


def scenario(case_id):
    return SCENARIOS.get(case_id, DEFAULT_SCENARIO)


def asset_art(filename, label='Shopping category illustration'):
    """Embed local artwork so saved output pages remain self-contained."""
    path = ROOT / 'assets' / 'example' / filename
    if path.suffix.lower() == '.png':
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        return '<img src="data:image/png;base64,' + encoded + '" alt="' + text(label) + '">'
    artwork = path.read_text(encoding='utf-8')
    return re.sub(r'\s+xmlns(?:\:[a-z]+)?="[^"]*"', '', artwork)


def illustration(case_id):
    return asset_art(scenario(case_id)[3])


def normalized_words(value):
    return ' '.join(re.sub(r'[^\w]+', ' ', value.casefold()).split())


def product_records(latest):
    records = []
    for document in latest.get('documents', []):
        item = document.get('content', {})
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except (ValueError, TypeError):
                item = {}
        if not isinstance(item, dict):
            item = {}
        title = str(document.get('title', item.get('title', 'Product record')))
        aliases = {normalized_words(title)}
        for fragment in re.split(r'\s+-\s+|\|', title):
            alias = normalized_words(fragment)
            if len(alias) >= 5 and not alias.isdigit() and alias not in {'white', 'black', 'ivory', 'dark navy'}:
                aliases.add(alias)
        short_title = re.sub(r'\s+in\s+(?:black|white|blue|ivory)$', '', title, flags=re.I)
        aliases.add(normalized_words(short_title))
        brand = item.get('brand', '')
        records.append({'doc_id': str(document.get('doc_id', '')), 'title': title,
                        'brand': brand if isinstance(brand, str) else '',
                        'aliases': aliases})
    return records


class Presentation:
    """Resolve visible web references to supplied product labels without editing results."""
    def __init__(self, case=None):
        self.case_id = case['query_id'] if case else ''
        latest = decoded(case['messages'][-1]) if case else {}
        self.products = product_records(latest)
        labels_path = ROOT / 'assets' / 'product_labels.json'
        self.labels = load_json(labels_path).get(self.case_id, {}) if labels_path.is_file() else {}

    def label(self, address, nearby=''):
        value = unescape(address).rstrip('.,;:!?)\\]}\'\"').rstrip('/')
        key = hashlib.sha256(value.encode('utf-8')).hexdigest()
        exact = self.labels.get('urls', {}).get(key)
        if exact:
            return exact
        try:
            parsed = urlsplit(value if '://' in value else 'https://' + value)
        except ValueError:
            return 'Product reference'
        hostname = (parsed.hostname or '').lower().removeprefix('www.')
        domain_key = hashlib.sha256(hostname.encode('utf-8')).hexdigest()
        candidates = self.labels.get('domains', {}).get(domain_key, [])
        context = ' ' + normalized_words(nearby) + ' '
        for product in self.products:
            if (not candidates or product['title'] in candidates) and any(
                    ' ' + alias + ' ' in context for alias in product['aliases']):
                return product['title']
        path_words = set(normalized_words(unquote(parsed.path)).split())
        ranked = sorted(self.products, key=lambda product: len(
            path_words & set(normalized_words(product['title']).split())), reverse=True)
        if ranked and path_words & set(normalized_words(ranked[0]['title']).split()):
            return ranked[0]['title']
        if candidates and not parsed.path.strip('/'):
            brands = [product['brand'] for product in self.products
                      if product['title'] in candidates and product['brand']]
            if brands:
                return ', '.join(dict.fromkeys(brands))
        if candidates:
            return ', '.join(dict.fromkeys(candidates))
        return 'Product reference'

    def visible(self, value):
        value = str(value)
        value = WEB_LINK.sub(lambda match: self.label(match.group(2), match.group(1)), value)
        value = re.sub(r'\((?:source|sources)\s*:\s*(https?://[^\s)]+)\)',
                       lambda match: '(' + self.label(match.group(1), value) + ')', value, flags=re.I)
        def replace(match):
            address = match.group()
            trimmed = address.rstrip('.,;:!?)\\]}\'\"')
            return self.label(trimmed, value) + address[len(trimmed):]
        return WEB_ADDRESS.sub(replace, value)

    def text(self, value):
        return text(self.visible(value))


def inline_reply(value):
    """Format a small Markdown subset; never accept HTML or executable links."""
    parts, position = [], 0
    for match in INLINE.finditer(value):
        parts.append(text(value[position:match.start()]))
        token = match.group()
        if token.startswith('`'):
            parts.append('<code>' + text(token[1:-1]) + '</code>')
        elif token.startswith('**'):
            parts.append('<strong>' + text(token[2:-2]) + '</strong>')
        elif token.startswith('*'):
            parts.append('<em>' + text(token[1:-1]) + '</em>')
        elif token.startswith('['):
            label, url = token[1:].split('](', 1)
            url = url[:-1]
            if url.startswith('#') or re.fullmatch(r'[A-Za-z0-9_-]+\.html(?:#[A-Za-z0-9_-]+)?', url):
                parts.append('<a href="' + text(url) + '">' + text(label) + '</a>')
            else:
                parts.append(text(label))
        position = match.end()
    parts.append(text(value[position:]))
    return ''.join(parts)


def table_cells(line):
    value = line.strip()
    if value.startswith('|'):
        value = value[1:]
    if value.endswith('|') and not value.endswith('\\|'):
        value = value[:-1]
    return re.split(r'(?<!\\)\|', value)


def category_art(kind):
    shapes = {
        'bottle': '<rect x="87" y="41" width="66" height="15" rx="5" fill="#cfb68c"/><rect x="77" y="57" width="86" height="119" rx="22" fill="#e7d9b9"/><rect x="86" y="99" width="68" height="40" rx="9" fill="#fffaf0"/><path d="M98 119h44" stroke="#7b947b" stroke-width="5"/>',
        'gloves': '<path d="M65 169V99c0-16 14-20 23-9V58c0-11 16-11 16 0V49c0-11 16-11 16 0v6c0-11 16-11 16 0v7c0-11 16-11 16 0v76c0 22-15 39-33 39H88Z" fill="#6d7d69"/><path d="M72 151h62" stroke="#e1caa3" stroke-width="8"/><path d="M104 64v48m16-48v49m16-46v50" stroke="#52684f" stroke-width="3"/>',
        'bag': '<path d="M81 60c0-38 78-38 78 0" fill="none" stroke="#385347" stroke-width="9"/><rect x="61" y="53" width="118" height="121" rx="26" fill="#cba27a"/><rect x="71" y="112" width="98" height="50" rx="13" fill="#af825d"/><path d="M92 75h56m-43 17h30" stroke="#f2e2c6" stroke-width="5"/><path d="M98 129h44" stroke="#e8cdb0" stroke-width="4"/>',
        'aquarium': '<rect x="51" y="55" width="138" height="115" rx="9" fill="#d0e0d5" stroke="#456c5e" stroke-width="5"/><path d="M55 84h130v81H55Z" fill="#9bbdad"/><path d="M70 153c14-22 15-41 6-57m87 57c-14-22-15-38-9-51" stroke="#587d52" stroke-width="6" fill="none"/><ellipse cx="121" cy="113" rx="17" ry="10" fill="#d6a971"/><path d="m140 113 14-13v25Z" fill="#d6a971"/><circle cx="111" cy="111" r="2" fill="#385347"/>',
        'bedding': '<path d="M50 84h139v85H50Z" fill="#d9c7a8"/><path d="M50 104h139v56H50Z" fill="#f0e6cf"/><rect x="55" y="59" width="61" height="39" rx="12" fill="#eee0bf"/><path d="M121 103v57m-33-55v52m-35-31h134" stroke="#c5b9a0" stroke-width="2"/>',
        'shoe': '<path d="M56 142c21-5 36-16 48-43l31 12c8 17 17 26 40 31 11 2 16 8 16 18H52c-4-6-2-14 4-18Z" fill="#e1d3b3"/><path d="M53 158h138" stroke="#8b7e66" stroke-width="6"/><path d="m99 120 28 4m-36 6 32 4" stroke="#fcf8ee" stroke-width="4"/>',
        'care': '<rect x="61" y="72" width="118" height="91" rx="12" fill="#e5ccb1"/><path d="M61 92h118" stroke="#cbab87" stroke-width="4"/><rect x="84" y="112" width="70" height="28" rx="7" fill="#f7f0db"/><path d="M110 119h18m-9-8v27" stroke="#839b7e" stroke-width="5"/>',
    }
    return ('<svg viewBox="0 0 240 210" role="img" aria-label="Product category illustration">'
            '<rect width="240" height="210" rx="14" fill="#f6efe0"/>'
            '<ellipse cx="120" cy="178" rx="81" ry="8" fill="#e7dcc7"/>'
            + shapes.get(kind, shapes['care']) + '</svg>')


def product_art(product, case_id):
    previews = {'1': 'denim-trousers.png', '2': 'raffia-loafers.png', '3': 'white-sneakers.png',
                '6': 'white-black-sneakers.png', '9': 'velvet-loafers.png', '10': 'ivory-trousers.png'}
    if case_id == 'N130' and product['doc_id'] in previews:
        return asset_art(previews[product['doc_id']], 'Product illustration'), 'Product illustration'
    name = normalized_words(product['title'])
    if any(word in name for word in ('bottle', 'rinse', 'dechlorinator', 'cleaner')):
        kind = 'bottle'
    elif any(word in name for word in ('glove', 'mitt')):
        kind = 'gloves'
    elif any(word in name for word in ('backpack', 'bag', 'mover', 'prvke', 'retrospective', 'accelerator')):
        kind = 'bag'
    elif any(word in name for word in ('aquarium', 'filter', 'heater', 'pellet', 'gravel')):
        kind = 'aquarium'
    elif any(word in name for word in ('sheet', 'pillow', 'towel')):
        kind = 'bedding'
    elif any(word in name for word in ('slipper', 'loafer', 'sneaker')):
        kind = 'shoe'
    else:
        kind = 'care'
    return category_art(kind), 'Category illustration'


def product_cards(products, case_id):
    cards = []
    for product in products:
        art, caption = product_art(product, case_id)
        cards.append('<article class="shopping-product"><div class="shopping-product-art">' + art
                     + '</div><div class="shopping-product-body"><span class="preview-caption">'
                     + caption + '</span><h4>' + text(product['title']) + '</h4>'
                     + ('<p class="shopping-product-brand">' + text(product['brand']) + '</p>' if product['brand'] else '')
                     + '<button type="button" disabled aria-disabled="true">Add to bag</button></div></article>')
    return '<div class="shopping-products">' + ''.join(cards) + '</div>' if cards else ''


def render_reply(response, presentation=None):
    """Return safely formatted reply HTML and a heading navigation list."""
    presentation = presentation or Presentation()
    lines, parts, headings = response.splitlines(), [], []
    shown, pending_products = set(), []

    def matching_products(value):
        references = [presentation.label(match.group()) for match in WEB_ADDRESS.finditer(value)
                      if match.group().lower().startswith(('http://', 'https://'))]
        value = ' ' + normalized_words(value + ' ' + ' '.join(references)) + ' '
        return [product for product in presentation.products if product['doc_id'] not in shown
                and any(' ' + alias + ' ' in value for alias in product['aliases'])]

    def block(markup, value):
        parts.append(markup)
        selected = pending_products + matching_products(value)
        unique = {product['doc_id']: product for product in selected if product['doc_id'] not in shown}
        if unique:
            shown.update(unique)
            parts.append(product_cards(list(unique.values()), presentation.case_id))
        pending_products.clear()

    def formatted(value):
        return inline_reply(presentation.visible(value))

    position = 0
    while position < len(lines):
        line = lines[position].strip()
        if not line:
            position += 1
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', line)
        standalone_bold = re.fullmatch(r'\*\*([^*]+)\*\*', line)
        if standalone_bold:
            anchor = 'reply-section-' + str(len(headings) + 1)
            label = presentation.visible(standalone_bold.group(1))
            parts.append('<h3 id="' + anchor + '">' + text(label) + '</h3>')
            headings.append((anchor, label))
            pending_products.extend(matching_products(label))
            position += 1
            continue
        if heading:
            level = max(2, len(heading.group(1)))
            anchor = 'reply-section-' + str(len(headings) + 1)
            label = presentation.visible(heading.group(2))
            parts.append('<h' + str(level) + ' id="' + anchor + '">'
                         + formatted(label) + '</h' + str(level) + '>')
            if level == 2:
                headings.append((anchor, label))
            else:
                # Keep anchors unique without crowding the main navigation.
                headings.append((anchor, label, 'nested'))
            pending_products.extend(matching_products(label))
            position += 1
            continue
        if re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', line):
            parts.append('<hr>')
            position += 1
            continue
        if (position + 1 < len(lines) and '|' in line
                and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*', lines[position + 1])):
            headers = table_cells(line)
            table_parts = ['<div class="table-wrap"><table><thead><tr>' + ''.join(
                '<th scope="col">' + formatted(cell.strip()) + '</th>' for cell in headers)
                         + '</tr></thead><tbody>']
            table_text = [line]
            position += 2
            while position < len(lines) and '|' in lines[position] and lines[position].strip():
                cells = table_cells(lines[position])
                # Preserve malformed extra cells instead of silently dropping text.
                table_parts.append('<tr>' + ''.join('<td>' + formatted(cell.strip().replace('\\|', '|'))
                                                  + '</td>' for cell in cells) + '</tr>')
                table_text.append(lines[position])
                position += 1
            table_parts.append('</tbody></table></div>')
            block(''.join(table_parts), '\n'.join(table_text))
            continue
        listing = re.match(r'^(?:([-+*])|(\d+)\.)\s+(.+)$', line)
        if listing:
            ordered = bool(listing.group(2))
            tag = 'ol' if ordered else 'ul'
            start = (' start="' + text(listing.group(2)) + '"') if ordered else ''
            list_parts, list_text = ['<' + tag + start + '>'], []
            while position < len(lines):
                item = re.match(r'^(?:([-+*])|(\d+)\.)\s+(.+)$', lines[position].strip())
                if not item or bool(item.group(2)) != ordered:
                    break
                ordinal = (' value="' + text(item.group(2)) + '"') if ordered else ''
                list_parts.append('<li' + ordinal + '>' + formatted(item.group(3)) + '</li>')
                list_text.append(item.group(3))
                position += 1
            list_parts.append('</' + tag + '>')
            block(''.join(list_parts), '\n'.join(list_text))
            continue
        if line.startswith('>'):
            quotes = []
            while position < len(lines) and lines[position].strip().startswith('>'):
                quotes.append(lines[position].strip()[1:].lstrip())
                position += 1
            block('<blockquote><p>' + formatted('\n'.join(quotes)) + '</p></blockquote>', '\n'.join(quotes))
            continue
        paragraph = [lines[position].strip()]
        position += 1
        while position < len(lines) and lines[position].strip():
            next_line = lines[position].strip()
            if re.match(r'^(?:#{1,4}\s|[-+*]\s|\d+\.\s|>|-{3,}$)', next_line):
                break
            if position + 1 < len(lines) and '|' in next_line and re.match(r'^\s*\|?\s*:?-{3,}', lines[position + 1]):
                break
            paragraph.append(next_line)
            position += 1
        block('<p>' + formatted('\n'.join(paragraph)) + '</p>', '\n'.join(paragraph))
    return ''.join(parts), [item[:2] for item in headings if len(item) == 2]


def page_shell(title, body):
    css = (ROOT / 'assets' / 'results.css').read_text(encoding='utf-8')
    brand = ('<svg viewBox="0 0 44 44" aria-hidden="true"><rect x="1" y="1" width="42" height="42" '
             'rx="13" fill="#274b3f"/><path d="M11 13h4l3 16h15l3-12H17m4 17h1m8 0h1" '
             'fill="none" stroke="#f9f3e2" stroke-width="2.3" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>'
            + text(title) + '</title><style>' + css + '</style></head><body>'
            '<header class="masthead"><a class="brand" href="index.html">' + brand
            + '<span><b>CARTBench</b><small>Shopping advice, examined</small></span></a>'
            '<nav class="toplinks" aria-label="Page navigation"><a href="index.html">Explore outputs</a>'
            '<a href="#evaluation">Evaluation details ↗</a></nav></header>' + body
            + '</body></html>')


def rate_text(rate):
    value = rate['resolved_pass_rate']
    return '—' if value is None else format(value * 100, '.1f') + '%'


def catalog(latest, presentation=None):
    presentation = presentation or Presentation()
    products = []
    for product in product_records(latest):
        products.append('<div class="product"><span class="product-number">'
                        + presentation.text(product['doc_id']) + '</span><span><span class="product-title">'
                        + presentation.text(product['title'])
                        + '</span><span class="product-brand">' + presentation.text(product['brand']) + '</span></span></div>')
    if not products:
        return ''
    return ('<section class="aside-panel catalog" aria-label="Retrieved product context">'
            '<span class="section-label">Supplied context</span><h2>On the shortlist</h2>'
            '<p class="catalog-caption">Retrieved product records for this request.</p>'
            + ''.join(products[:4])
            + ('<details><summary>Show all ' + str(len(products)) + ' product records</summary>'
               + ''.join(products[4:]) + '</details>' if len(products) > 4 else '') + '</section>')


def score_cards(rates):
    cards = []
    for name in ('Core', 'Excellence', 'Safety'):
        rate = rates[name]
        percentage = 0 if rate['resolved_pass_rate'] is None else max(0, min(100, rate['resolved_pass_rate'] * 100))
        counts = text(rate['pass']) + ' pass · ' + text(rate['fail']) + ' fail'
        if rate['unresolved'] or rate['not_applicable']:
            counts += '<br>' + text(rate['unresolved']) + ' unresolved · ' + text(rate['not_applicable']) + ' not applicable'
        cards.append('<div class="score ' + name.lower() + '"><div class="score-head"><span class="score-tier">'
                     + name + '</span><span class="tier-dot" aria-hidden="true"></span></div><strong>'
                     + rate_text(rate) + '</strong><div class="counts">' + counts
                     + '</div><div class="meter" aria-hidden="true"><span style="width:'
                     + format(percentage, '.1f') + '%"></span></div></div>')
    return '<div class="score-grid">' + ''.join(cards) + '</div>'


def criterion_cards(case, judgment, presentation=None):
    presentation = presentation or Presentation(case)
    rubrics = {item['rubric_id']: item for item in case['rubrics']}
    groups = {'Core': [], 'Excellence': [], 'Safety': []}
    for score in judgment['scores']:
        rubric = rubrics[score['rubric_id']]
        status = score['status']
        status_class = status if status in {'pass', 'fail', 'unresolved', 'not_applicable'} else 'unresolved'
        card = ('<details class="criterion"><summary><span class="criterion-title">'
                + presentation.text(rubric['criterion']) + '<span class="criterion-id">' + text(score['rubric_id'])
                + '</span></span><span class="status ' + status_class + '">'
                + text(status.replace('_', ' ')) + '</span></summary><div class="criterion-body"><p>'
                + presentation.text(score['reason']) + '</p>')
        if score.get('response_quote'):
            card += ('<span class="evidence-label">Quoted from the reply</span><blockquote class="evidence">'
                     + presentation.text(score['response_quote']) + '</blockquote>')
        for span in score.get('input_evidence', []):
            label = span['source'] + (' · product ' + str(span['doc_id']) if span.get('doc_id') else '')
            card += ('<span class="evidence-label">Input evidence · ' + text(label)
                     + '</span><blockquote class="evidence">' + presentation.text(span['quote']) + '</blockquote>')
        card += ('<div class="conditions"><p><strong>Pass condition.</strong> '
                 + presentation.text(rubric['pass_condition']) + '</p><p><strong>Fail condition.</strong> '
                 + presentation.text(rubric['fail_condition']) + '</p></div></div></details>')
        groups[tier(rubric)].append(card)
    return ''.join('<section class="criteria-tier"><h3>' + name + '<span class="criteria-count">'
                   + str(len(cards)) + ' checks</span></h3>' + ''.join(cards) + '</section>'
                   for name, cards in groups.items() if cards)


def dialogue(case, presentation):
    """Show every user and intent-agent turn in its recorded order."""
    bubbles = []
    for index, message in enumerate(case['messages']):
        if message['role'] == 'system':
            continue
        value = decoded(message)
        content = value.get('query', value.get('content', '')) if isinstance(value, dict) else value
        timestamp = value.get('timestamp', '') if isinstance(value, dict) else ''
        try:
            shown_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%d %b %Y · %H:%M')
        except (ValueError, AttributeError):
            shown_time = timestamp
        is_current = index == len(case['messages']) - 1
        role = 'user' if message['role'] == 'user' else 'assistant'
        role_label = 'User' if role == 'user' else 'Intent agent'
        step = 'Current request' if is_current else ('Initial request' if not bubbles else 'Earlier turn')
        bubbles.append('<article class="chat-bubble ' + role + (' current' if is_current else '')
                       + '" data-role="' + role + '"><div class="chat-meta"><strong>' + role_label
                       + '</strong><span>' + step + '</span><time datetime="' + text(timestamp) + '">'
                       + presentation.text(shown_time) + '</time></div><p>'
                       + presentation.text(content).replace('\n', '<br>') + '</p></article>')
    return ('<section class="request"><div><h2>The conversation</h2><p class="chat-caption">'
            'How the request takes shape.</p></div><div class="chat-thread">' + ''.join(bubbles)
            + '</div></section>')


def result_page(case, result, json_link=True):
    """Render a complete saved evaluation without external resource dependencies."""
    case_id = case['query_id']
    title, tagline, deck, _, category = scenario(case_id)
    latest = decoded(case['messages'][-1])
    presentation = Presentation(case)
    reply, headings = render_reply(result['target_response'], presentation)
    contents = ('<section class="aside-panel"><span class="section-label">Your guide</span>'
                '<h2>In this reply</h2><ol class="contents">' + ''.join(
                    '<li><a href="#' + anchor + '">' + inline_reply(label) + '</a></li>'
                    for anchor, label in headings) + '</ol></section>') if headings else ''
    json_nav = '<a href="' + text(case_id) + '.json">Download JSON ↗</a>' if json_link else ''
    body = ('<main><section class="hero"><div><span class="eyebrow">' + text(category)
            + ' · ' + text(case_id) + '</span><h1>' + text(title) + '</h1><p class="deck">'
            + text(tagline) + ' ' + text(deck) + '</p><div class="metadata"><span class="pill">Agent <b>'
            + text(result.get('agent_model', 'Configured agent')) + '</b></span><span class="pill">Judge <b>'
            + text(result.get('judge_model', 'Configured judge')) + '</b></span></div></div>'
            '<div class="hero-art">' + illustration(case_id) + '</div></section>'
            + dialogue(case, presentation) + '<nav class="section-nav" aria-label="Result sections">'
            '<a href="#guide">01 &nbsp; Shopping guide</a><a href="#evaluation">02 &nbsp; Criterion review</a>'
            + json_nav + '</nav><div class="body-grid"><section class="guide" id="guide">'
            '<div class="reply-heading"><span class="section-label">The model’s recommendation</span>'
            '<h2>A closer look at the advice</h2><div class="model-label">Complete reply · '
            + text(result.get('agent_model', 'Configured agent')) + '</div></div><div class="reply">'
            + reply + '</div><details class="source-text"><summary>View the complete reply as plain text</summary>'
            '<pre class="reply-source">' + presentation.text(result['target_response']) + '</pre></details></section>'
            '<aside class="aside">' + contents + catalog(latest, presentation) + '</aside></div>'
            '<section class="evaluation" id="evaluation"><div class="evaluation-header"><div>'
            '<span class="section-label">Case-specific rubric</span><h2>How the advice holds up</h2></div>'
            '<p>Pass rates use pass / (pass + fail). Unresolved and not-applicable checks are counted separately.</p>'
            '</div>' + score_cards(result['rates']) + criterion_cards(case, result['judgment'], presentation)
            + '<details class="input-details"><summary>Input reference</summary><div class="hash">SHA-256 · '
            + text(case['input_sha256']) + '</div></details></section>'
            '<footer class="footer"><span>CARTBENCH / SHOPPING ADVICE, EXAMINED</span>'
            '<span>Case ' + text(case_id) + ' · ' + text(len(case['rubrics'])) + ' criteria</span></footer></main>')
    return page_shell('CARTBench · ' + title + ' · ' + case_id, body)


def result_index(rows):
    """Browse saved shopping replies with their actual tier pass rates."""
    entries = []
    for result in rows:
        case_id = result['query_id']
        title, tagline, _, _, category = scenario(case_id)
        rates = ''.join('<div>' + name + '<strong>' + rate_text(result['rates'][name]) + '</strong></div>'
                        for name in ('Core', 'Excellence', 'Safety'))
        entries.append('<article class="exhibit"><a href="' + text(case_id) + '.html" aria-label="Open '
                       + text(title) + '"><div class="exhibit-art">' + illustration(case_id)
                       + '</div><div class="exhibit-body"><span class="eyebrow">' + text(category)
                       + ' · ' + text(case_id) + '</span><h2>' + text(title) + '</h2><p>'
                       + text(tagline) + '</p><p class="model-label">Agent · '
                       + text(result.get('agent_model', 'Configured agent'))
                       + '</p><div class="exhibit-rates">' + rates
                       + '</div><span class="open-guide">Explore the reply <span aria-hidden="true">↗</span>'
                       '</span></div></a></article>')
    content = ('<div class="exhibit-grid">' + ''.join(entries) + '</div>') if entries else '<p class="empty-state">Run an evaluation to add its shopping guide here.</p>'
    body = ('<main><section class="index-hero"><span class="eyebrow">CARTBench output gallery</span>'
            '<h1>Shopping advice.<br>A closer look.</h1><p>Explore complete recommendations and the evidence behind their case-specific judgments.'
            ' Each guide brings the request, product context, and evaluation together.</p></section>'
            '<section id="evaluation" aria-label="Saved evaluations">' + content + '</section>'
            '<footer class="footer"><span>CARTBENCH / SHOPPING ADVICE, EXAMINED</span><span>'
            + str(len(rows)) + ' saved evaluations</span></footer></main>')
    return page_shell('CARTBench · Output gallery', body)


def save_result_pages(output_dir, case, result):
    with (output_dir / (case['query_id'] + '.html')).open('x', encoding='utf-8') as page:
        page.write(result_page(case, result))
    results = []
    for path in sorted(output_dir.glob('*.json')):
        item = load_json(path)
        if isinstance(item, dict) and {'query_id', 'rates', 'judgment'} <= item.keys():
            results.append(item)
    temporary = output_dir / 'index.html.tmp'
    temporary.write_text(result_index(results), encoding='utf-8')
    temporary.replace(output_dir / 'index.html')
