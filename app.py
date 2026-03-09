"""
PDF Turkish Character Repair Tool — Web UI
===========================================
Detects and repairs broken Turkish characters in PDFs that display correctly
but produce garbled text when copied (ğ→control, ı→1, İ→1, ş→_, Ş→_).

Works by patching the font ToUnicode CMap tables in-place.
No text extraction, no PDF regeneration — zero data loss.

Recommended setup:
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

Usage:
    python app.py
    → http://127.0.0.1:5000

See pdf_tr_fix.py for the CLI version.
"""
import os
import re
import secrets
import tempfile
from collections import defaultdict
from pathlib import Path

import pikepdf
from flask import Flask, g, jsonify, render_template_string, request, send_file
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['MAX_FORM_MEMORY_SIZE'] = 1024 * 1024

VERSION = 'v2.4.1'
SUPPORTED_LANGUAGES = ('tr', 'en')
PDF_HEADER_SCAN_BYTES = 1024
MAX_CMAP_BYTES = 2 * 1024 * 1024
MAX_BFRANGE_SPAN = 65536
MAX_CMAP_ENTRIES = 131072
OUTPUT_BUFFER_LIMIT = 2 * 1024 * 1024

TEXTS = {
    'tr': {
        'page_title': 'PDF Onarıcı',
        'app_name': 'PDF Onarıcı',
        'status_ready': 'Hazır',
        'engine_name': 'CMap Patch Engine',
        'language_label': 'Dil',
        'contrast_label': 'Kontrast',
        'contrast_default': 'Normal',
        'contrast_high': 'Yuksek',
        'panel_file': 'Dosya',
        'drop_title': "PDF'i bırakın veya tıklayın",
        'drop_hint': 'Maks. {size} MB · .pdf',
        'file_thumb': 'PDF',
        'remove_file': 'Kaldır',
        'panel_repaired_characters': 'Onarılan Karakterler',
        'btn_analyze_fix': 'Analiz Et & Onar',
        'step_upload': 'Dosya yükle',
        'step_analyze': 'Analiz',
        'step_repair': 'Onarım',
        'step_download': 'İndir',
        'terminal_title': 'cmap-patch.log',
        'engine_ready_waiting': 'Motor hazır. Dosya bekleniyor…',
        'processing': 'İşleniyor…',
        'stat_pages': 'Sayfa',
        'stat_fonts': 'Font',
        'stat_issue_types': 'Hata türü',
        'stat_patches': 'Patch',
        'download': 'İndir',
        'footer_text': 'Font ToUnicode CMap · In-place patch · Sıfır veri kaybı',
        'select_pdf_error': 'Lütfen bir .pdf dosyası seçin',
        'file_uploaded': 'Dosya yüklendi: {name} ({size})',
        'no_issues': 'Türkçe karakter hatası bulunamadı',
        'analysis_started': 'Analiz başladı…',
        'scanning_cmaps': 'CMap tabloları taranıyor…',
        'server_error': 'Sunucu hatası: {message}',
        'analysis_completed': 'Analiz tamamlandı: {font_count} font, {fix_count} hata türü',
        'clean_pdf': 'Bu PDF temiz görünüyor.',
        'affected_fonts': '{mapping} — {count} font etkilenmiş',
        'patching_fonts': 'Font tabloları yamalanıyor…',
        'repair_error': 'Onarım hatası: {message}',
        'repair_failed': 'Onarım başarısız.',
        'repair_completed': 'Onarım tamamlandı — {elapsed}s sürdü',
        'output_ready': 'Çıktı: {name} ({size})',
        'download_note': '{elapsed}s — {size}',
        'result_count': '{count} font',
        'output_suffix': '_onarildi',
        'upload_missing': 'PDF bulunamadı',
        'upload_pdf_only': 'Sadece .pdf dosyalari kabul edilir',
        'upload_invalid_pdf': 'Gecerli bir PDF yukleyin',
        'cmap_stream_too_large': 'CMap akisi beklenenden buyuk',
        'cmap_invalid_range': 'Gecersiz CMap araligi',
        'cmap_range_limit': 'CMap araligi guvenlik limitini asiyor',
        'cmap_entries_limit': 'CMap esleme sayisi guvenlik limitini asiyor',
        'pdf_security_limit': 'PDF guvenlik sinirlarini asiyor',
        'request_too_large': 'PDF boyutu {mb} MB sinirini asiyor',
        'bad_request': 'Istek gecersiz veya eksik',
        'unexpected_error': 'Islem sirasinda beklenmeyen bir hata olustu',
        'desc_control_char': 'Görünmez kontrol karakteri',
        'desc_digit_one': 'Rakam "1" olarak kodlanmış',
        'desc_underscore': 'Alt çizgi "_" olarak kodlanmış',
    },
    'en': {
        'page_title': 'PDF Repair',
        'app_name': 'PDF Repair',
        'status_ready': 'Ready',
        'engine_name': 'CMap Patch Engine',
        'language_label': 'Language',
        'contrast_label': 'Contrast',
        'contrast_default': 'Default',
        'contrast_high': 'High',
        'panel_file': 'File',
        'drop_title': 'Drop a PDF here or click to browse',
        'drop_hint': 'Max {size} MB · .pdf',
        'file_thumb': 'PDF',
        'remove_file': 'Remove',
        'panel_repaired_characters': 'Repaired Characters',
        'btn_analyze_fix': 'Analyze & Repair',
        'step_upload': 'Upload file',
        'step_analyze': 'Analyze',
        'step_repair': 'Repair',
        'step_download': 'Download',
        'terminal_title': 'cmap-patch.log',
        'engine_ready_waiting': 'Engine ready. Waiting for a file…',
        'processing': 'Processing…',
        'stat_pages': 'Pages',
        'stat_fonts': 'Fonts',
        'stat_issue_types': 'Issue types',
        'stat_patches': 'Patches',
        'download': 'Download',
        'footer_text': 'Font ToUnicode CMap · In-place patch · Zero data loss',
        'select_pdf_error': 'Please select a .pdf file',
        'file_uploaded': 'File loaded: {name} ({size})',
        'no_issues': 'No Turkish character issues were detected',
        'analysis_started': 'Analysis started…',
        'scanning_cmaps': 'Scanning CMap tables…',
        'server_error': 'Server error: {message}',
        'analysis_completed': 'Analysis complete: {font_count} fonts, {fix_count} issue types',
        'clean_pdf': 'This PDF looks clean.',
        'affected_fonts': '{mapping} — {count} {font_word} affected',
        'patching_fonts': 'Patching font tables…',
        'repair_error': 'Repair error: {message}',
        'repair_failed': 'Repair failed.',
        'repair_completed': 'Repair complete — took {elapsed}s',
        'output_ready': 'Output: {name} ({size})',
        'download_note': '{elapsed}s — {size}',
        'result_count': '{count} {font_word}',
        'output_suffix': '_repaired',
        'upload_missing': 'PDF file not found',
        'upload_pdf_only': 'Only .pdf files are accepted',
        'upload_invalid_pdf': 'Please upload a valid PDF',
        'cmap_stream_too_large': 'CMap stream is larger than the safety limit',
        'cmap_invalid_range': 'Invalid CMap range',
        'cmap_range_limit': 'CMap range exceeds the safety limit',
        'cmap_entries_limit': 'CMap mapping count exceeds the safety limit',
        'pdf_security_limit': 'PDF exceeds processing safety limits',
        'request_too_large': 'PDF size exceeds the {mb} MB limit',
        'bad_request': 'Request is invalid or incomplete',
        'unexpected_error': 'An unexpected error occurred during processing',
        'desc_control_char': 'Invisible control character',
        'desc_digit_one': 'Encoded as the digit "1"',
        'desc_underscore': 'Encoded as an underscore "_"',
    },
}

