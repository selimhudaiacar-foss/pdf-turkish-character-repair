"""
PDF Turkish Character Repair Tool — Web UI
===========================================
Detects and repairs broken Turkish characters in PDFs that display correctly
but produce garbled text when copied (ğ→control, ı→1, İ→1, ş→_, Ş→_).

Works by patching the font ToUnicode CMap tables in-place.
No text extraction, no PDF regeneration — zero data loss.

Usage:
    pip install flask pikepdf
    python app.py
    → http://localhost:5000

See pdf_tr_fix.py for the CLI version.
"""
from flask import Flask, request, send_file, render_template_string, jsonify
import pikepdf, re, io
from collections import defaultdict
from pathlib import Path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

def parse_mappings(cmap_text):
    mappings = {}
    for block in re.findall(r'beginbfrange(.*?)endbfrange', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)><([0-9A-Fa-f]+)><([0-9A-Fa-f]+)>', block):
            s,e,b = int(m.group(1),16),int(m.group(2),16),int(m.group(3),16)
            for i,c in enumerate(range(s,e+1)): mappings[c]=b+i
    for block in re.findall(r'beginbfchar(.*?)endbfchar', cmap_text, re.DOTALL):
        for m in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
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

def analyze_pdf(pdf_bytes):
    pdf=pikepdf.open(io.BytesIO(pdf_bytes))
    seen=set(); summary=defaultdict(int); page_count=len(pdf.pages)
    LABELS={
        (0x001F,0x011F):('ğ','U+001F → U+011F','Görünmez kontrol karakteri'),
        (0x001E,0x011E):('Ğ','U+001E → U+011E','Görünmez kontrol karakteri'),
        (0x0031,0x0131):('ı','U+0031 → U+0131','Rakam "1" olarak kodlanmış'),
        (0x0031,0x0130):('İ','U+0031 → U+0130','Rakam "1" olarak kodlanmış'),
        (0x005F,0x015F):('ş','U+005F → U+015F','Alt çizgi "_" olarak kodlanmış'),
        (0x005F,0x015E):('Ş','U+005F → U+015E','Alt çizgi "_" olarak kodlanmış'),
    }
    for page in pdf.pages:
        try:
            fd=page.get('/Resources',{}).get('/Font',{})
            for _,fref in fd.items():
                fobj=fref
                try: objnum=fobj.objgen[0]
                except: continue
                if objnum in seen or '/ToUnicode' not in fobj: continue
                seen.add(objnum)
                cmap=bytes(fobj['/ToUnicode'].read_bytes()).decode('latin-1')
                for _,(wrong,correct) in find_fixes(parse_mappings(cmap)).items():
                    summary[(wrong,correct)]+=1
        except: pass
    results=[]
    for (wrong,correct),cnt in sorted(summary.items(),key=lambda x:-x[1]):
        char,mapping,desc=LABELS.get((wrong,correct),(f'?',f'U+{wrong:04X}→U+{correct:04X}',''))
        results.append({'char':char,'mapping':mapping,'desc':desc,'count':cnt})
    return results, len(seen), page_count

def fix_pdf_bytes(pdf_bytes):
    pdf=pikepdf.open(io.BytesIO(pdf_bytes)); seen=set(); total=0; fonts_fixed=0
    for page in pdf.pages:
        try:
            fd=page.get('/Resources',{}).get('/Font',{})
            for _,fref in fd.items():
                fobj=fref
                try: objnum=fobj.objgen[0]
                except: continue
                if objnum in seen or '/ToUnicode' not in fobj: continue
                seen.add(objnum)
                cmap_text=bytes(fobj['/ToUnicode'].read_bytes()).decode('latin-1')
                fixes=find_fixes(parse_mappings(cmap_text))
                if not fixes: continue
                new_cmap,count=patch_cmap(cmap_text,fixes)
                if count>0:
                    fobj['/ToUnicode']=pdf.make_stream(new_cmap.encode('latin-1'))
                    total+=count; fonts_fixed+=1
        except: pass
    out=io.BytesIO(); pdf.save(out); out.seek(0)
    return out, total, fonts_fixed

HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF Onarıcı</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist+Mono:wght@300;400;500&family=Geist:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* ── Reset & Tokens ─────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #07070d;
  --ink:       #f0ede6;
  --ink-dim:   #7a7870;
  --ink-faint: #2e2c2a;
  --card:      #0e0d13;
  --card2:     #161420;
  --line:      rgba(240,237,230,0.07);
  --line2:     rgba(240,237,230,0.13);
  --gold:      #d4a853;
  --gold-dim:  rgba(212,168,83,0.15);
  --gold-glow: rgba(212,168,83,0.06);
  --green:     #5fbe8e;
  --green-dim: rgba(95,190,142,0.12);
  --red:       #e06060;
  --mono: 'Geist Mono', monospace;
  --serif: 'Instrument Serif', Georgia, serif;
  --sans: 'Geist', sans-serif;
  --r: 10px;
}

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
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

/* ── Layout ─────────────────────────────────────── */
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 340px 1fr;
  grid-template-rows: auto 1fr auto;
}

/* ── Topbar ─────────────────────────────────────── */
.topbar {
  grid-column: 1 / -1;
  border-bottom: 1px solid var(--line);
  padding: 0 2rem;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: baseline;
  gap: .6rem;
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
  gap: 1.5rem;
}

.status-dot {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
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
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
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
  padding: 2.5rem 1.5rem;
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
  border-color: rgba(212,168,83,0.3);
  background: rgba(212,168,83,0.02);
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
}

.drop-hint {
  font-family: var(--mono);
  font-size: .68rem;
  color: var(--ink-dim);
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
  display: flex;
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
  grid-template-columns: repeat(6, 1fr);
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
  border-color: rgba(212,168,83,0.3);
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
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  overflow-y: auto;
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
}

.terminal-body {
  padding: 1rem;
  font-family: var(--mono);
  font-size: .72rem;
  line-height: 1.8;
  min-height: 100px;
  max-height: 200px;
  overflow-y: auto;
  color: var(--ink-dim);
}

.log-line { display: flex; gap: .6rem; }
.log-time { color: var(--ink-faint); flex-shrink: 0; }
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
  display: flex;
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

.result-info { flex: 1; }
.result-mapping {
  font-family: var(--mono);
  font-size: .7rem;
  color: var(--gold);
  margin-bottom: .25rem;
  letter-spacing: .03em;
}
.result-desc { font-size: .8rem; color: var(--ink-dim); }

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
  grid-template-columns: repeat(4, 1fr);
  gap: .75rem;
}

.stat-cell {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 1rem;
  animation: fadeIn .3s ease both;
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
  white-space: nowrap;
}

