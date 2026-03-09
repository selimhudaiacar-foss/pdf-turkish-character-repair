# PDF Turkish Character Repair

PDF dosyalarında kopyalama sırasında bozulan Turkce karakterleri duzeltir.

Bazi PDF'lerde metin ekranda dogru gorunur ama kopyalandiginda `g`, `i` veya `s` ailesindeki Turkce karakterler bozulur. Sorun genelde PDF icindeki font `ToUnicode CMap` eslemelerinin hatali olmasindan kaynaklanir. Bu proje PDF'i yeniden olusturmaz; sadece hatali Unicode eslemelerini yerinde yamalar.

> Not: Kurulum, calistirma, test ve gelistirme komutlarinin tamami icin bir sanal ortam (`venv`) kullanmaniz tavsiye edilir.

## Ne ise yarar?

Su tip bozulmalari hedefler:

- `ğ` yerine kontrol karakteri
- `Ğ` yerine kontrol karakteri
- `ı` yerine `1`
- `İ` yerine `1`
- `ş` yerine `_`
- `Ş` yerine `_`

Bu sayede:

- PDF'in gorunumu degismez
- Orijinal sayfa yapisi korunur
- Kopyala-yapistir sonucu duzelir
- OCR veya yeniden render gerekmez

## Nasil calisir?

Arac, PDF icindeki font nesnelerinin `ToUnicode CMap` tablolarini inceler. Bu tablolar CID degerlerini Unicode kod noktalarina map eder. Hedeflenen hata sinifinda PDF gorunurde dogru olsa da bu tablolar yanlis doldurulmustur.

Proje su yaklasimi kullanir:

1. PDF acilir.
2. Her fontun `ToUnicode` akisi okunur.
3. Hedef karakterler icin bozuk eslemeler tespit edilir.
4. Sadece ilgili CMap satirlari patch edilir.
5. PDF yeni bir icerik uretilmeden kaydedilir.

## Temel ozellikler

- Web arayuzu (`app.py`)
- Mobil ve tablet ekranlara uyumlu responsive tasarim
- Web arayuzunde kalici yuksek kontrast modu
- Komut satiri araci (`pdf_tr_fix.py`)
- In-place CMap patch mantigi
- Buyuk PDF'lerde hizli calisma
- Guvenilmeyen PDF girdileri icin temel guvenlik sinirlari
- Gorsel veri kaybi olmadan duzeltme

## Desteklenen hata tipleri

| Bozuk | Dogru | Tespit mantigi |
|---|---|---|
| `U+001F` | `ğ` | Kontrol karakteri oldugu icin kesin eslesme |
| `U+001E` | `Ğ` | Kontrol karakteri oldugu icin kesin eslesme |
| `1` | `ı` | CID'in `i` karakterine komsu olmasi |
| `1` | `İ` | Birden fazla `1` eslemesi icinde rakam komsulugu olmamasi |
| `_` | `ş` | CID'in `s` karakterine yakin olmasi |
| `_` | `Ş` | CID'in `S` karakterine yakin olmasi |

## Ne zaman ise yarar?

Bu arac ozellikle su durumda faydalidir:

- PDF'te metin secilebiliyor ama kopyalaninca bozuluyor
- PDF gorunurde dogru, metin cikariminda yanlis
- Sorun OCR degil, encoding veya CMap kaynakli
- Ozellikle Turkce resmi evraklar, akademik PDF'ler ve raporlarda karakter bozulmasi var

## Ne zaman ise yaramaz?

Su senaryolar bu projenin kapsami disindadir:

- PDF icinde secilebilir metin yoksa
- Belge taranmis goruntu ise
- Sorun font CMap degilse
- Hedef karakterler disinda farkli bir encoding bozulmasi varsa
- PDF tamamen kirik veya acilamiyorsa

## Kurulum

### Gereksinimler

- Python 3.8+
- `flask`
- `pikepdf`

### Depoyu klonlama

```bash
git clone https://github.com/selimhudaiacar-foss/pdf-turkish-character-repair.git
cd pdf-turkish-character-repair
```

### Sanal ortam ve bagimliliklar

Asagidaki kurulum akisi tavsiye edilen yoldur; komutlari bir `venv` icinde calistirin.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows icin:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Hizli baslangic

Bu bolumdeki tum komutlar, aktif bir `venv` icinde calistiriliyor varsayimi ile verilmiştir.

### Web arayuzu

```bash
python3 app.py
```

Ardindan tarayicida `http://127.0.0.1:5000` adresini acin.

Dil secimi:

- Varsayilan dil tarayici diline gore belirlenebilir
- Elle secmek icin `/?lang=tr` veya `/?lang=en` kullanabilirsiniz
- Arayuzun sag ustunde `TR / EN` gecisi bulunur

