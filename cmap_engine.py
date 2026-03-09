import re
from collections import defaultdict

_BLOCK_TOKENS = (
    ('bfrange', 'beginbfrange', 'endbfrange'),
    ('bfchar', 'beginbfchar', 'endbfchar'),
)
_BFCHAR_ENTRY_RE = re.compile(
    r'<(?P<src>[0-9A-Fa-f]+)>\s*<(?P<dst>[0-9A-Fa-f]+)>',
    re.DOTALL,
)
_BFRANGE_ENTRY_RE = re.compile(
    r'<(?P<start>[0-9A-Fa-f]+)>\s*<(?P<end>[0-9A-Fa-f]+)>\s*'
    r'(?:<(?P<base>[0-9A-Fa-f]+)>|\[(?P<array_body>(?:\s*<[0-9A-Fa-f]+>\s*)+)\])',
    re.DOTALL,
)
_HEX_TOKEN_RE = re.compile(r'<([0-9A-Fa-f]+)>')


def parse_mappings(cmap_text, consume_mapping_budget):
    mappings = {}
    total_entries = 0

    for kind, _, _, body in _iter_cmap_blocks(cmap_text):

        if kind == 'bfrange':
            for entry in _BFRANGE_ENTRY_RE.finditer(body):
                start = int(entry.group('start'), 16)
                end = int(entry.group('end'), 16)
                span = end - start + 1
                total_entries = consume_mapping_budget(total_entries, span)

                if entry.group('base') is not None:
                    base = int(entry.group('base'), 16)
                    for offset, cid in enumerate(range(start, end + 1)):
                        mappings[cid] = base + offset
                    continue

                targets = [int(token.group(1), 16) for token in _HEX_TOKEN_RE.finditer(entry.group('array_body'))]
                for offset, target in enumerate(targets[:span]):
                    mappings[start + offset] = target
            continue

        for entry in _BFCHAR_ENTRY_RE.finditer(body):
            total_entries = consume_mapping_budget(total_entries, 1)
            mappings[int(entry.group('src'), 16)] = int(entry.group('dst'), 16)

    return mappings


def find_fixes(mappings):
    rev = defaultdict(list)
    for cid, uni in mappings.items():
        rev[uni].append(cid)

    fixes = {}

    for cid, uni in mappings.items():
        if uni == 0x001F:
            fixes[cid] = (uni, 0x011F)
        elif uni == 0x001E:
            fixes[cid] = (uni, 0x011E)

    if len(rev[0x0031]) > 1:
        has_digit_one = any(
            any(mappings.get(c + d) in range(0x32, 0x3A) for d in range(-5, 6) if d != 0)
            for c in rev[0x0031]
        )
        for cid in rev[0x0031]:
            near_i = mappings.get(cid - 1) == 0x0069 or mappings.get(cid + 1) == 0x0069
            near_digit = any(mappings.get(cid + d) in range(0x32, 0x3A) for d in range(-5, 6) if d != 0)
            if near_i:
                fixes[cid] = (0x0031, 0x0131)
            elif not near_digit and has_digit_one:
                fixes[cid] = (0x0031, 0x0130)

    for cid in rev[0x005F]:
        nearby = [mappings.get(cid + d) for d in range(-6, 7) if d != 0 and mappings.get(cid + d)]
        if 0x0053 in nearby:
            fixes[cid] = (0x005F, 0x015E)
        elif 0x0073 in nearby:
            fixes[cid] = (0x005F, 0x015F)

    return fixes


def patch_cmap(cmap_text, fixes):
    if not fixes:
        return cmap_text, 0

    parts = []
    total_patches = 0
    cursor = 0

    for kind, body_start, body_end, body in _iter_cmap_blocks(cmap_text):
        parts.append(cmap_text[cursor:body_start])

        if kind == 'bfrange':
            new_body, count = _patch_bfrange_block(body, fixes)
        else:
            new_body, count = _patch_bfchar_block(body, fixes)

        parts.append(new_body)
        total_patches += count
        cursor = body_end

    parts.append(cmap_text[cursor:])
    return ''.join(parts), total_patches


def collect_font_cmap_streams(pdf):
    import pikepdf

    streams = []
    seen_streams = set()
    seen_resources = set()
    seen_xobjects = set()

    def add_font(font_obj):
        if not isinstance(font_obj, pikepdf.Dictionary):
            return

        cmap_stream = font_obj.get('/ToUnicode')
        if not isinstance(cmap_stream, pikepdf.Stream):
            return

        stream_key = _object_key(cmap_stream)
        if stream_key in seen_streams:
            return

        seen_streams.add(stream_key)
        streams.append(cmap_stream)

    def walk_resources(resources, inherited_resources=None):
        effective_resources = resources if isinstance(resources, pikepdf.Dictionary) else inherited_resources
        if not isinstance(effective_resources, pikepdf.Dictionary):
            return

        resource_key = _object_key(effective_resources)
        if resource_key in seen_resources:
            return
        seen_resources.add(resource_key)

        fonts = effective_resources.get('/Font', {})
        if isinstance(fonts, pikepdf.Dictionary):
            for _, font_obj in fonts.items():
                add_font(font_obj)

        xobjects = effective_resources.get('/XObject', {})
        if not isinstance(xobjects, pikepdf.Dictionary):
            return

        for _, xobject in xobjects.items():
            if not isinstance(xobject, pikepdf.Stream):
                continue
            if xobject.get('/Subtype') != '/Form':
                continue

            xobject_key = _object_key(xobject)
            if xobject_key in seen_xobjects:
                continue
            seen_xobjects.add(xobject_key)

            walk_resources(xobject.get('/Resources', effective_resources), effective_resources)

    def walk_page_tree(node, inherited_resources=None):
        if not isinstance(node, pikepdf.Dictionary):
            return

        resources = node.get('/Resources', inherited_resources)
        if node.get('/Type') == '/Page':
            walk_resources(resources, inherited_resources)
            return

        for child in node.get('/Kids', []):
            walk_page_tree(child, resources)

    root_pages = pdf.Root.get('/Pages')
    if root_pages is not None:
        walk_page_tree(root_pages)

    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Dictionary) and obj.get('/Type') == '/Font':
            add_font(obj)

    return streams


