"""
PDF Turkish Character Repair Tool — CLI
========================================
Detects and patches broken Turkish character mappings in PDF font CMap tables.

PDFs affected by this bug display correctly on screen but produce garbled text
when copied: ğ becomes a control character, ı and İ become "1", ş/Ş become "_".

Repaired characters:
  ğ / Ğ  → mapped to U+001F/1E (control char) instead of U+011F/1E
  ı      → mapped to U+0031 ('1'), detected by adjacency to 'i' → U+0131
  İ      → mapped to U+0031 ('1'), detected as isolated duplicate → U+0130
  ş / Ş  → mapped to U+005F ('_'), detected by adjacency to s/S → U+015F/E

Usage:
    python pdf_tr_fix.py input.pdf
    python pdf_tr_fix.py input.pdf output.pdf
    python pdf_tr_fix.py input.pdf --analyze

Recommended setup:
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
"""

import os
import sys, re, argparse
from collections import defaultdict
from pathlib import Path
import pikepdf

SUPPORTED_LANGUAGES = ('tr', 'en')
MAX_CMAP_BYTES = 2 * 1024 * 1024
MAX_BFRANGE_SPAN = 65536
MAX_CMAP_ENTRIES = 131072

TEXTS = {
    'tr': {
        'parser_description': 'PDF Türkçe karakter onarıcı',
        'parser_epilog': 'Kurulum ve geliştirme için bir sanal ortam (venv) kullanılması tavsiye edilir.',
        'input_help': 'Girdi PDF',
        'output_help': 'Çıktı PDF',
        'analyze_help': 'Sadece analiz, değiştirme',
        'lang_help': 'Arayüz ve çıktı dili',
        'opening': 'Açılıyor: {path}',
        'detected_fixes': 'Tespit edilen düzeltmeler:',
        'analyze_only': '(--analyze: dosya değiştirilmedi)',
        'no_fix_found': 'Düzeltilecek hata bulunamadı.',
        'fixed_fonts': 'Düzeltilen font: {fonts}  |  Toplam patch: {patches}',
        'saved': 'Kaydedildi: {path}',
        'error_prefix': 'Hata: {message}',
        'output_suffix': '_onarildi',
        'cmap_stream_too_large': 'CMap akisi beklenenden buyuk',
        'cmap_invalid_range': 'Gecersiz CMap araligi',
        'cmap_range_limit': 'CMap araligi guvenlik limitini asiyor',
        'cmap_entries_limit': 'CMap esleme sayisi guvenlik limitini asiyor',
        'label_ctrl_1f': 'U+001F → ğ',
        'label_ctrl_1e': 'U+001E → Ğ',
        'label_one_dotless_i': "'1' → ı",
        'label_one_capital_i': "'1' → İ",
        'label_underscore_s': "'_' → ş",
        'label_underscore_capital_s': "'_' → Ş",
    },
    'en': {
        'parser_description': 'Repair broken Turkish character mappings in PDFs',
        'parser_epilog': 'Using a virtual environment (venv) is recommended for installation and development.',
        'input_help': 'Input PDF',
        'output_help': 'Output PDF',
        'analyze_help': 'Analyze only, do not modify the file',
        'lang_help': 'Language for CLI output',
        'opening': 'Opening: {path}',
        'detected_fixes': 'Detected fixes:',
        'analyze_only': '(--analyze: file was not modified)',
        'no_fix_found': 'No fixable issues were found.',
        'fixed_fonts': 'Patched fonts: {fonts}  |  Total patches: {patches}',
        'saved': 'Saved: {path}',
        'error_prefix': 'Error: {message}',
        'output_suffix': '_repaired',
        'cmap_stream_too_large': 'CMap stream is larger than the safety limit',
        'cmap_invalid_range': 'Invalid CMap range',
        'cmap_range_limit': 'CMap range exceeds the safety limit',
        'cmap_entries_limit': 'CMap mapping count exceeds the safety limit',
        'label_ctrl_1f': 'U+001F → ğ',
        'label_ctrl_1e': 'U+001E → Ğ',
        'label_one_dotless_i': "'1' → ı",
        'label_one_capital_i': "'1' → İ",
        'label_underscore_s': "'_' → ş",
        'label_underscore_capital_s': "'_' → Ş",
    },
}


