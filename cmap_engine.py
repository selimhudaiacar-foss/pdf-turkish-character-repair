import re
import unicodedata
from collections import defaultdict
from io import BytesIO

from fontTools import agl
from fontTools.encodings import MacRoman, StandardEncoding

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


def find_fixes(mappings, font_obj=None):
    fixes = {}

    if font_obj is not None:
        try:
            fixes.update(find_font_cmap_fixes(mappings, extract_font_cid_to_unicode(font_obj)))
        except Exception:
            pass

    for cid, fix in _find_heuristic_fixes(mappings).items():
        fixes.setdefault(cid, fix)

    return fixes


def find_font_cmap_fixes(mappings, cid_to_unicode):
    fixes = {}

    for cid, current_unicode in mappings.items():
        candidate_unicode = cid_to_unicode.get(cid)
        if candidate_unicode is None or candidate_unicode == current_unicode:
            continue
        if _should_replace_with_font_unicode(current_unicode, candidate_unicode):
            fixes[cid] = (current_unicode, candidate_unicode)

    return fixes


def build_cid_to_unicode_map(unicode_to_gid, cid_to_gid=None):
    gid_to_preferred_unicode = build_gid_to_unicode_map(unicode_to_gid)

    if cid_to_gid is None:
        return dict(gid_to_preferred_unicode)

    cid_to_unicode = {}
    items = cid_to_gid.items() if hasattr(cid_to_gid, 'items') else enumerate(cid_to_gid)
    for cid, gid in items:
        unicode_codepoint = gid_to_preferred_unicode.get(gid)
        if unicode_codepoint is not None:
            cid_to_unicode[int(cid)] = unicode_codepoint
    return cid_to_unicode


def build_gid_to_unicode_map(unicode_to_gid):
    gid_to_unicode_candidates = defaultdict(list)

    for unicode_codepoint, gid in unicode_to_gid.items():
        if not isinstance(gid, int) or gid <= 0:
            continue
        if not _is_valid_codepoint(unicode_codepoint):
            continue
        gid_to_unicode_candidates[gid].append(unicode_codepoint)

    gid_to_preferred_unicode = {
        gid: _select_preferred_unicode(codepoints)
        for gid, codepoints in gid_to_unicode_candidates.items()
        if codepoints
    }
    return gid_to_preferred_unicode


def build_simple_font_code_to_unicode_map(unicode_to_gid, code_to_unicode=None, code_to_glyph_name=None, glyph_name_to_gid=None):
    gid_to_preferred_unicode = build_gid_to_unicode_map(unicode_to_gid)
    code_to_unicode_map = {}
    codepoints = set()
    if code_to_unicode:
        codepoints.update(code_to_unicode)
    if code_to_glyph_name:
        codepoints.update(code_to_glyph_name)

    for code in codepoints:
        gid = None
        glyph_name = code_to_glyph_name.get(code) if code_to_glyph_name else None
        if glyph_name and glyph_name_to_gid:
            gid = glyph_name_to_gid.get(glyph_name)
        if gid is None and code_to_unicode:
            unicode_codepoint = code_to_unicode.get(code)
            if unicode_codepoint is not None:
                gid = unicode_to_gid.get(unicode_codepoint)
        if gid is None:
            continue
        preferred_unicode = gid_to_preferred_unicode.get(gid)
        if preferred_unicode is not None:
            code_to_unicode_map[int(code)] = preferred_unicode

    return code_to_unicode_map


def extract_font_cid_to_unicode(font_obj):
    subtype = str(font_obj.get('/Subtype', ''))

    if subtype == '/Type0' or subtype == '/CIDFontType2':
        cid_font = _resolve_cid_font(font_obj)
        if cid_font is None:
            return {}

        font_program = _extract_font_program(cid_font)
        if not font_program:
            return {}

        return build_cid_to_unicode_map(font_program['unicode_to_gid'], _read_cid_to_gid_map(cid_font))

    if subtype in {'/TrueType', '/Type1', '/MMType1'}:
        font_program = _extract_font_program(font_obj)
        if not font_program:
            return {}
        code_to_unicode, code_to_glyph_name = _read_simple_font_encoding(font_obj)
        if not code_to_unicode and not code_to_glyph_name:
            return {}
        return build_simple_font_code_to_unicode_map(
            font_program['unicode_to_gid'],
            code_to_unicode=code_to_unicode,
            code_to_glyph_name=code_to_glyph_name,
            glyph_name_to_gid=font_program['glyph_name_to_gid'],
        )

    return {}


