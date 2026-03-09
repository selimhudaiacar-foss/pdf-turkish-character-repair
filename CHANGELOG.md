# Changelog

## v2.4.0 - 2026-03-10

Bu sürüm web arayüzünün erişilebilirliği ve cihaz uyumluluğuna odaklanır. Arayüz artık telefon, tablet ve masaüstünde daha tutarlı davranır; ayrıca VS Code benzeri kalıcı bir yüksek kontrast modu sunar.

### Eklenenler

- Web arayüzüne `Normal / Yuksek` kontrast anahtarı eklendi.
- Yüksek kontrast tercihini `localStorage` ile saklayan istemci tarafı tema akışı eklendi.
- Tarayıcı `prefers-contrast: more` sinyalini algılayıp başlangıç temasını buna göre seçen başlangıç betiği eklendi.
- Klavye odağı için daha görünür `:focus-visible` halkaları eklendi.

### İyileştirmeler

- Ana layout telefon, tablet ve dar dizüstü genişlikleri için çoklu breakpoint ile yeniden düzenlendi.
- Üst bar, adım akışı, sonuç kartları, istatistik alanı, indirme bloğu ve footer dar ekranlarda taşmayacak şekilde güncellendi.
- Safe-area inset desteği ile çentikli mobil cihazlarda içerik boşlukları iyileştirildi.
- Düşük kontrastlı metin ve ayrım çizgileri hem normal hem yüksek kontrast temasında daha okunur hale getirildi.

### Dokümantasyon

- `README.md` dosyasına responsive arayüz ve yüksek kontrast modu bilgileri eklendi.

### Doğrulama

- `python3 -m py_compile app.py pdf_tr_fix.py`
- Yerel Flask açılış testi ve `GET /` için `200 OK` doğrulaması

## v2.3.0 - 2026-03-09

Bu sürüm dil desteği ve dokümantasyon iyileştirmelerine odaklanır. Web arayüzü ve CLI artık Türkçe ile birlikte İngilizce de destekler; ayrıca kurulum ve geliştirme akışlarında `venv` kullanımı daha görünür hale getirilmiştir.

### Eklenenler

- Web arayüzüne TR/EN dil desteği eklendi.
- CLI aracına `--lang {tr,en}` seçeneği eklendi.
- Web tarafında dil seçimi için `TR / EN` geçişi eklendi.
- Tarayıcı dili ve istek parametresine göre dil belirleme akışı eklendi.

### İyileştirmeler

- Web arayüzündeki statik ve dinamik metinler yerelleştirildi.
- API hata mesajları seçilen dile göre döndürülür hale getirildi.
- İndirilen dosya adı dile göre `_onarildi` veya `_repaired` son eki alacak şekilde güncellendi.
- CLI yardım metinleri ve çıktı mesajları seçilen dile göre uyarlanır hale getirildi.
- `README.md` dosyası, dil desteği ve `venv` tavsiyesi açısından genişletildi.

### Dokümantasyon

- Kurulum, hızlı başlangıç ve geliştirme bölümlerine `venv` kullanım tavsiyesi eklendi.
- Web için `/?lang=en` ve `/?lang=tr` kullanımı belgelendi.
- CLI için İngilizce ve Türkçe kullanım örnekleri eklendi.

### Doğrulama

- `python3 -m py_compile app.py pdf_tr_fix.py`
- Web arayüzü `?lang=en` render testi
- İngilizce API hata yanıtı testi
- İngilizce `Content-Disposition` dosya adı testi
- CLI `--lang en --help` testi
- CLI `--lang en --analyze` testi

## v2.2.0 - 2026-03-09

Bu sürüm güvenlik sertleştirmesine odaklanır. Web arayüzü ve CLI, güvenilmeyen PDF girdilerine karşı daha sıkı doğrulama ve daha kontrollü hata yönetimi ile güncellendi.

### Eklenenler

- Yüklenen dosyanın gerçekten PDF olup olmadığını doğrulayan giriş kontrolü eklendi.
- `ToUnicode CMap` akışları için boyut, aralık ve toplam eşleme limitleri eklendi.
- HTTP yanıtlarına `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` ve `Cross-Origin-Resource-Policy` başlıkları eklendi.
- Script yürütmesini sınırlandırmak için nonce tabanlı CSP akışı eklendi.

### Güvenlik Düzeltmeleri

- Küçük ama kötü niyetli PDF'lerle tetiklenebilen algoritmik DoS riski kapatıldı.
- Bellekte birden fazla PDF kopyası tutulmasına yol açan akış sadeleştirildi; çıktı üretimi için `SpooledTemporaryFile` kullanıldı.
- Dosya adı kaynaklı istemci tarafı XSS riski kaldırıldı; log ve sonuç alanları güvenli DOM API'leri ile render ediliyor.
- İç istisna mesajlarının istemciye sızması engellendi; kullanıcıya kontrollü hata yanıtları dönülüyor.
- İndirme dosya adı `secure_filename` ile normalize edilerek header enjeksiyonu ve problemli karakterler temizlendi.
- Geliştirme sunucusunun varsayılan bind adresi `0.0.0.0` yerine `127.0.0.1` yapıldı.
- PDF açma sırasında agresif recovery yolu kapatıldı (`attempt_recovery=False`).

### Davranış Değişiklikleri

- Geçersiz PDF yüklemeleri artık `400` ile net biçimde reddediliyor.
- Boyut aşımı durumunda API, yapılandırılmış `413` JSON hatası döndürüyor.
- Şüpheli veya anormal büyüklükte `CMap` içeren PDF'ler işlenmeden reddediliyor.
- İndirme adı artık kullanıcıdan gelen ham dosya adını birebir yansıtmıyor; güvenlileştirilmiş isim kullanılıyor.

### Operasyon Notları

- Yerel araç zincirindeki `pip` sürümü `26.0.1`'e yükseltildi.
- `pip-audit` kontrolü sonrası bilinen bir bağımlılık zafiyeti kalmadı.

### Doğrulama

- `python3 -m py_compile app.py pdf_tr_fix.py`
- Geçersiz PDF yükleme testi
- Güvenli `Content-Disposition` testi
- `CMap` guard testi
- Boyut limiti testi
- `./bin/python -m pip_audit`
