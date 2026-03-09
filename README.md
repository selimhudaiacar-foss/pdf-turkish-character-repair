# PDF Türkçe Karakter Onarıcı

PDF dosyalarında kopyalama sırasında bozulan Türkçe karakterleri otomatik olarak onarır.

> **Sorun:** Bazı PDF'lerde ğ, ı, İ, ş, Ş gibi Türkçe harfler görsel olarak doğru görünür, ancak kopyalanınca `1`, `_` veya görünmez kontrol karakterlerine dönüşür.  
> **Çözüm:** Font'ların ToUnicode CMap tablolarındaki hatalı eşleşmeleri tespit edip in-place onarır — PDF yeniden oluşturulmaz, içerik korunur.

---

## Özellikler

- **6 karakter** onarımı: `ğ` `Ğ` `ı` `İ` `ş` `Ş`
- **Sıfır veri kaybı** — sadece CMap tabloları yamalanır
- **Web arayüzü** (`app.py`) ve **CLI** (`pdf_tr_fix.py`) desteği
- Büyük PDF'lerde hızlı — 400+ sayfalık dosyayı ~5 saniyede işler

## Desteklenen Hata Tipleri

| Bozuk | Doğru | Tespit yöntemi |
|-------|-------|----------------|
| `U+001F` (kontrol karakteri) | **ğ** | Kesin — kontrol karakteri |
| `U+001E` (kontrol karakteri) | **Ğ** | Kesin — kontrol karakteri |
| `1` (rakam) | **ı** | CID'in `i` harfine komşu olması |
| `1` (rakam) | **İ** | Birden fazla `1` var, bu CID'in digit komşusu yok |
| `_` (alt çizgi) | **ş** | CID'in `s` harfine yakın olması |
| `_` (alt çizgi) | **Ş** | CID'in `S` harfine yakın olması |

---

## Kurulum

```bash
git clone https://github.com/kullanici/pdf-turkish-fix
cd pdf-turkish-fix

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## Kullanım

### Web Arayüzü

```bash
python3 app.py
# → http://localhost:5000
```

PDF'i sürükle-bırak veya tıklayarak yükle, "Analiz Et & Onar" butonuna bas, onarılmış dosyayı indir.

### Komut Satırı (CLI)

```bash
# Onar (çıktı: dosya_onarildi.pdf)
python3 pdf_tr_fix.py belge.pdf

# Çıktı dosyasını belirt
python3 pdf_tr_fix.py belge.pdf onarilmis.pdf

# Sadece analiz et, değiştirme
python3 pdf_tr_fix.py belge.pdf --analyze
```

#### Örnek çıktı

```
Açılıyor: belge.pdf

Tespit edilen düzeltmeler:
  '_' → ş: 772 font
  U+001F → ğ: 752 font
  '1' → ı: 697 font
  '1' → İ: 384 font
  '_' → Ş: 176 font

Düzeltilen font: 879  |  Toplam patch: 2781
Kaydedildi: belge_onarildi.pdf
```

---

## Teknik Detay

PDF'lerdeki font nesneleri, her karakter kodunu (CID) Unicode kod noktasına eşleyen **ToUnicode CMap** tablolarına sahiptir. Bazı PDF oluşturucular bu tabloları hatalı doldurur:

- Türkçe özgü karakterler yerine benzer görünen ASCII veya kontrol karakterleri yazar
- Örnek: `ğ` (U+011F) yerine `U+001F` (kontrol), `ı` (U+0131) yerine `1` (U+0031)

Bu araç, pikepdf ile CMap tablolarını okur, hatalı eşleşmeleri istatistiksel örüntülerle tespit eder ve doğrudan yamar. PDF'in görsel içeriği hiç değişmez.

---

## Gereksinimler

- Python 3.8+
- `flask` ≥ 3.0
- `pikepdf` ≥ 8.0

---

## Lisans

MIT