class PDFSecurityError(ValueError):
    pass


def normalize_language(value):
    if not value:
        return None
    value = value.strip().lower()
    for lang in SUPPORTED_LANGUAGES:
        if value == lang or value.startswith(f'{lang}-') or value.startswith(f'{lang}_'):
            return lang
    return None


def detect_default_language():
    for env_key in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        lang = normalize_language(os.environ.get(env_key))
        if lang:
            return lang
    return 'tr'


def translate(lang, key, **kwargs):
    text = TEXTS[lang][key]
    return text.format(**kwargs) if kwargs else text


def open_pdf(source):
    return pikepdf.open(source, attempt_recovery=False, suppress_warnings=True)


def read_cmap_text(cmap_stream, lang):
    try:
        declared_length = int(cmap_stream.get('/Length', 0))
    except Exception:
        declared_length = 0

    if declared_length and declared_length > MAX_CMAP_BYTES:
        raise PDFSecurityError(translate(lang, 'cmap_stream_too_large'))

    cmap_bytes = bytes(cmap_stream.read_bytes())
    if len(cmap_bytes) > MAX_CMAP_BYTES:
        raise PDFSecurityError(translate(lang, 'cmap_stream_too_large'))

    return cmap_bytes.decode('latin-1')


def consume_mapping_budget(total_entries, span, lang):
    if span <= 0:
        raise PDFSecurityError(translate(lang, 'cmap_invalid_range'))
    if span > MAX_BFRANGE_SPAN:
        raise PDFSecurityError(translate(lang, 'cmap_range_limit'))

    total_entries += span
    if total_entries > MAX_CMAP_ENTRIES:
        raise PDFSecurityError(translate(lang, 'cmap_entries_limit'))
    return total_entries