@keyframes toastIn {
  from { opacity: 0; transform: translateX(-50%) translateY(8px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* Footer */
.footer {
  grid-column: 1 / -1;
  border-top: 1px solid var(--line);
  padding: .75rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: .65rem;
  color: var(--ink-faint);
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
@media (max-width: 700px) {
  .shell { grid-template-columns: 1fr; }
  .left-panel { border-right: none; border-bottom: 1px solid var(--line); }
  .topbar-right { display: none; }
  .stat-bar { grid-template-columns: repeat(2,1fr); }
}
</style>
</head>
<body>

<div class="shell">

  <!-- ── Topbar ── -->
  <header class="topbar">
    <div class="logo">
      <span class="logo-serif">PDF Onarıcı</span>
      <span class="logo-tag">v2.1</span>
    </div>
    <div class="topbar-right">
      <span class="status-dot">Hazır</span>
      <span>CMap Patch Engine</span>
    </div>
  </header>

  <!-- ── Left ── -->
  <aside class="left-panel">

    <div>
      <div class="panel-label">Dosya</div>

      <div class="drop-zone" id="dropZone">
        <span class="drop-glyph">Aa</span>
        <div class="drop-title">PDF'i bırakın veya tıklayın</div>
        <div class="drop-hint">Maks. 100 MB · .pdf</div>
        <input type="file" id="fileInput" accept=".pdf">
      </div>

      <div class="file-card" id="fileCard">
        <div class="file-card-top">
          <div class="file-thumb">PDF</div>
          <div class="file-meta">
            <div class="file-name-text" id="fileName"></div>
            <div class="file-size-text" id="fileSize"></div>
          </div>
          <button class="btn-clear" id="btnClear" title="Kaldır">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div>
      <div class="panel-label">Onarılan Karakterler</div>
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
      <button class="btn-primary" id="btnFix" disabled onclick="startFix()">
        Analiz Et &amp; Onar
      </button>
    </div>

  </aside>

  <!-- ── Right ── -->
  <main class="right-panel">

    <!-- Steps -->
    <div class="steps" id="stepsRow">
      <div class="step" id="step1">
        <div class="step-num">1</div>
        <span>Dosya yükle</span>
      </div>
      <div class="step" id="step2">
        <div class="step-num">2</div>
        <span>Analiz</span>
      </div>
      <div class="step" id="step3">
        <div class="step-num">3</div>
        <span>Onarım</span>
      </div>
      <div class="step" id="step4">
        <div class="step-num">4</div>
        <span>İndir</span>
      </div>
    </div>

    <!-- Terminal log -->
    <div class="terminal">
      <div class="terminal-bar">
        <div class="term-dot" style="background:#ff5f56"></div>
        <div class="term-dot" style="background:#ffbd2e"></div>
        <div class="term-dot" style="background:#27c93f"></div>
        <div class="terminal-title">cmap-patch.log</div>
      </div>
      <div class="terminal-body" id="logBody">
        <div class="log-line">
          <span class="log-time">00:00</span>
          <span class="log-info">Motor hazır. Dosya bekleniyor…</span>
        </div>
      </div>
    </div>

    <!-- Spinner -->
    <div class="spin-line" id="spinLine">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <span id="spinText">İşleniyor…</span>
    </div>

    <!-- Stat bar -->
    <div class="stat-bar" id="statBar">
      <div class="stat-cell">
        <div class="stat-val" id="statPages">—</div>
        <div class="stat-key">Sayfa</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statFonts">—</div>
        <div class="stat-key">Font</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statTypes">—</div>
        <div class="stat-key">Hata türü</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val" id="statPatches">—</div>
        <div class="stat-key">Patch</div>
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
        <span id="dlBtnText">İndir</span>
      </a>
      <div class="dl-note" id="dlNote"></div>
    </div>

  </main>

  <!-- ── Footer ── -->
  <footer class="footer">
    <span>Font ToUnicode CMap · In-place patch · Sıfır veri kaybı</span>
    <span>ğ ı İ ş Ş Ğ</span>
  </footer>

</div>

<div class="toast" id="toast"></div>

<script>
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

const steps = [1,2,3,4].map(i => document.getElementById('step'+i));

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

function setFile(f) {
  if (!f.name.toLowerCase().endsWith('.pdf')) { showToast('Lütfen bir .pdf dosyası seçin'); return; }
  selectedFile = f;
  fileNameEl.textContent = f.name;
  fileSizeEl.textContent = fmtSize(f.size);
  dropZone.style.display = 'none';
  fileCard.style.display = 'block';
  btnFix.disabled = false;
  setStep(1);
  resetResults();
  log('info', 'Dosya yüklendi: ' + f.name + ' (' + fmtSize(f.size) + ')');
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
  log('info', 'Motor hazır. Dosya bekleniyor…');
}

function fmtSize(b) {
  return b > 1048576 ? (b/1048576).toFixed(1)+' MB' : (b/1024).toFixed(0)+' KB';
}

function now() {
  const d = new Date(); 
  return d.toTimeString().slice(0,8);
}

function log(type, msg) {
  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `<span class="log-time">${now()}</span><span class="log-${type}">${msg}</span>`;
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
  resultsGrid.innerHTML = '';
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

async function startFix() {
  if (!selectedFile) return;
  btnFix.disabled = true;
  resetResults();
  clearChars();
  startTime = Date.now();

  // Step 2: Analyze
  setStep(1);
  spinLine.style.display = 'flex';
  spinText.textContent = 'CMap tabloları taranıyor…';
  log('info', 'Analiz başladı…');

  const f1 = new FormData(); f1.append('pdf', selectedFile);
  let d;
  try {
    const r = await fetch('/analyze', { method:'POST', body:f1 });
    d = await r.json();
  } catch(e) { spinLine.style.display='none'; log('err','Sunucu hatası: '+e.message); btnFix.disabled=false; return; }

  if (d.error) { spinLine.style.display='none'; log('err', d.error); showToast(d.error); btnFix.disabled=false; return; }

  // Stats
  document.getElementById('statPages').textContent  = d.page_count ?? '—';
  document.getElementById('statFonts').textContent  = d.font_count ?? '—';
  document.getElementById('statTypes').textContent  = d.fixes ? d.fixes.length : 0;
  document.getElementById('statPatches').textContent = '…';
  statBar.style.display = 'grid';

  setStep(2);
  log('ok', `Analiz tamamlandı: ${d.font_count} font, ${d.fixes.length} hata türü`);

  if (!d.fixes || !d.fixes.length) {
    spinLine.style.display = 'none';
    resultsGrid.style.display = 'flex';
    resultsGrid.innerHTML = '<div class="no-issues"><span class="no-issues-icon">✓</span>Türkçe karakter hatası bulunamadı</div>';
    log('ok', 'Bu PDF temiz görünüyor.');
    btnFix.disabled = false;
    return;
  }

  // Highlight chars
  d.fixes.forEach(f => {
    const cell = charGrid.querySelector(`[data-char="${f.char}"]`);
    if (cell) cell.classList.add('active');
  });

  // Show fix rows
  resultsGrid.style.display = 'flex';
  d.fixes.forEach((f, i) => {
    const row = document.createElement('div');
    row.className = 'result-row';
    row.style.animationDelay = (i * 60) + 'ms';
    row.innerHTML = `
      <div class="result-char-wrap">
        <span class="result-char-before">?</span>
        <span class="result-char-after">${f.char}</span>
      </div>
      <div class="result-info">
        <div class="result-mapping">${f.mapping}</div>
        <div class="result-desc">${f.desc}</div>
      </div>
      <div class="result-count">${f.count} font</div>
    `;
    resultsGrid.appendChild(row);
    log('warn', `${f.mapping} — ${f.count} font etkilenmiş`);
  });

  // Step 3: Fix
  spinText.textContent = 'Font tabloları yamalanıyor…';
  setStep(2);

  const f2 = new FormData(); f2.append('pdf', selectedFile);
  let r2;
  try { r2 = await fetch('/fix', { method:'POST', body:f2 }); }
  catch(e) { spinLine.style.display='none'; log('err','Onarım hatası: '+e.message); btnFix.disabled=false; return; }

  if (!r2.ok) { spinLine.style.display='none'; log('err','Onarım başarısız.'); btnFix.disabled=false; return; }

  const patchCount = r2.headers.get('X-Patch-Count') || '—';
  document.getElementById('statPatches').textContent = patchCount;

  const blob    = await r2.blob();
  const url     = URL.createObjectURL(blob);
  const outName = selectedFile.name.replace(/\.pdf$/i, '_onarildi.pdf');
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  dlBtn.href = url; dlBtn.download = outName;
  dlBtnText.textContent = outName;
  dlNote.textContent = `${elapsed}s — ${fmtSize(blob.size)}`;
  dlSection.style.display = 'flex';

  spinLine.style.display = 'none';
  setStep(3);
  log('ok', `Onarım tamamlandı — ${elapsed}s sürdü`);
  log('ok', `Çıktı: ${outName} (${fmtSize(blob.size)})`);
  btnFix.disabled = false;
}
</script>
</body>
</html>"""

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'pdf' not in request.files: return jsonify({'error':'PDF bulunamadı'}), 400
    try:
        fixes, font_count, page_count = analyze_pdf(request.files['pdf'].read())
        return jsonify({'fixes': fixes, 'font_count': font_count, 'page_count': page_count})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/fix', methods=['POST'])
def fix():
    if 'pdf' not in request.files: return jsonify({'error':'PDF bulunamadı'}), 400
    f = request.files['pdf']
    try:
        out, patch_count, fonts_fixed = fix_pdf_bytes(f.read())
        resp = send_file(out, mimetype='application/pdf', as_attachment=True,
                         download_name=Path(f.filename).stem+'_onarildi.pdf')
        resp.headers['X-Patch-Count'] = str(patch_count)
        return resp
    except Exception as e: return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("→ http://localhost:5000")
    app.run(debug=False, host='0.0.0.0', port=5000)
