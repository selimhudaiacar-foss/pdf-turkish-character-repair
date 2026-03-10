# Changelog

## v3.1 - 2026-03-10

Bu sürüm `ToUnicode` onarımını yalnızca mevcut CMap içeriğine bakarak değil, mümkün olduğunda gömülü fontun kendi `cmap` verisini okuyarak yapar. Böylece bozuk eşlemeler font programındaki gerçek glyph ilişkileriyle doğrulanır; güvenli aday bulunamadığında mevcut Türkçe heuristikler fallback olarak korunur.

### Eklenenler

- Gömülü font programını okuyup `Unicode -> GID` eşlemeleri çıkaran font tabanlı onarım hattı eklendi.
- `Type0/CIDFontType2` fontlar için `CIDToGIDMap` destekli `CID -> Unicode` geri eşleme akışı eklendi.
- Basit `TrueType` ve `Type1` fontlar için PDF `Encoding` ve `Differences` verisini kullanan `charcode -> glyph -> GID` çözümleme desteği eklendi.
- `fonttools` proje bağımlılıklarına eklendi.

### İyileştirmeler

- `find_fixes` akışı artık önce fontun kendi verisinden gelen daha güvenilir Unicode adaylarını değerlendiriyor.
- Aynı glyph için birden fazla Unicode bulunduğunda harfleri ve semantik olarak daha anlamlı kod noktalarını tercih eden seçim kuralı eklendi.
- Web ve CLI akışları font nesnesini CMap patch motoruna iletecek şekilde genişletildi.
- Türkçe karakter düzeltmeleri artık yalnızca çevresel heuristiklere değil, desteklenen font tiplerinde doğrudan font verisine de dayanabiliyor.

### Dokümantasyon

- `README.md` font-cmap tabanlı yeni onarım mantığını ve desteklenen font yollarını açıklayacak şekilde güncellendi.

### Doğrulama

- `python3 -m unittest tests/test_cmap_engine.py`
- `python3 -m py_compile app.py cmap_engine.py pdf_tr_fix.py`

## v3.0 - 2026-03-10

Bu sürüm CMap onarım motorunu daha dayanıklı hale getirir ve web akışındaki çift upload maliyetini kaldırır. Boşluklu ve array tabanlı CMap tanımları daha doğru işlenir; paylaşılan `ToUnicode` akışları yerinde güncellenir; web arayüzü PDF'i tek istekte analiz edip onarır.

### Eklenenler

- Ortak CMap işleme mantığını taşıyan yeni `cmap_engine.py` modülü eklendi.
- Web tarafına tek-upload iş akışı için `POST /process` endpoint'i eklendi.
- Geçici onarılmış dosyaların indirilmesi için `GET /download/<token>` endpoint'i eklendi.
- Geçici çıktı dosyaları için süreye bağlı temizleme akışı ve token tabanlı dosya saklama mekanizması eklendi.
- CMap motoru için whitespace, array-format, bozuk blok ve patch davranışlarını kapsayan yeni testler eklendi.

### Güvenlik Düzeltmeleri

- `beginbfrange ... endbfrange` ve `beginbfchar ... endbfchar` blokları artık regex ile tüm metin üzerinde geri izleme yapan desenlerle değil, deterministik blok taraması ile ayrıştırılıyor.
- Bozuk veya kapanmayan CMap bloklarında gereksiz CPU tüketimine yol açabilecek regex tarama davranışı sınırlandırıldı.
- İndirme tokeni doğrulaması ve güvenlileştirilmiş dosya adı akışı ile geçici dosya erişimi daha sıkı hale getirildi.
- Paylaşımlı `ToUnicode` stream referansları koparılmadan doğrudan stream üzerine yazılarak aynı nesneyi kullanan fontlarda tutarsızlık riski kaldırıldı.

### İyileştirmeler

- `beginbfrange` parse mantığı artık etiketler arası boşlukları ve satır sonlarını tolere ediyor.
- `beginbfrange` içindeki array formatı (`[ <...> <...> ]`) desteklenir hale getirildi.
- Patch motoru artık yalnızca dar bir regex kalıbına değil, hem `bfchar` hem `bfrange` bloklarına uygulanıyor.
- Tek bir CID düzeltmesi geniş bir range içinde yer alıyorsa ilgili kayıt array biçimine çevrilerek kısmi patch yapılabiliyor.
- Web arayüzü artık aynı PDF'i önce analiz sonra onarım için ikinci kez upload etmiyor.
- Sonuç ekranı tek işlemde gelen analiz ve onarım verisi ile dolduruluyor; indirme bağlantısı geçici sunucu artefact'ına bağlanıyor.
- Font keşfi inherited resources, form XObject kaynakları ve obje taraması üzerinden daha geniş kapsamlı hale getirildi.
- CLI ve web giriş noktaları aynı CMap motorunu kullanacak şekilde sadeleştirildi.

### Uyumluluk

- Mevcut istemciler bozulmasın diye `POST /analyze` ve `POST /fix` endpoint'leri korunmaya devam ediyor.

### Dokümantasyon

- `README.md` web API özeti tek-upload `POST /process` akışını ve geçici indirme endpoint'ini açıklayacak şekilde güncellendi.

### Doğrulama

- `python3 -m unittest discover -s tests`
- `python3 -m py_compile app.py cmap_engine.py pdf_tr_fix.py tests/test_cmap_engine.py`

## v2.4.1 - 2026-03-10

Bu patch sürüm Render dağıtım hatasını düzeltir. Production başlangıç komutlarında sık kullanılan `gunicorn` artık proje bağımlılıkları arasında yer alır.

### Düzeltmeler

- `requirements.txt` dosyasına `gunicorn` eklendi.
- Render ve benzeri platformlarda `gunicorn app:app` başlangıç komutunun `127 command not found` ile düşmesi engellendi.

### Doğrulama

- `python3 -m py_compile app.py pdf_tr_fix.py`
- Temiz sanal ortamda `pip install -r requirements.txt`
- `gunicorn app:app` açılış testi

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