Erisebilirlik ve gorunum:

- Arayuz telefon, tablet ve masaustu ekranlarda responsive calisir
- Sag ustte `Normal / Yuksek` kontrast anahtari bulunur
- Kontrast secimi tarayicida saklanir ve sonraki acilislarda korunur

Akis:

1. PDF'i surukleyip birakin veya secin.
2. `Analiz Et & Onar` butonuna basin.
3. Bulunan hata tiplerini inceleyin.
4. Onarilmis PDF'i indirin.

### CLI kullanimi

```bash
python3 pdf_tr_fix.py belge.pdf
```

Varsayilan cikti:

```text
belge_onarildi.pdf
```

Ozel cikti adi:

```bash
python3 pdf_tr_fix.py belge.pdf onarilmis.pdf
```

Sadece analiz:

```bash
python3 pdf_tr_fix.py belge.pdf --analyze
```

Ingilizce cikti:

```bash
python3 pdf_tr_fix.py --lang en belge.pdf
```

Turkce ciktiyi zorlamak icin:

```bash
python3 pdf_tr_fix.py --lang tr belge.pdf
```

## Ornek CLI cikti

```text
Aciliyor: belge.pdf

Tespit edilen duzeltmeler:
  '_' → ş: 772 font
  U+001F → ğ: 752 font
  '1' → ı: 697 font
  '1' → İ: 384 font
  '_' → Ş: 176 font

Duzeltilen font: 879  |  Toplam patch: 2781
Kaydedildi: belge_onarildi.pdf
```

## Web API ozeti

Tarayici arayuzu varsayilan olarak tek-upload akisi kullanir:

- `POST /process`
  PDF'i tek istekte analiz eder, gerekiyorsa onarir ve gecici indirme adresi dondurur.
- `GET /download/<token>`
  `POST /process` tarafindan uretilen gecici onarilmis PDF'i indirir.

Uyumluluk icin su endpoint'ler korunur:

- `POST /analyze`
  PDF'i sadece analiz eder, bulunan hata turlerini JSON olarak dondurur.
- `POST /fix`
  PDF'i dogrudan onarir ve duzeltilmis PDF'i indirilebilir yanit olarak dondurur.

Bu endpoint'ler esasen tarayici arayuzu icin tasarlanmistir; resmi public API sozu vermez.

## Deploy notu

Render benzeri production ortamlarda Flask development server yerine asagidaki baslatma komutu tercih edilmelidir:

```bash
gunicorn app:app
```

## Guvenlik notlari

Guncel surumlerde su sertlestirmeler bulunur:

- Yuklenen dosya PDF imzasi icin dogrulaniyor
- Asiri buyuk `CMap` akislari reddediliyor
- Asiri genis mapping araliklari sinirlaniyor
- Kontrolsuz ic hata mesajlari istemciye sizdirilmiyor
- Dosya adlari guvenli hale getiriliyor
- Tarayici tarafinda XSS riskini azaltan CSP ve guvenlik basliklari ekleniyor

Yine de internet uzerinde acik servis olarak kullanilacaksa:

- Flask development server yerine production WSGI sunucusu kullanin
- Reverse proxy arkasinda calistirin
- Upload rate limit uygulayin
- TLS sonlandirmasi ekleyin

## Performans

Calisma su faktorlerden etkilenir:

- Sayfa sayisi
- Font sayisi
- `ToUnicode CMap` akisi sayisi
- PDF'in genel yapisi

Arac tam metin cikarimi yapmadigi icin bircok belge icin hafif kalir. En pahali kisim ilgili font tablolarinin taranmasidir.

## Proje yapisi

```text
app.py           Flask tabanli web arayuzu
pdf_tr_fix.py    Komut satiri araci
requirements.txt Python bagimliliklari
CHANGELOG.md     Surum notlari
```

## Gelistirme

Gelistirme araclarini da ayri bir `venv` icinde calistirmaniz tavsiye edilir.

Yerelde hizli dogrulama icin:

```bash
source venv/bin/activate
python -m py_compile app.py pdf_tr_fix.py
```

Bagimlilik denetimi:

```bash
source venv/bin/activate
python -m pip_audit
```

## Sinirlar

- Su anda yalnizca belirli Turkce karakter bozulmalarina odaklidir
- Her bozuk PDF icin evrensel bir cozum degildir
- Heuristik kurallar sebebiyle nadir belgelerde hic bulgu olmayabilir
- Font'larda `ToUnicode` akisi yoksa arac etkisiz kalabilir

## Yol haritasi icin fikirler

- Daha fazla Turkce karakter varyanti
- Batch isleme modu
- Test PDF koleksiyonu
- Otomatik regresyon testleri
- Docker paketi

## Lisans

MIT