def parse_mappings(cmap_text, lang):
    mappings = {}
    total_entries = 0
    for block in re.findall(r'beginbfrange(.*?)endbfrange', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)><([0-9A-Fa-f]+)><([0-9A-Fa-f]+)>', block):
            s, e, b = int(m.group(1),16), int(m.group(2),16), int(m.group(3),16)
            total_entries = consume_mapping_budget(total_entries, e - s + 1, lang)
            for i, c in enumerate(range(s, e+1)):
                mappings[c] = b + i
    for block in re.findall(r'beginbfchar(.*?)endbfchar', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            total_entries = consume_mapping_budget(total_entries, 1, lang)
            mappings[int(m.group(1),16)] = int(m.group(2),16)
    return mappings


def find_fixes(mappings):
    rev = defaultdict(list)
    for cid, uni in mappings.items():
        rev[uni].append(cid)
    fixes = {}

    # Kural 1: Kontrol karakteri → ğ/Ğ (kesin hata)
    for cid, uni in mappings.items():
        if uni == 0x001F: fixes[cid] = (uni, 0x011F)
        elif uni == 0x001E: fixes[cid] = (uni, 0x011E)

    # Kural 2: Birden fazla '1' CID'i → ı veya İ
    if len(rev[0x0031]) > 1:
        has_digit_one = any(
            any(mappings.get(c+d) in range(0x32, 0x3A) for d in range(-5,6) if d!=0)
            for c in rev[0x0031]
        )
        for cid in rev[0x0031]:
            near_i     = mappings.get(cid-1)==0x0069 or mappings.get(cid+1)==0x0069
            near_digit = any(mappings.get(cid+d) in range(0x32,0x3A) for d in range(-5,6) if d!=0)
            if near_i:
                fixes[cid] = (0x0031, 0x0131)        # ı
            elif not near_digit and has_digit_one:
                fixes[cid] = (0x0031, 0x0130)        # İ

    # Kural 3: '_' → ş/Ş (s veya S yakınında)
    for cid in rev[0x005F]:
        nearby = [mappings.get(cid+d) for d in range(-6,7) if d!=0 and mappings.get(cid+d)]
        if 0x0053 in nearby:   fixes[cid] = (0x005F, 0x015E)  # Ş
        elif 0x0073 in nearby: fixes[cid] = (0x005F, 0x015F)  # ş

    return fixes


def patch_cmap(cmap_text, fixes):
    count = 0
    for cid, (wrong, correct) in fixes.items():
        pat = re.compile(
            r'<(' + f'{cid:04x}' + r')><(' + f'{cid:04x}' + r')><(' + f'{wrong:04x}' + r')>',
            re.IGNORECASE
        )
        cmap_text, n = pat.subn(
            lambda m, c=f'{correct:04X}': f'<{m.group(1)}><{m.group(2)}><{c}>',
            cmap_text
        )
        count += n
    return cmap_text, count


def get_cli_labels(lang):
    return {
        ('[ctrl-1F]', 'ğ'): translate(lang, 'label_ctrl_1f'),
        ('[ctrl-1E]', 'Ğ'): translate(lang, 'label_ctrl_1e'),
        ('1', 'ı'): translate(lang, 'label_one_dotless_i'),
        ('1', 'İ'): translate(lang, 'label_one_capital_i'),
        ('_', 'ş'): translate(lang, 'label_underscore_s'),
        ('_', 'Ş'): translate(lang, 'label_underscore_capital_s'),
    }


def fix_pdf(input_path, output_path=None, analyze_only=False, lang='tr'):
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent / (input_path.stem + translate(lang, 'output_suffix') + input_path.suffix)

    print(translate(lang, 'opening', path=input_path))
    pdf = open_pdf(input_path)

    seen = set()
    total_patches = 0
    fonts_patched = 0
    summary = defaultdict(int)

    try:
        for page in pdf.pages:
            try:
                fd = page.get('/Resources', {}).get('/Font', {})
                for fname, fref in fd.items():
                    fobj = fref
                    try: objnum = fobj.objgen[0]
                    except Exception: continue
                    if objnum in seen or '/ToUnicode' not in fobj: continue
                    seen.add(objnum)

                    cmap_text  = read_cmap_text(fobj['/ToUnicode'], lang)
                    mappings   = parse_mappings(cmap_text, lang)
                    fixes      = find_fixes(mappings)
                    if not fixes: continue

                    for cid, (wrong, correct) in fixes.items():
                        try:
                            wc = chr(wrong) if wrong >= 0x20 else f'[ctrl-{wrong:02X}]'
                            summary[(wc, chr(correct))] += 1
                        except Exception:
                            continue

                    if not analyze_only:
                        new_cmap, count = patch_cmap(cmap_text, fixes)
                        if count > 0:
                            fobj['/ToUnicode'] = pdf.make_stream(new_cmap.encode('latin-1'))
                            fonts_patched += 1
                            total_patches += count
            except PDFSecurityError:
                raise
            except Exception:
                continue

        labels = get_cli_labels(lang)
        print(f"\n{translate(lang, 'detected_fixes')}")
        for (wc,cc), cnt in sorted(summary.items(), key=lambda x:-x[1]):
            print(f"  {labels.get((wc,cc), repr(wc)+' → '+repr(cc))}: {cnt} font")

        if analyze_only:
            print(f"\n{translate(lang, 'analyze_only')}")
            return None

        if total_patches == 0:
            print(f"\n{translate(lang, 'no_fix_found')}")
            return None

        print(f"\n{translate(lang, 'fixed_fonts', fonts=fonts_patched, patches=total_patches)}")
        pdf.save(output_path)
        print(translate(lang, 'saved', path=output_path))
        return output_path
    finally:
        pdf.close()


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument('--lang', choices=SUPPORTED_LANGUAGES)
    pre_args, _ = pre_parser.parse_known_args()
    default_lang = pre_args.lang or detect_default_language()

    parser = argparse.ArgumentParser(
        description=translate(default_lang, 'parser_description'),
        epilog=translate(default_lang, 'parser_epilog'),
    )
    parser.add_argument('input',  help=translate(default_lang, 'input_help'))
    parser.add_argument('output', nargs='?', help=translate(default_lang, 'output_help'))
    parser.add_argument('--analyze', action='store_true', help=translate(default_lang, 'analyze_help'))
    parser.add_argument('--lang', choices=SUPPORTED_LANGUAGES, default=default_lang, help=translate(default_lang, 'lang_help'))
    args = parser.parse_args()
    try:
        fix_pdf(args.input, args.output, args.analyze, args.lang)
    except (PDFSecurityError, pikepdf.PdfError, OSError, ValueError) as exc:
        print(translate(args.lang, 'error_prefix', message=exc), file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