LANGUAGE_OPTIONS = (
    ('tr', 'TR'),
    ('en', 'EN'),
)


class UploadValidationError(ValueError):
    pass


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


def get_request_language():
    lang = normalize_language(request.args.get('lang'))
    if lang:
        return lang
    lang = normalize_language(request.headers.get('X-App-Lang'))
    if lang:
        return lang
    try:
        lang = normalize_language(request.form.get('lang'))
        if lang:
            return lang
    except (BadRequest, RequestEntityTooLarge):
        pass
    return request.accept_languages.best_match(SUPPORTED_LANGUAGES) or 'tr'


def get_texts(lang):
    return TEXTS[lang]


def translate(key, lang, **kwargs):
    text = get_texts(lang)[key]
    return text.format(**kwargs) if kwargs else text


def get_fix_labels(lang):
    return {
        (0x001F, 0x011F): ('ğ', 'U+001F → U+011F', translate('desc_control_char', lang)),
        (0x001E, 0x011E): ('Ğ', 'U+001E → U+011E', translate('desc_control_char', lang)),
        (0x0031, 0x0131): ('ı', 'U+0031 → U+0131', translate('desc_digit_one', lang)),
        (0x0031, 0x0130): ('İ', 'U+0031 → U+0130', translate('desc_digit_one', lang)),
        (0x005F, 0x015F): ('ş', 'U+005F → U+015F', translate('desc_underscore', lang)),
        (0x005F, 0x015E): ('Ş', 'U+005F → U+015E', translate('desc_underscore', lang)),
    }


def validate_pdf_upload(upload, lang):
    if upload is None or not upload.filename:
        raise UploadValidationError(translate('upload_missing', lang))

    if not upload.filename.lower().endswith('.pdf'):
        raise UploadValidationError(translate('upload_pdf_only', lang))

    header = upload.stream.read(PDF_HEADER_SCAN_BYTES)
    upload.stream.seek(0)
    if b'%PDF-' not in header:
        raise UploadValidationError(translate('upload_invalid_pdf', lang))

    return upload


def open_pdf(source):
    if hasattr(source, 'seek'):
        source.seek(0)
    return pikepdf.open(source, attempt_recovery=False, suppress_warnings=True)


def read_cmap_text(cmap_stream, lang):
    try:
        declared_length = int(cmap_stream.get('/Length', 0))
    except Exception:
        declared_length = 0

    if declared_length and declared_length > MAX_CMAP_BYTES:
        raise PDFSecurityError(translate('cmap_stream_too_large', lang))

    cmap_bytes = bytes(cmap_stream.read_bytes())
    if len(cmap_bytes) > MAX_CMAP_BYTES:
        raise PDFSecurityError(translate('cmap_stream_too_large', lang))

    return cmap_bytes.decode('latin-1')


def consume_mapping_budget(total_entries, span, lang):
    if span <= 0:
        raise PDFSecurityError(translate('cmap_invalid_range', lang))
    if span > MAX_BFRANGE_SPAN:
        raise PDFSecurityError(translate('cmap_range_limit', lang))

    total_entries += span
    if total_entries > MAX_CMAP_ENTRIES:
        raise PDFSecurityError(translate('cmap_entries_limit', lang))
    return total_entries


def safe_download_name(filename, lang):
    stem = Path(secure_filename(filename or 'document.pdf')).stem or 'document'
    return f"{stem}{translate('output_suffix', lang)}.pdf"


def json_error(message, status):
    return jsonify({'error': message}), status


def max_upload_limit_mb():
    return max(1, app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024))


def handle_api_exception(exc, lang=None):
    lang = lang or get_request_language()
    if isinstance(exc, UploadValidationError):
        return json_error(str(exc), 400)
    if isinstance(exc, PDFSecurityError):
        app.logger.warning('Blocked suspicious PDF: %s', exc)
        return json_error(translate('pdf_security_limit', lang), 400)
    if isinstance(exc, pikepdf.PdfError):
        return json_error(translate('upload_invalid_pdf', lang), 400)
    if isinstance(exc, RequestEntityTooLarge):
        return json_error(translate('request_too_large', lang, mb=max_upload_limit_mb()), 413)
    if isinstance(exc, BadRequest):
        return json_error(translate('bad_request', lang), 400)

    app.logger.exception('Unexpected PDF processing error')
    return json_error(translate('unexpected_error', lang), 500)


@app.before_request
def set_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)
    g.lang = get_request_language()
    g.texts = get_texts(g.lang)


@app.after_request
def add_security_headers(response):
    script_src = "script-src 'self'"
    nonce = getattr(g, 'csp_nonce', None)
    if nonce:
        script_src += f" 'nonce-{nonce}'"
    else:
        script_src += " 'unsafe-inline'"

    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        f"{script_src}; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response