def _iter_cmap_blocks(cmap_text):
    lower_text = cmap_text.lower()
    cursor = 0
    text_length = len(cmap_text)

    while cursor < text_length:
        next_kind = None
        next_begin = -1
        next_begin_token = None
        next_end_token = None

        for kind, begin_token, end_token in _BLOCK_TOKENS:
            begin_index = lower_text.find(begin_token, cursor)
            if begin_index == -1:
                continue
            if next_begin == -1 or begin_index < next_begin:
                next_kind = kind
                next_begin = begin_index
                next_begin_token = begin_token
                next_end_token = end_token

        if next_begin == -1:
            break

        body_start = next_begin + len(next_begin_token)
        body_end = lower_text.find(next_end_token, body_start)
        if body_end == -1:
            cursor = body_start
            continue

        yield next_kind, body_start, body_end, cmap_text[body_start:body_end]
        cursor = body_end + len(next_end_token)


def _patch_bfchar_block(block_text, fixes):
    parts = []
    count = 0
    cursor = 0

    for entry in _BFCHAR_ENTRY_RE.finditer(block_text):
        parts.append(block_text[cursor:entry.start()])

        src = int(entry.group('src'), 16)
        dst = int(entry.group('dst'), 16)
        fix = fixes.get(src)
        if not fix or dst != fix[0]:
            parts.append(entry.group(0))
            cursor = entry.end()
            continue

        count += 1
        parts.append(
            f'{_format_hex_like(src, entry.group("src"))} '
            f'{_format_hex_like(fix[1], entry.group("dst"))}'
        )
        cursor = entry.end()

    parts.append(block_text[cursor:])
    return ''.join(parts), count


def _patch_bfrange_block(block_text, fixes):
    parts = []
    count = 0
    cursor = 0

    for entry in _BFRANGE_ENTRY_RE.finditer(block_text):
        parts.append(block_text[cursor:entry.start()])

        start = int(entry.group('start'), 16)
        end = int(entry.group('end'), 16)
        span = end - start + 1
        if span <= 0:
            parts.append(entry.group(0))
            cursor = entry.end()
            continue

        start_token = _format_hex_like(start, entry.group('start'))
        end_token = _format_hex_like(end, entry.group('end'))

        base = entry.group('base')
        if base is not None:
            style_tokens = [base] * span
            targets = [int(base, 16) + offset for offset in range(span)]
            emit_sequential_if_possible = True
        else:
            style_tokens = [token.group(1) for token in _HEX_TOKEN_RE.finditer(entry.group('array_body'))]
            targets = [int(token, 16) for token in style_tokens]
            emit_sequential_if_possible = False

        changed = 0
        patchable_span = min(span, len(targets))
        for offset in range(patchable_span):
            cid = start + offset
            fix = fixes.get(cid)
            if fix and targets[offset] == fix[0]:
                targets[offset] = fix[1]
                changed += 1

        if changed == 0:
            parts.append(entry.group(0))
            cursor = entry.end()
            continue

        count += changed
        if emit_sequential_if_possible and _is_sequential(targets):
            parts.append(f'{start_token} {end_token} {_format_hex_like(targets[0], base)}')
            cursor = entry.end()
            continue

        if not style_tokens:
            style_tokens = [entry.group('start')]

        rendered_targets = [
            _format_hex_like(target, style_tokens[min(index, len(style_tokens) - 1)])
            for index, target in enumerate(targets)
        ]
        parts.append(f'{start_token} {end_token} [{" ".join(rendered_targets)}]')
        cursor = entry.end()

    parts.append(block_text[cursor:])
    return ''.join(parts), count


def _format_hex_like(value, original_hex):
    width = max(len(original_hex), len(f'{value:X}'))
    digits = f'{value:0{width}X}'
    if original_hex.islower():
        digits = digits.lower()
    return f'<{digits}>'


def _is_sequential(values):
    if not values:
        return False
    return all(values[index] == values[0] + index for index in range(1, len(values)))


def _object_key(obj):
    try:
        objnum, generation = obj.objgen
        if objnum:
            return ('indirect', int(objnum), int(generation))
    except Exception:
        pass
    return ('direct', id(obj))