def _find_heuristic_fixes(mappings):
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
    return [cmap_stream for _, cmap_stream in collect_font_cmap_records(pdf)]


def collect_font_cmap_records(pdf):
    import pikepdf

    records = []
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
        records.append((font_obj, cmap_stream))

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

    return records


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


def _resolve_cid_font(font_obj):
    subtype = str(font_obj.get('/Subtype', ''))

    if subtype == '/Type0':
        encoding = str(font_obj.get('/Encoding', ''))
        if encoding not in {'/Identity-H', '/Identity-V'}:
            return None

        descendants = font_obj.get('/DescendantFonts', [])
        if not descendants:
            return None

        descendant_font = descendants[0]
        if str(descendant_font.get('/Subtype', '')) != '/CIDFontType2':
            return None
        return descendant_font

    if subtype == '/CIDFontType2':
        return font_obj

    return None


def _find_embedded_font_stream(font_obj):
    descriptor = font_obj.get('/FontDescriptor')
    if descriptor is None:
        return None

    for key in ('/FontFile2', '/FontFile3', '/FontFile'):
        stream = descriptor.get(key)
        if stream is not None:
            return stream

    return None


def _extract_font_program(font_obj):
    font_stream = _find_embedded_font_stream(font_obj)
    if font_stream is None:
        return {}

    unicode_to_gid, glyph_name_to_gid = _extract_font_program_maps(font_stream)
    if not unicode_to_gid:
        return {}

    return {
        'unicode_to_gid': unicode_to_gid,
        'glyph_name_to_gid': glyph_name_to_gid,
    }


def _extract_font_program_maps(font_stream):
    try:
        from fontTools.ttLib import TTFont, TTLibError
    except ImportError:
        return {}, {}

    try:
        font = TTFont(BytesIO(bytes(font_stream.read_bytes())), lazy=True)
    except (TTLibError, OSError, ValueError):
        return {}, {}

    try:
        unicode_to_gid = {}
        cmap = font.getBestCmap() or {}
        _merge_unicode_to_gid_map(font, cmap, unicode_to_gid)

        if not unicode_to_gid and 'cmap' in font:
            for table in getattr(font['cmap'], 'tables', []):
                if not table.isUnicode():
                    continue
                _merge_unicode_to_gid_map(font, table.cmap, unicode_to_gid)

        glyph_name_to_gid = {}
        for glyph_name in font.getGlyphOrder():
            gid = _glyph_to_gid(font, glyph_name)
            if gid is not None:
                glyph_name_to_gid[glyph_name] = gid

        return unicode_to_gid, glyph_name_to_gid
    finally:
        font.close()


def _merge_unicode_to_gid_map(font, cmap, unicode_to_gid):
    for unicode_codepoint, glyph in cmap.items():
        gid = _glyph_to_gid(font, glyph)
        if gid is not None:
            unicode_to_gid.setdefault(int(unicode_codepoint), gid)


def _glyph_to_gid(font, glyph):
    if isinstance(glyph, int):
        return glyph

    try:
        return font.getGlyphID(glyph)
    except Exception:
        return None


def _read_simple_font_encoding(font_obj):
    code_to_unicode = {}
    code_to_glyph_name = {}

    base_encoding_name = _resolve_base_encoding_name(font_obj)
    if base_encoding_name:
        _apply_base_encoding(code_to_unicode, code_to_glyph_name, base_encoding_name)

    encoding = font_obj.get('/Encoding')
    if hasattr(encoding, 'get'):
        differences = encoding.get('/Differences')
        if differences is not None:
            _apply_encoding_differences(code_to_unicode, code_to_glyph_name, differences)

    return code_to_unicode, code_to_glyph_name


def _resolve_base_encoding_name(font_obj):
    encoding = font_obj.get('/Encoding')
    encoding_name = _normalize_pdf_name(encoding)
    if encoding_name:
        return encoding_name

    if hasattr(encoding, 'get'):
        base_name = _normalize_pdf_name(encoding.get('/BaseEncoding'))
        if base_name:
            return base_name

    subtype = str(font_obj.get('/Subtype', ''))
    if subtype in {'/Type1', '/MMType1'}:
        return '/StandardEncoding'
    if subtype == '/TrueType':
        return '/WinAnsiEncoding'
    return None