def parse_mappings(cmap_text, lang):
    mappings = {}
    total_entries = 0
    for block in re.findall(r'beginbfrange(.*?)endbfrange', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)><([0-9A-Fa-f]+)><([0-9A-Fa-f]+)>', block):
            s,e,b = int(m.group(1),16),int(m.group(2),16),int(m.group(3),16)
            total_entries = consume_mapping_budget(total_entries, e - s + 1, lang)
            for i,c in enumerate(range(s,e+1)): mappings[c]=b+i
    for block in re.findall(r'beginbfchar(.*?)endbfchar', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            total_entries = consume_mapping_budget(total_entries, 1, lang)
            mappings[int(m.group(1),16)]=int(m.group(2),16)
    return mappings

def find_fixes(mappings):
    rev = defaultdict(list)
    for cid,uni in mappings.items(): rev[uni].append(cid)
    fixes = {}
    for cid,uni in mappings.items():
        if uni==0x001F: fixes[cid]=(uni,0x011F)
        elif uni==0x001E: fixes[cid]=(uni,0x011E)
    if len(rev[0x0031])>1:
        has_digit_one=any(any(mappings.get(c+d) in range(0x32,0x3A) for d in range(-5,6) if d!=0) for c in rev[0x0031])
        for cid in rev[0x0031]:
            near_i=mappings.get(cid-1)==0x0069 or mappings.get(cid+1)==0x0069
            near_digit=any(mappings.get(cid+d) in range(0x32,0x3A) for d in range(-5,6) if d!=0)
            if near_i: fixes[cid]=(0x0031,0x0131)
            elif not near_digit and has_digit_one: fixes[cid]=(0x0031,0x0130)
    for cid in rev[0x005F]:
        nearby=[mappings.get(cid+d) for d in range(-6,7) if d!=0 and mappings.get(cid+d)]
        if 0x0053 in nearby: fixes[cid]=(0x005F,0x015E)
        elif 0x0073 in nearby: fixes[cid]=(0x005F,0x015F)
    return fixes

def patch_cmap(cmap_text,fixes):
    count=0
    for cid,(wrong,correct) in fixes.items():
        pat=re.compile(r'<('+f'{cid:04x}'+r')><('+f'{cid:04x}'+r')><('+f'{wrong:04x}'+r')>',re.IGNORECASE)
        cmap_text,n=pat.subn(lambda m,c=f'{correct:04X}':f'<{m.group(1)}><{m.group(2)}><{c}>',cmap_text)
        count+=n
    return cmap_text,count

def analyze_pdf(pdf_source, lang):
    pdf = open_pdf(pdf_source)
    seen=set(); summary=defaultdict(int); page_count=len(pdf.pages)
    labels = get_fix_labels(lang)
    try:
        for page in pdf.pages:
            try:
                fd=page.get('/Resources',{}).get('/Font',{})
                for _,fref in fd.items():
                    fobj=fref
                    try: objnum=fobj.objgen[0]
                    except Exception: continue
                    if objnum in seen or '/ToUnicode' not in fobj: continue
                    seen.add(objnum)
                    cmap=read_cmap_text(fobj['/ToUnicode'], lang)
                    for _,(wrong,correct) in find_fixes(parse_mappings(cmap, lang)).items():
                        summary[(wrong,correct)]+=1
            except PDFSecurityError:
                raise
            except Exception:
                continue
        results=[]
        for (wrong,correct),cnt in sorted(summary.items(),key=lambda x:-x[1]):
            char,mapping,desc=labels.get((wrong,correct),(f'?',f'U+{wrong:04X}→U+{correct:04X}',''))
            results.append({'char':char,'mapping':mapping,'desc':desc,'count':cnt})
        return results, len(seen), page_count
    finally:
        pdf.close()

def fix_pdf_stream(pdf_source, lang):
    pdf = open_pdf(pdf_source); seen=set(); total=0; fonts_fixed=0
    try:
        for page in pdf.pages:
            try:
                fd=page.get('/Resources',{}).get('/Font',{})
                for _,fref in fd.items():
                    fobj=fref
                    try: objnum=fobj.objgen[0]
                    except Exception: continue
                    if objnum in seen or '/ToUnicode' not in fobj: continue
                    seen.add(objnum)
                    cmap_text=read_cmap_text(fobj['/ToUnicode'], lang)
                    fixes=find_fixes(parse_mappings(cmap_text, lang))
                    if not fixes: continue
                    new_cmap,count=patch_cmap(cmap_text,fixes)
                    if count>0:
                        fobj['/ToUnicode']=pdf.make_stream(new_cmap.encode('latin-1'))
                        total+=count; fonts_fixed+=1
            except PDFSecurityError:
                raise
            except Exception:
                continue
        out = tempfile.SpooledTemporaryFile(max_size=OUTPUT_BUFFER_LIMIT, mode='w+b')
        pdf.save(out)
        out.seek(0)
        return out, total, fonts_fixed
    finally:
        pdf.close()

HTML = r"""<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ t.page_title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist+Mono:wght@300;400;500&family=Geist:wght@300;400;500;600&display=swap" rel="stylesheet">
<script nonce="{{ csp_nonce }}">
(() => {
  const key = 'pdf-repair-contrast';
  try {
    const stored = window.localStorage.getItem(key);
    const prefersHigh = window.matchMedia && window.matchMedia('(prefers-contrast: more)').matches;
    const mode = stored === 'high' || stored === 'default' ? stored : (prefersHigh ? 'high' : 'default');
    if (mode === 'high') document.documentElement.dataset.contrast = 'high';
  } catch (_) {}
})();
</script>
<style>
/* ── Reset & Tokens ─────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #04050a;
  --ink:       #fcf8ef;
  --ink-dim:   #c8c1b0;
  --ink-faint: #8f887a;
  --card:      #11131a;
  --card2:     #1b1e28;
  --line:      rgba(252,248,239,0.14);
  --line2:     rgba(252,248,239,0.24);
  --gold:      #f1c36d;
  --gold-dim:  rgba(241,195,109,0.22);
  --gold-glow: rgba(241,195,109,0.12);
  --green:     #7ce0aa;
  --green-dim: rgba(124,224,170,0.18);
  --red:       #ff8e8e;
  --focus-ring:#f1c36d;
  --mono: 'Geist Mono', monospace;
  --serif: 'Instrument Serif', Georgia, serif;
  --sans: 'Geist', sans-serif;
  --r: 10px;
  --page-gutter: clamp(1rem, 2.5vw, 2rem);
  --panel-pad: clamp(1rem, 3vw, 2rem);
  --safe-left: env(safe-area-inset-left, 0px);
  --safe-right: env(safe-area-inset-right, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
}

:root[data-contrast='high'] {
  --bg:        #000000;
  --ink:       #ffffff;
  --ink-dim:   #f2f2f2;
  --ink-faint: #b9b9b9;
  --card:      #05070d;
  --card2:     #0f131b;
  --line:      rgba(255,255,255,0.32);
  --line2:     rgba(255,255,255,0.52);
  --gold:      #ffd866;
  --gold-dim:  rgba(255,216,102,0.24);
  --gold-glow: rgba(255,216,102,0.18);
  --green:     #8effc2;
  --green-dim: rgba(142,255,194,0.22);
  --red:       #ffb0b0;
  --focus-ring:#ffffff;
}

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
  overflow-x: hidden;
}

/* ── Grid noise texture overlay ─────────────────── */
body::after {
  content: '';
  position: fixed; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 9999;
  opacity: .6;
}

:root[data-contrast='high'] body::after {
  opacity: .28;
}

/* ── Layout ─────────────────────────────────────── */
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  grid-template-rows: auto 1fr auto;
}

/* ── Topbar ─────────────────────────────────────── */
.topbar {
  grid-column: 1 / -1;
  border-bottom: 1px solid var(--line);
  padding: .85rem calc(var(--page-gutter) + var(--safe-right)) .85rem calc(var(--page-gutter) + var(--safe-left));
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem 1.25rem;
  flex-wrap: wrap;
}

.logo {
  display: flex;
  align-items: baseline;
  gap: .6rem;
  flex-wrap: wrap;
  row-gap: .35rem;
}

.logo-serif {
  font-family: var(--serif);
  font-size: 1.25rem;
  color: var(--ink);
  letter-spacing: -.01em;
}

.logo-tag {
  font-family: var(--mono);
  font-size: .65rem;
  color: var(--gold);
  background: var(--gold-dim);
  padding: .15rem .5rem;
  border-radius: 3px;
  letter-spacing: .06em;
}

.topbar-right {
  font-family: var(--mono);
  font-size: .7rem;
  color: var(--ink-dim);
  display: flex;
  align-items: center;
  gap: .75rem 1.25rem;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.lang-switch {
  display: flex;
  align-items: center;
  gap: .45rem;
  flex-wrap: wrap;
}

.contrast-switch {
  display: flex;
  align-items: center;
  gap: .45rem;
  flex-wrap: wrap;
}

.lang-label {
  color: var(--ink-faint);
  white-space: nowrap;
}

.contrast-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--card);
}

.contrast-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--ink-dim);
  border-radius: 999px;
  padding: .24rem .58rem;
  font-family: var(--mono);
  font-size: .68rem;
  line-height: 1;
  cursor: pointer;
  transition: color .15s, background .15s, box-shadow .15s;
}

.contrast-btn:hover {
  color: var(--ink);
  background: rgba(255,255,255,0.06);
}

.contrast-btn.active {
  color: var(--ink);
  background: var(--gold-dim);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
}

.lang-link {
  color: var(--ink-dim);
  text-decoration: none;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: .2rem .45rem;
  transition: border-color .15s, color .15s, background .15s;
}

.lang-link:hover,
.lang-link.active {
  color: var(--gold);
  border-color: rgba(241,195,109,0.55);
  background: rgba(241,195,109,0.14);
}

:where(.lang-link, .contrast-btn, .btn-primary, .btn-clear, .dl-btn, .drop-zone):focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.status-dot {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  white-space: nowrap;
}

.status-dot::before {
  content: '';
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
  animation: breathe 2.5s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: .4; }
}

/* ── Left panel ─────────────────────────────────── */
.left-panel {
  border-right: 1px solid var(--line);
  padding: var(--panel-pad);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  min-width: 0;
}

.panel-label {
  font-family: var(--mono);
  font-size: .65rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--ink-dim);
  margin-bottom: .75rem;
}

/* Drop zone */
.drop-zone {
  position: relative;
  border: 1px solid var(--line2);
  border-radius: var(--r);
  padding: clamp(1.35rem, 5vw, 2.5rem) clamp(1rem, 3vw, 1.5rem);
  text-align: center;
  cursor: pointer;
  transition: border-color .2s, background .2s;
  background: var(--card);
  overflow: hidden;
}

.drop-zone::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--gold), transparent);
  opacity: 0;
  transition: opacity .3s;
}

.drop-zone:hover::before,
.drop-zone.over::before { opacity: .6; }

.drop-zone:hover,
.drop-zone.over {
  border-color: rgba(241,195,109,0.45);
  background: rgba(241,195,109,0.08);
}

.drop-zone input[type=file] {
  position: absolute; inset: 0;
  opacity: 0; cursor: pointer;
  width: 100%; height: 100%;
}

.drop-glyph {
  font-family: var(--serif);
  font-style: italic;
  font-size: 3rem;
  color: var(--gold);
  opacity: .4;
  display: block;
  margin-bottom: .75rem;
  line-height: 1;
  transition: opacity .2s;
}

.drop-zone:hover .drop-glyph { opacity: .7; }

.drop-title {
  font-size: .9rem;
  font-weight: 500;
  color: var(--ink);
  margin-bottom: .3rem;
  overflow-wrap: anywhere;
}

.drop-hint {
  font-family: var(--mono);
  font-size: .68rem;
  color: var(--ink-dim);
  overflow-wrap: anywhere;
}

/* File card */
.file-card {
  display: none;
  background: var(--card);
  border: 1px solid var(--line2);
  border-radius: var(--r);
  padding: 1rem 1.25rem;
  animation: fadeIn .25s ease;
}

.file-card-top {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: .85rem;
}

.file-thumb {
  width: 36px; height: 36px; flex-shrink: 0;
  background: var(--gold-dim);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono);
  font-size: .6rem;
  font-weight: 500;
  color: var(--gold);
  letter-spacing: .05em;
}

.file-meta { flex: 1; min-width: 0; }
.file-name-text {
  font-size: .85rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: .2rem;
}
.file-size-text {
  font-family: var(--mono);
  font-size: .68rem;
  color: var(--ink-dim);
}

.btn-clear {
  background: none; border: none; cursor: pointer;
  color: var(--ink-dim); padding: .2rem;
  border-radius: 5px; transition: color .15s;
  flex-shrink: 0;
  align-self: flex-start;
}
.btn-clear:hover { color: var(--red); }

/* Primary button */
.btn-primary {
  display: block; width: 100%;
  padding: .75rem 1rem;
  background: var(--gold);
  color: #07070d;
  border: none; border-radius: var(--r);
  font-family: var(--sans);
  font-size: .9rem;
  font-weight: 600;
  letter-spacing: -.01em;
  cursor: pointer;
  transition: all .2s;
  position: relative;
  overflow: hidden;
}

.btn-primary::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, rgba(255,255,255,.15), transparent);
}

.btn-primary:hover:not(:disabled) {
  background: #e0b560;
  box-shadow: 0 4px 20px rgba(212,168,83,0.3);
  transform: translateY(-1px);
}

.btn-primary:disabled {
  background: var(--ink-faint);
  color: var(--ink-dim);
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* Char grid */
.char-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: .4rem;
}

.char-cell {
  aspect-ratio: 1;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--serif);
  font-size: 1.1rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--ink-dim);
  transition: all .2s;
  cursor: default;
  position: relative;
  overflow: hidden;
}

.char-cell.active {
  color: var(--gold);
  border-color: rgba(241,195,109,0.48);
  background: var(--gold-dim);
}

.char-cell.active::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: var(--gold);
  opacity: .4;
}

/* ── Right panel ────────────────────────────────── */
.right-panel {
  padding: var(--panel-pad);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  overflow-y: auto;
  min-width: 0;
}

/* Steps */
.steps {
  display: flex;
  gap: 0;
}

.step {
  flex: 1;
  display: flex;
  align-items: center;
  gap: .6rem;
  padding: .6rem .75rem;
  border-radius: 6px;
  font-size: .8rem;
  color: var(--ink-dim);
  transition: all .2s;
  position: relative;
  min-width: 0;
}

.step-label {
  min-width: 0;
  overflow-wrap: anywhere;
}

.step::after {
  content: '→';
  position: absolute;
  right: -.3rem;
  font-size: .75rem;
  color: var(--line2);
}
.step:last-child::after { display: none; }

.step.active { color: var(--gold); }
.step.done { color: var(--green); }

.step-num {
  width: 22px; height: 22px; flex-shrink: 0;
  border-radius: 50%;
  border: 1px solid currentColor;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono);
  font-size: .65rem;
  font-weight: 500;
  transition: all .2s;
}

.step.done .step-num {
  background: var(--green);
  border-color: var(--green);
  color: #07070d;
}

.step.active .step-num {
  background: var(--gold-dim);
  border-color: var(--gold);
  color: var(--ink);
}

/* Log terminal */
.terminal {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  overflow: hidden;
}

.terminal-bar {
  display: flex;
  align-items: center;
  gap: .5rem;
  padding: .6rem 1rem;
  border-bottom: 1px solid var(--line);
  background: var(--card2);
}

.term-dot {
  width: 9px; height: 9px;
  border-radius: 50%;
}

.terminal-title {
  font-family: var(--mono);
  font-size: .68rem;
  color: var(--ink-dim);
  flex: 1;
  text-align: center;
  letter-spacing: .05em;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.terminal-body {
  padding: 1rem;
  font-family: var(--mono);
  font-size: .72rem;
  line-height: 1.8;
  min-height: 100px;
  max-height: min(220px, 34vh);
  overflow-y: auto;
  color: var(--ink-dim);
}

.log-line { display: flex; gap: .6rem; align-items: flex-start; }
.log-time { color: var(--ink-faint); flex-shrink: 0; }
.log-info,
.log-ok,
.log-warn,
.log-err {
  min-width: 0;
  overflow-wrap: anywhere;
}
.log-info { color: var(--ink-dim); }
.log-ok { color: var(--green); }
.log-warn { color: var(--gold); }
.log-err { color: var(--red); }

/* Spinner */
.spin-line {
  display: none;
  align-items: center;
  gap: .6rem;
  font-family: var(--mono);
  font-size: .75rem;
  color: var(--gold);
}

.spin-line svg { animation: rot .7s linear infinite; flex-shrink: 0; }
@keyframes rot { to { transform: rotate(360deg); } }

/* Results grid */
.results-grid {
  display: none;
  gap: .5rem;
  flex-direction: column;
}

.result-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 1rem;
  padding: .85rem 1rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  transition: border-color .15s;
  animation: slideIn .25s ease both;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}

.result-row:hover { border-color: var(--line2); }

.result-char-wrap {
  width: 44px; height: 44px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  position: relative;
}

.result-char-before {
  font-family: var(--mono);
  font-size: .85rem;
  color: var(--red);
  text-decoration: line-through;
  opacity: .7;
}

.result-char-after {
  font-family: var(--serif);
  font-size: 1.3rem;
  color: var(--gold);
  position: absolute;
  right: 0; bottom: 0;
  line-height: 1;
  background: var(--bg);
  padding: 1px 2px;
}

.result-info { min-width: 0; }
.result-mapping {
  font-family: var(--mono);
  font-size: .7rem;
  color: var(--gold);
  margin-bottom: .25rem;
  letter-spacing: .03em;
  overflow-wrap: anywhere;
}
.result-desc {
  font-size: .8rem;
  color: var(--ink-dim);
  overflow-wrap: anywhere;
}

.result-count {
  font-family: var(--mono);
  font-size: .72rem;
  color: var(--ink-dim);
  background: var(--card2);
  border: 1px solid var(--line);
  padding: .2rem .6rem;
  border-radius: 5px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Stat bar */
.stat-bar {
  display: none;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .75rem;
}

.stat-cell {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 1rem;
  animation: fadeIn .3s ease both;
  min-width: 0;
}

.stat-val {
  font-family: var(--serif);
  font-size: 1.8rem;
  color: var(--gold);
  line-height: 1;
  margin-bottom: .3rem;
}

.stat-key {
  font-family: var(--mono);
  font-size: .65rem;
  color: var(--ink-dim);
  text-transform: uppercase;
  letter-spacing: .08em;
}

/* Download */
.dl-section {
  display: none;
  flex-direction: column;
  gap: .75rem;
  animation: fadeIn .3s ease;
}

.dl-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .75rem;
  flex-wrap: wrap;
  padding: .9rem 1.5rem;
  background: var(--green-dim);
  border: 1.5px solid rgba(95,190,142,0.25);
  border-radius: var(--r);
  color: var(--green);
  font-family: var(--sans);
  font-size: .95rem;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: all .2s;
  letter-spacing: -.01em;
  text-align: center;
}

.dl-btn span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.dl-btn:hover {
  background: rgba(95,190,142,0.18);
  border-color: rgba(95,190,142,0.4);
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(95,190,142,0.1);
}

.dl-note {
  font-family: var(--mono);
  font-size: .68rem;
  color: var(--ink-dim);
  text-align: center;
}

/* No issues */
.no-issues {
  text-align: center;
  padding: 2.5rem 1rem;
  color: var(--ink-dim);
  font-family: var(--mono);
  font-size: .8rem;
}

.no-issues-icon {
  font-size: 2rem;
  margin-bottom: .75rem;
  display: block;
}

/* Error toast */
.toast {
  display: none;
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: #1a0e0e;
  border: 1px solid rgba(224,96,96,0.3);
  color: var(--red);
  padding: .7rem 1.25rem;
  border-radius: 8px;
  font-family: var(--mono);
  font-size: .78rem;
  z-index: 1000;
  animation: toastIn .2s ease;
  width: max-content;
  max-width: min(32rem, calc(100vw - 2rem));
  white-space: normal;
  text-align: center;
}

@keyframes toastIn {
  from { opacity: 0; transform: translateX(-50%) translateY(8px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* Footer */
.footer {
  grid-column: 1 / -1;
  border-top: 1px solid var(--line);
  padding: .75rem calc(var(--page-gutter) + var(--safe-right)) calc(.75rem + var(--safe-bottom)) calc(var(--page-gutter) + var(--safe-left));
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: .65rem;
  color: var(--ink-dim);
  gap: .5rem 1rem;
  flex-wrap: wrap;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--ink-faint); border-radius: 2px; }

/* Responsive */
@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto 1fr auto;
  }

  .left-panel {
    border-right: none;
    border-bottom: 1px solid var(--line);
  }

  .right-panel {
    overflow-y: visible;
  }

  .topbar-right {
    width: 100%;
    justify-content: space-between;
  }
}

@media (max-width: 820px) {
  .left-panel,
  .right-panel {
    padding: 1.1rem calc(var(--page-gutter) + var(--safe-right)) 1.1rem calc(var(--page-gutter) + var(--safe-left));
  }

  .steps {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .55rem;
  }

  .step {
    border: 1px solid var(--line);
    border-radius: var(--r);
    background: var(--card);
  }

  .step::after {
    display: none;
  }

  .stat-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .topbar {
    align-items: flex-start;
  }

  .topbar-right {
    gap: .65rem .9rem;
  }

  .contrast-group {
    max-width: 100%;
  }

  .char-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .result-row {
    grid-template-columns: 44px minmax(0, 1fr);
    align-items: flex-start;
  }

  .result-count {
    grid-column: 2;
    justify-self: start;
  }

  .dl-btn {
    justify-content: flex-start;
  }
}

@media (max-width: 480px) {
  .logo-serif {
    font-size: 1.1rem;
  }

  .topbar-right {
    flex-direction: column;
    align-items: flex-start;
  }

  .lang-switch {
    justify-content: flex-start;
  }

  .steps,
  .stat-bar {
    grid-template-columns: 1fr;
  }

  .terminal-bar {
    padding: .6rem .85rem;
  }

  .terminal-title {
    text-align: left;
  }

  .footer {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 360px) {
  .char-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .file-card-top {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .file-thumb {
    display: none;
  }
}
</style>
</head>
<body>

<div class="shell">

  <!-- ── Topbar ── -->
  <header class="topbar">
    <div class="logo">
      <span class="logo-serif">{{ t.app_name }}</span>
      <span class="logo-tag">{{ version }}</span>
    </div>
    <div class="topbar-right">
      <div class="lang-switch">
        <span class="lang-label">{{ t.language_label }}</span>
        {% for option_code, option_label in lang_options %}
        <a class="lang-link {% if lang == option_code %}active{% endif %}" href="/?lang={{ option_code }}">{{ option_label }}</a>
        {% endfor %}
      </div>
      <div class="contrast-switch">
        <span class="lang-label">{{ t.contrast_label }}</span>
        <div class="contrast-group" role="group" aria-label="{{ t.contrast_label }}">
          <button class="contrast-btn" type="button" data-contrast-target="default">{{ t.contrast_default }}</button>
          <button class="contrast-btn" type="button" data-contrast-target="high">{{ t.contrast_high }}</button>
        </div>
      </div>
      <span class="status-dot">{{ t.status_ready }}</span>
      <span>{{ t.engine_name }}</span>
    </div>
  </header>

  <!-- ── Left ── -->
  <aside class="left-panel">

    <div>
      <div class="panel-label">{{ t.panel_file }}</div>

      <div class="drop-zone" id="dropZone">
        <span class="drop-glyph">Aa</span>
        <div class="drop-title">{{ t.drop_title }}</div>
        <div class="drop-hint">{{ drop_hint }}</div>
        <input type="file" id="fileInput" accept=".pdf">
      </div>

      <div class="file-card" id="fileCard">
        <div class="file-card-top">
          <div class="file-thumb">{{ t.file_thumb }}</div>
          <div class="file-meta">
            <div class="file-name-text" id="fileName"></div>
            <div class="file-size-text" id="fileSize"></div>
          </div>
          <button class="btn-clear" id="btnClear" title="{{ t.remove_file }}">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div>
      <div class="panel-label">{{ t.panel_repaired_characters }}</div>
      <div class="char-grid" id="charGrid">
        <div class="char-cell" data-char="ğ">ğ</div>
        <div class="char-cell" data-char="Ğ">Ğ</div>
        <div class="char-cell" data-char="ı">ı</div>
        <div class="char-cell" data-char="İ">İ</div>
        <div class="char-cell" data-char="ş">ş</div>
        <div class="char-cell" data-char="Ş">Ş</div>
      </div>
    </div>

    <div style="margin-top:auto">
      <button class="btn-primary" id="btnFix" disabled>
        {{ t.btn_analyze_fix }}
      </button>
    </div>

  </aside>

  <!-- ── Right ── -->
  <main class="right-panel">

    <!-- Steps -->
    <div class="steps" id="stepsRow">
      <div class="step" id="step1">
        <div class="step-num">1</div>
        <span class="step-label">{{ t.step_upload }}</span>
      </div>
      <div class="step" id="step2">
        <div class="step-num">2</div>
        <span class="step-label">{{ t.step_analyze }}</span>
      </div>
      <div class="step" id="step3">
        <div class="step-num">3</div>
        <span class="step-label">{{ t.step_repair }}</span>
      </div>
      <div class="step" id="step4">
        <div class="step-num">4</div>
        <span class="step-label">{{ t.step_download }}</span>
      </div>
    </div>

    <!-- Terminal log -->
    <div class="terminal">
      <div class="terminal-bar">
        <div class="term-dot" style="background:#ff5f56"></div>
        <div class="term-dot" style="background:#ffbd2e"></div>
        <div class="term-dot" style="background:#27c93f"></div>
        <div class="terminal-title">{{ t.terminal_title }}</div>
      </div>
      <div class="terminal-body" id="logBody">
        <div class="log-line">
          <span class="log-time">00:00</span>
          <span class="log-info">{{ t.engine_ready_waiting }}</span>
        </div>
      </div>
    </div>

    <!-- Spinner -->
    <div class="spin-line" id="spinLine">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <span id="spinText">{{ t.processing }}</span>
    </div>

    <!-- Stat bar -->
    <div class="stat-bar" id="statBar">
      <div class="stat-cell">
        <div class="stat-val" id="statPages">—</div>
        <div class="stat-key">{{ t.stat_pages }}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statFonts">—</div>
        <div class="stat-key">{{ t.stat_fonts }}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statTypes">—</div>
        <div class="stat-key">{{ t.stat_issue_types }}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statPatches">—</div>
        <div class="stat-key">{{ t.stat_patches }}</div>
      </div>
    </div>

    <!-- Results -->
    <div class="results-grid" id="resultsGrid"></div>

    <!-- Download -->
    <div class="dl-section" id="dlSection">
      <a class="dl-btn" id="dlBtn">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span id="dlBtnText">{{ t.download }}</span>
      </a>
      <div class="dl-note" id="dlNote"></div>
    </div>

  </main>

  <!-- ── Footer ── -->
  <footer class="footer">
    <span>{{ t.footer_text }}</span>
    <span>ğ ı İ ş Ş Ğ</span>
  </footer>

</div>

<div class="toast" id="toast"></div>

<script nonce="{{ csp_nonce }}">
const M = {{ messages|tojson }};
const currentLang = {{ lang|tojson }};
const CONTRAST_STORAGE_KEY = 'pdf-repair-contrast';
let selectedFile = null;
let startTime = null;

const dropZone  = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileCard  = document.getElementById('fileCard');
const fileNameEl= document.getElementById('fileName');
const fileSizeEl= document.getElementById('fileSize');
const btnClear  = document.getElementById('btnClear');
const btnFix    = document.getElementById('btnFix');
const logBody   = document.getElementById('logBody');
const spinLine  = document.getElementById('spinLine');
const spinText  = document.getElementById('spinText');
const statBar   = document.getElementById('statBar');
const resultsGrid = document.getElementById('resultsGrid');
const dlSection = document.getElementById('dlSection');
const dlBtn     = document.getElementById('dlBtn');
const dlBtnText = document.getElementById('dlBtnText');
const dlNote    = document.getElementById('dlNote');
const charGrid  = document.getElementById('charGrid');
const contrastButtons = Array.from(document.querySelectorAll('[data-contrast-target]'));

const steps = [1,2,3,4].map(i => document.getElementById('step'+i));

function t(key, params = {}) {
  let text = M[key] ?? key;
  for (const [name, value] of Object.entries(params)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

function fontWord(count) {
  if (currentLang === 'en') return count === 1 ? 'font' : 'fonts';
  return 'font';
}

function makeOutputName(filename) {
  const suffix = M.output_suffix || '_repaired';
  return filename.replace(/\.pdf$/i, `${suffix}.pdf`);
}

function normalizeContrastMode(value) {
  return value === 'high' ? 'high' : 'default';
}

function applyContrastMode(mode, persist = true) {
  const nextMode = normalizeContrastMode(mode);
  const root = document.documentElement;

  if (nextMode === 'high') root.dataset.contrast = 'high';
  else delete root.dataset.contrast;

  contrastButtons.forEach(button => {
    const active = button.dataset.contrastTarget === nextMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });

  if (persist) {
    try {
      window.localStorage.setItem(CONTRAST_STORAGE_KEY, nextMode);
    } catch (_) {}
  }
}

contrastButtons.forEach(button => {
  button.addEventListener('click', () => applyContrastMode(button.dataset.contrastTarget));
});

applyContrastMode(document.documentElement.dataset.contrast === 'high' ? 'high' : 'default', false);

// ── File handling ──
dropZone.addEventListener('dragenter', e => { e.preventDefault(); dropZone.classList.add('over'); });
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('over'); });
dropZone.addEventListener('dragleave', e => { if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove('over'); });
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('over');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });
btnClear.addEventListener('click', clearFile);
btnFix.addEventListener('click', startFix);

function setFile(f) {
  if (!f.name.toLowerCase().endsWith('.pdf')) { showToast(t('select_pdf_error')); return; }
  selectedFile = f;
  fileNameEl.textContent = f.name;
  fileSizeEl.textContent = fmtSize(f.size);
  dropZone.style.display = 'none';
  fileCard.style.display = 'block';
  btnFix.disabled = false;
  setStep(1);
  resetResults();
  log('info', t('file_uploaded', { name: f.name, size: fmtSize(f.size) }));
}

function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  fileCard.style.display = 'none';
  dropZone.style.display = '';
  btnFix.disabled = true;
  setStep(0);
  resetResults();
  clearChars();
  log('info', t('engine_ready_waiting'));
}

function fmtSize(b) {
  return b > 1048576 ? (b/1048576).toFixed(1)+' MB' : (b/1024).toFixed(0)+' KB';
}

function now() {
  const d = new Date(); 
  return d.toTimeString().slice(0,8);
}

function appendText(node, className, text) {
  const child = document.createElement('span');
  child.className = className;
  child.textContent = text;
  node.appendChild(child);
}

function log(type, msg) {
  const line = document.createElement('div');
  line.className = 'log-line';
  appendText(line, 'log-time', now());
  appendText(line, `log-${type}`, msg);
  logBody.appendChild(line);
  logBody.scrollTop = logBody.scrollHeight;
}

function setStep(n) {
  steps.forEach((s, i) => {
    s.classList.remove('active','done');
    if (i < n) s.classList.add('done');
    else if (i === n) s.classList.add('active');
  });
}

function resetResults() {
  spinLine.style.display = 'none';
  statBar.style.display = 'none';
  resultsGrid.style.display = 'none';
  resultsGrid.replaceChildren();
  dlSection.style.display = 'none';
}

function clearChars() {
  charGrid.querySelectorAll('.char-cell').forEach(c => c.classList.remove('active'));
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3000);
}

function renderNoIssues() {
  const wrap = document.createElement('div');
  wrap.className = 'no-issues';

  const icon = document.createElement('span');
  icon.className = 'no-issues-icon';
  icon.textContent = '✓';

  wrap.appendChild(icon);
  wrap.appendChild(document.createTextNode(t('no_issues')));
  resultsGrid.appendChild(wrap);
}

function activateChar(char) {
  charGrid.querySelectorAll('.char-cell').forEach(cell => {
    if (cell.dataset.char === char) cell.classList.add('active');
  });
}

function createResultRow(fix, index) {
  const row = document.createElement('div');
  row.className = 'result-row';
  row.style.animationDelay = (index * 60) + 'ms';

  const charWrap = document.createElement('div');
  charWrap.className = 'result-char-wrap';

  const before = document.createElement('span');
  before.className = 'result-char-before';
  before.textContent = '?';

  const after = document.createElement('span');
  after.className = 'result-char-after';
  after.textContent = fix.char;

  const info = document.createElement('div');
  info.className = 'result-info';

  const mapping = document.createElement('div');
  mapping.className = 'result-mapping';
  mapping.textContent = fix.mapping;

  const desc = document.createElement('div');
  desc.className = 'result-desc';
  desc.textContent = fix.desc;

  const count = document.createElement('div');
  count.className = 'result-count';
  count.textContent = t('result_count', { count: fix.count, font_word: fontWord(fix.count) });

  charWrap.appendChild(before);
  charWrap.appendChild(after);
  info.appendChild(mapping);
  info.appendChild(desc);
  row.appendChild(charWrap);
  row.appendChild(info);
  row.appendChild(count);
  return row;
}

async function readJsonError(response, fallback) {
  try {
    const payload = await response.json();
    return payload.error || fallback;
  } catch (_) {
    return fallback;
  }
}

async function startFix() {
  if (!selectedFile) return;
  btnFix.disabled = true;
  resetResults();
  clearChars();
  startTime = Date.now();

  // Step 2: Analyze
  setStep(1);
  spinLine.style.display = 'flex';
  spinText.textContent = t('scanning_cmaps');
  log('info', t('analysis_started'));

  const f1 = new FormData(); f1.append('pdf', selectedFile); f1.append('lang', currentLang);
  let d;
  try {
    const r = await fetch('/analyze', { method:'POST', body:f1, headers: { 'X-App-Lang': currentLang } });
    d = await r.json();
  } catch(e) { spinLine.style.display='none'; log('err', t('server_error', { message: e.message })); btnFix.disabled=false; return; }

  if (d.error) { spinLine.style.display='none'; log('err', d.error); showToast(d.error); btnFix.disabled=false; return; }

  // Stats
  document.getElementById('statPages').textContent  = d.page_count ?? '—';
  document.getElementById('statFonts').textContent  = d.font_count ?? '—';
  document.getElementById('statTypes').textContent  = d.fixes ? d.fixes.length : 0;
  document.getElementById('statPatches').textContent = '…';
  statBar.style.display = 'grid';

  setStep(2);
  log('ok', t('analysis_completed', { font_count: d.font_count, fix_count: d.fixes.length }));

  if (!d.fixes || !d.fixes.length) {
    spinLine.style.display = 'none';
    resultsGrid.style.display = 'flex';
    renderNoIssues();
    log('ok', t('clean_pdf'));
    btnFix.disabled = false;
    return;
  }

  // Highlight chars
  d.fixes.forEach(f => {
    activateChar(f.char);
  });

  // Show fix rows
  resultsGrid.style.display = 'flex';
  d.fixes.forEach((f, i) => {
    resultsGrid.appendChild(createResultRow(f, i));
    log('warn', t('affected_fonts', { mapping: f.mapping, count: f.count, font_word: fontWord(f.count) }));
  });

  // Step 3: Fix
  spinText.textContent = t('patching_fonts');
  setStep(2);

  const f2 = new FormData(); f2.append('pdf', selectedFile); f2.append('lang', currentLang);
  let r2;
  try { r2 = await fetch('/fix', { method:'POST', body:f2, headers: { 'X-App-Lang': currentLang } }); }
  catch(e) { spinLine.style.display='none'; log('err', t('repair_error', { message: e.message })); btnFix.disabled=false; return; }

  if (!r2.ok) {
    const message = await readJsonError(r2, t('repair_failed'));
    spinLine.style.display='none';
    log('err', message);
    showToast(message);
    btnFix.disabled=false;
    return;
  }

  const patchCount = r2.headers.get('X-Patch-Count') || '—';
  document.getElementById('statPatches').textContent = patchCount;

  const blob    = await r2.blob();
  const url     = URL.createObjectURL(blob);
  const outName = makeOutputName(selectedFile.name);
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  dlBtn.href = url; dlBtn.download = outName;
  dlBtnText.textContent = outName;
  dlNote.textContent = t('download_note', { elapsed, size: fmtSize(blob.size) });
  dlSection.style.display = 'flex';

  spinLine.style.display = 'none';
  setStep(3);
  log('ok', t('repair_completed', { elapsed }));
  log('ok', t('output_ready', { name: outName, size: fmtSize(blob.size) }));
  btnFix.disabled = false;
}
</script>
</body>
</html>"""


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(exc):
    return handle_api_exception(exc)


@app.errorhandler(BadRequest)
def handle_bad_request(exc):
    return handle_api_exception(exc)

@app.route('/')
def index():
    lang = getattr(g, 'lang', 'tr')
    texts = get_texts(lang)
    return render_template_string(
        HTML,
        csp_nonce=getattr(g, 'csp_nonce', ''),
        t=texts,
        messages=texts,
        lang=lang,
        version=VERSION,
        lang_options=LANGUAGE_OPTIONS,
        max_upload_mb=max_upload_limit_mb(),
        drop_hint=translate('drop_hint', lang, size=max_upload_limit_mb()),
    )

@app.route('/analyze', methods=['POST'])
def analyze():
    lang = get_request_language()
    try:
        upload = validate_pdf_upload(request.files.get('pdf'), lang)
        fixes, font_count, page_count = analyze_pdf(upload.stream, lang)
        return jsonify({'fixes': fixes, 'font_count': font_count, 'page_count': page_count})
    except Exception as exc:
        return handle_api_exception(exc, lang)

@app.route('/fix', methods=['POST'])
def fix():
    lang = get_request_language()
    try:
        upload = validate_pdf_upload(request.files.get('pdf'), lang)
        out, patch_count, _ = fix_pdf_stream(upload.stream, lang)
        resp = send_file(out, mimetype='application/pdf', as_attachment=True,
                         download_name=safe_download_name(upload.filename, lang))
        resp.headers['X-Patch-Count'] = str(patch_count)
        return resp
    except Exception as exc:
        return handle_api_exception(exc, lang)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"→ http://127.0.0.1:{port}")
    app.run(debug=False, host='127.0.0.1', port=port)
