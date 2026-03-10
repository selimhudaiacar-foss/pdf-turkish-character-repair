# PDF Turkish Character Repair

PDF dosyalarında kopyalama sırasında bozulan Türkçe karakterleri düzeltir.

Bazı PDF'lerde metin ekranda doğru görünür ama kopyalandığında `ğ`, `ı`, `İ`, `ş` gibi Türkçe karakterler bozulur. Bu sorun genellikle PDF içindeki font `ToUnicode CMap` eşlemelerinin hatalı olmasından kaynaklanır. Bu proje PDF'i yeniden oluşturmaz; yalnızca hatalı Unicode eşlemelerini yerinde yamalar.

> Not: Kurulum, çalıştırma, test ve geliştirme komutlarının tamamı için bir sanal ortam (`venv`) kullanmanız tavsiye edilir.

## Ne işe yarar?

Şu tür bozulmaları hedefler:

- `ğ` yerine kontrol karakteri
- `Ğ` yerine kontrol karakteri
- `ı` yerine `1`
- `İ` yerine `1`
- `ş` yerine `_`
- `Ş` yerine `_`

Bu sayede:

- PDF'in görünümü değişmez
- Orijinal sayfa yapısı korunur
- Kopyala-yapıştır sonucu düzelir
- OCR veya yeniden render gerekmez

## Nasıl çalışır?

Araç, PDF içindeki font nesnelerinin `ToUnicode CMap` tablolarını inceler. Bu tablolar CID değerlerini Unicode kod noktalarına eşler. Hedeflenen hata sınıfında PDF görünürde doğru olsa da bu tablolar yanlış doldurulmuştur.

Mevcut sürüm iki aşamalı çalışır:

1. Mümkünse gömülü font programının gerçek `cmap` tablosu okunur.
2. `Type0/CIDFontType2` fontlarda `Unicode -> glyph/GID` eşlemesi, PDF'in `CIDToGIDMap` bilgisiyle CID tarafına geri çevrilir.
3. Basit `TrueType` ve `Type1` fontlarda PDF `Encoding` bilgisi ile `charcode -> glyph -> GID` zinciri kurulur.
4. Aynı glyph için birden fazla Unicode varsa harf > işaret > rakam > noktalama > sembol sıralı bir tercih kuralıyla en anlamlı kod noktası seçilir.
5. Fonttan güvenilir veri alınamazsa mevcut Türkçe heuristikler fallback olarak kullanılır.

Proje şu yaklaşımı izler:

1. PDF açılır.
2. Her fontun `ToUnicode` akışı ve mümkünse gömülü font verisi okunur.
3. Hedef karakterler için bozuk eşlemeler tespit edilir.
4. Yalnızca ilgili CMap satırları patch edilir.
5. PDF, içerik yeniden üretilmeden kaydedilir.

## Temel özellikler

- Web arayüzü (`app.py`)
- Mobil ve tablet ekranlara uyumlu responsive tasarım
- Web arayüzünde kalıcı yüksek kontrast modu
- Komut satırı aracı (`pdf_tr_fix.py`)
- Gömülü font `cmap` tablosundan CID ve simple-font tabanlı doğrulama
- In-place CMap patch mantığı
- Büyük PDF'lerde hızlı çalışma
- Güvenilmeyen PDF girdileri için temel güvenlik sınırları
- Görsel veri kaybı olmadan düzeltme

## Desteklenen hata tipleri

| Bozuk | Doğru | Tespit mantığı |
|---|---|---|
| `U+001F` | `ğ` | Kontrol karakteri olduğu için kesin eşleşme |
| `U+001E` | `Ğ` | Kontrol karakteri olduğu için kesin eşleşme |
| `1` | `ı` | CID'in `i` karakterine komşu olması |
| `1` | `İ` | Birden fazla `1` eşlemesi içinde rakam komşuluğu olmaması |
| `_` | `ş` | CID'in `s` karakterine yakın olması |
| `_` | `Ş` | CID'in `S` karakterine yakın olması |

## Ne zaman işe yarar?

Bu araç özellikle şu durumlarda faydalıdır:

- PDF'te metin seçilebiliyor ama kopyalanınca bozuluyorsa
- PDF görünürde doğru, metin çıkarımında yanlışsa
- Sorun OCR değil, encoding veya CMap kaynaklıysa
- Özellikle Türkçe resmî evraklar, akademik PDF'ler ve raporlarda karakter bozulması varsa

## Ne zaman işe yaramaz?

Şu senaryolar bu projenin kapsamı dışındadır:

- PDF içinde seçilebilir metin yoksa
- Belge taranmış görüntü ise
- Sorun font CMap kaynaklı değilse
- Hedef karakterler dışında farklı bir encoding bozulması varsa
- PDF tamamen bozuksa veya açılamıyorsa

## Kurulum

### Gereksinimler

- Python 3.8+
- `flask`
- `fonttools`
- `pikepdf`

### Depoyu klonlama

```bash
git clone https://github.com/selimhudaiacar-foss/pdf-turkish-character-repair.git
cd pdf-turkish-character-repair
```

### Sanal ortam ve bağımlılıklar

Aşağıdaki kurulum akışı tavsiye edilen yoldur; komutları bir `venv` içinde çalıştırın.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows için:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Hızlı başlangıç

Bu bölümdeki tüm komutlar, aktif bir `venv` içinde çalıştırılıyor varsayımıyla verilmiştir.

### Web arayüzü

```bash
python3 app.py
```

Ardından tarayıcıda `http://127.0.0.1:5000` adresini açın.

Dil seçimi:

- Varsayılan dil tarayıcı diline göre belirlenebilir
- Elle seçmek için `/?lang=tr` veya `/?lang=en` kullanabilirsiniz
- Arayüzün sağ üstünde `TR / EN` geçişi bulunur

Erişilebilirlik ve görünüm:

- Arayüz telefon, tablet ve masaüstü ekranlarda responsive çalışır
- Sağ üstte `Normal / Yüksek` kontrast anahtarı bulunur
- Kontrast seçimi tarayıcıda saklanır ve sonraki açılışlarda korunur

Akış:

1. PDF'i sürükleyip bırakın veya seçin.
2. `Analiz Et & Onar` butonuna basın.
3. Bulunan hata tiplerini inceleyin.
4. Onarılmış PDF'i indirin.

### CLI kullanımı

```bash
python3 pdf_tr_fix.py belge.pdf
```

Varsayılan çıktı:

```text
belge_onarildi.pdf
```

Özel çıktı adı:

```bash
python3 pdf_tr_fix.py belge.pdf onarilmis.pdf
```

Sadece analiz:

```bash
python3 pdf_tr_fix.py belge.pdf --analyze
```

İngilizce çıktı:

```bash
python3 pdf_tr_fix.py --lang en belge.pdf
```

Türkçe çıktıyı zorlamak için:

```bash
python3 pdf_tr_fix.py --lang tr belge.pdf
```

## Örnek CLI çıktısı

```text
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

## Web API özeti

Tarayıcı arayüzü varsayılan olarak tek-upload akışı kullanır:

- `POST /process`
  PDF'i tek istekte analiz eder, gerekiyorsa onarır ve geçici indirme adresi döndürür.
- `GET /download/<token>`
  `POST /process` tarafından üretilen geçici onarılmış PDF'i indirir.

Uyumluluk için şu endpoint'ler korunur:

- `POST /analyze`
  PDF'i sadece analiz eder, bulunan hata türlerini JSON olarak döndürür.
- `POST /fix`
  PDF'i doğrudan onarır ve düzeltilmiş PDF'i indirilebilir yanıt olarak döndürür.

Bu endpoint'ler esasen tarayıcı arayüzü için tasarlanmıştır; resmî public API sözü vermez.

## Deploy notu

Render benzeri production ortamlarda Flask development server yerine aşağıdaki başlatma komutu tercih edilmelidir:

```bash
gunicorn app:app
```

## Güvenlik notları

Güncel sürümlerde şu sertleştirmeler bulunur:

- Yüklenen dosya PDF imzası için doğrulanır
- Aşırı büyük `CMap` akışları reddedilir
- Aşırı geniş mapping aralıkları sınırlandırılır
- Kontrolsüz iç hata mesajları istemciye sızdırılmaz
- Dosya adları güvenli hâle getirilir
- Tarayıcı tarafında XSS riskini azaltan CSP ve güvenlik başlıkları eklenir

Yine de internet üzerinde açık servis olarak kullanılacaksa:

- Flask development server yerine production WSGI sunucusu kullanın
- Reverse proxy arkasında çalıştırın
- Upload rate limit uygulayın
- TLS sonlandırması ekleyin

## Performans

Çalışma süresi şu faktörlerden etkilenir:

- Sayfa sayısı
- Font sayısı
- `ToUnicode CMap` akışı sayısı
- PDF'in genel yapısı

Araç tam metin çıkarımı yapmadığı için birçok belge için hafif kalır. En pahalı kısım ilgili font tablolarının taranmasıdır.