def _apply_base_encoding(code_to_unicode, code_to_glyph_name, base_encoding_name):
    if base_encoding_name == '/WinAnsiEncoding':
        for code in range(256):
            try:
                text = bytes([code]).decode('cp1252')
            except UnicodeDecodeError:
                continue
            if len(text) == 1:
                code_to_unicode[code] = ord(text)
        return

    if base_encoding_name == '/MacRomanEncoding':
        _apply_glyph_name_table(code_to_unicode, code_to_glyph_name, MacRoman.MacRoman)
        return

    if base_encoding_name == '/StandardEncoding':
        _apply_glyph_name_table(code_to_unicode, code_to_glyph_name, StandardEncoding.StandardEncoding)


def _apply_glyph_name_table(code_to_unicode, code_to_glyph_name, table):
    for code, glyph_name in enumerate(table):
        _assign_codepoint_mapping(code_to_unicode, code_to_glyph_name, code, glyph_name)


def _apply_encoding_differences(code_to_unicode, code_to_glyph_name, differences):
    current_code = None
    for item in differences:
        if isinstance(item, int):
            current_code = item
            continue
        if current_code is None:
            continue
        glyph_name = _normalize_pdf_name(item)
        if glyph_name:
            _assign_codepoint_mapping(code_to_unicode, code_to_glyph_name, current_code, glyph_name.lstrip('/'))
            current_code += 1


def _assign_codepoint_mapping(code_to_unicode, code_to_glyph_name, code, glyph_name):
    if not glyph_name or glyph_name == '.notdef':
        return

    bare_name = glyph_name.lstrip('/')
    code_to_glyph_name[int(code)] = bare_name

    try:
        text = agl.toUnicode(bare_name)
    except Exception:
        return

    if len(text) == 1:
        code_to_unicode[int(code)] = ord(text)


def _normalize_pdf_name(value):
    text = str(value or '')
    if not text or text == 'None':
        return None
    if text.startswith('/'):
        return text
    return f'/{text}'


def _read_cid_to_gid_map(font_obj):
    cid_to_gid = font_obj.get('/CIDToGIDMap')
    if cid_to_gid is None or str(cid_to_gid) == '/Identity':
        return None

    try:
        raw = bytes(cid_to_gid.read_bytes())
    except Exception:
        return {}

    if len(raw) % 2:
        raw = raw[:-1]

    return {
        cid: int.from_bytes(raw[offset:offset + 2], 'big')
        for cid, offset in enumerate(range(0, len(raw), 2))
        if int.from_bytes(raw[offset:offset + 2], 'big') > 0
    }


def _select_preferred_unicode(codepoints):
    return min(codepoints, key=_unicode_preference_key)


def _unicode_preference_key(codepoint):
    return (
        _unicode_semantic_rank(codepoint),
        1 if _is_problematic_unicode(codepoint) else 0,
        codepoint,
    )


def _unicode_semantic_rank(codepoint):
    if not _is_valid_codepoint(codepoint):
        return 6

    category = unicodedata.category(chr(codepoint))
    if category.startswith('L'):
        return 0
    if category.startswith('M'):
        return 1
    if category.startswith('N'):
        return 2
    if category.startswith('P'):
        return 3
    if category.startswith('S'):
        return 4
    if category.startswith('Z'):
        return 5
    return 6


def _should_replace_with_font_unicode(current_unicode, candidate_unicode):
    current_rank = _unicode_semantic_rank(current_unicode)
    candidate_rank = _unicode_semantic_rank(candidate_unicode)

    if candidate_rank > current_rank:
        return False
    if current_rank == candidate_rank:
        return _is_problematic_unicode(current_unicode) and not _is_problematic_unicode(candidate_unicode)
    return True


def _is_problematic_unicode(codepoint):
    if not _is_valid_codepoint(codepoint):
        return True

    category = unicodedata.category(chr(codepoint))
    if category.startswith('C'):
        return True

    if _is_private_or_presentation(codepoint):
        return True

    return unicodedata.normalize('NFKC', chr(codepoint)) != chr(codepoint)


def _is_valid_codepoint(codepoint):
    return isinstance(codepoint, int) and 0 <= codepoint <= 0x10FFFF


def _is_private_or_presentation(codepoint):
    return (
        0x2E80 <= codepoint <= 0x2EF3
        or 0x2F00 <= codepoint <= 0x2FD5
        or 0xE000 <= codepoint <= 0xF8FF
        or 0xFB00 <= codepoint <= 0xFB4F
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x2F800 <= codepoint <= 0x2FA1F
        or 0xF0000 <= codepoint <= 0xFFFFD
        or 0x100000 <= codepoint <= 0x10FFFD
        or codepoint == 0x00AD
    )
