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
"""

import sys, re, argparse
from collections import defaultdict
from pathlib import Path
import pikepdf

MAX_CMAP_BYTES = 2 * 1024 * 1024
MAX_BFRANGE_SPAN = 65536
MAX_CMAP_ENTRIES = 131072


class PDFSecurityError(ValueError):
    pass


def open_pdf(source):
    return pikepdf.open(source, attempt_recovery=False, suppress_warnings=True)


def read_cmap_text(cmap_stream):
    try:
        declared_length = int(cmap_stream.get('/Length', 0))
    except Exception:
        declared_length = 0

    if declared_length and declared_length > MAX_CMAP_BYTES:
        raise PDFSecurityError('CMap akisi beklenenden buyuk')

    cmap_bytes = bytes(cmap_stream.read_bytes())
    if len(cmap_bytes) > MAX_CMAP_BYTES:
        raise PDFSecurityError('CMap akisi beklenenden buyuk')

    return cmap_bytes.decode('latin-1')


def consume_mapping_budget(total_entries, span):
    if span <= 0:
        raise PDFSecurityError('Gecersiz CMap araligi')
    if span > MAX_BFRANGE_SPAN:
        raise PDFSecurityError('CMap araligi guvenlik limitini asiyor')

    total_entries += span
    if total_entries > MAX_CMAP_ENTRIES:
        raise PDFSecurityError('CMap esleme sayisi guvenlik limitini asiyor')
    return total_entries


def parse_mappings(cmap_text):
    mappings = {}
    total_entries = 0
    for block in re.findall(r'beginbfrange(.*?)endbfrange', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)><([0-9A-Fa-f]+)><([0-9A-Fa-f]+)>', block):
            s, e, b = int(m.group(1),16), int(m.group(2),16), int(m.group(3),16)
            total_entries = consume_mapping_budget(total_entries, e - s + 1)
            for i, c in enumerate(range(s, e+1)):
                mappings[c] = b + i
    for block in re.findall(r'beginbfchar(.*?)endbfchar', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            total_entries = consume_mapping_budget(total_entries, 1)
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


def fix_pdf(input_path, output_path=None, analyze_only=False):
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent / (input_path.stem + '_onarildi' + input_path.suffix)

    print(f"Açılıyor: {input_path}")
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

                    cmap_text  = read_cmap_text(fobj['/ToUnicode'])
                    mappings   = parse_mappings(cmap_text)
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

        LABELS = {
            ('[ctrl-1F]','ğ'): 'U+001F → ğ',
            ('[ctrl-1E]','Ğ'): 'U+001E → Ğ',
            ('1','ı'):         "'1' → ı",
            ('1','İ'):         "'1' → İ",
            ('_','ş'):         "'_' → ş",
            ('_','Ş'):         "'_' → Ş",
        }
        print("\nTespit edilen düzeltmeler:")
        for (wc,cc), cnt in sorted(summary.items(), key=lambda x:-x[1]):
            print(f"  {LABELS.get((wc,cc), repr(wc)+' → '+repr(cc))}: {cnt} font")

        if analyze_only:
            print("\n(--analyze: dosya değiştirilmedi)")
            return None

        if total_patches == 0:
            print("\nDüzeltilecek hata bulunamadı.")
            return None

        print(f"\nDüzeltilen font: {fonts_patched}  |  Toplam patch: {total_patches}")
        pdf.save(output_path)
        print(f"Kaydedildi: {output_path}")
        return output_path
    finally:
        pdf.close()


def main():
    parser = argparse.ArgumentParser(description='PDF Türkçe karakter onarıcı')
    parser.add_argument('input',  help='Girdi PDF')
    parser.add_argument('output', nargs='?', help='Çıktı PDF')
    parser.add_argument('--analyze', action='store_true', help='Sadece analiz, değiştirme')
    args = parser.parse_args()
    try:
        fix_pdf(args.input, args.output, args.analyze)
    except (PDFSecurityError, pikepdf.PdfError, OSError, ValueError) as exc:
        print(f'Hata: {exc}', file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
