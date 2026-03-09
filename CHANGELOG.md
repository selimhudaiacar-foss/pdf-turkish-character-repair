# Changelog

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
