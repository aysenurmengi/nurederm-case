# Bölüm A — Müşteri mesajı otomasyonu

15 müşteri mesajını tek bir konuya ayırır, güvenli cevap taslakları üretir ve
temsilciye devredilecek talepleri işaretler. Python standart kütüphanesi kullanılır;
framework, ek paket, LLM veya API anahtarı gerekmez. Python 3.13.2 ile doğrulandı.

## Çalıştırma

Proje kökünde:

```powershell
python A-mesaj-otomasyonu/main.py
python -m unittest discover -s A-mesaj-otomasyonu -v
```

Windows'ta `python` komutu yoksa `py` kullanılabilir. Uygulama internet bağlantısı
ister; testler ağ bağlantısı kullanmaz. Girdi ve çıktı varsayılan olarak kodun
yanındaki klasördedir; komut başka bir çalışma dizininden de çağrılabilir.

İsteğe bağlı farklı yollar:

```powershell
python A-mesaj-otomasyonu/main.py --input A-mesaj-otomasyonu/mesajlar.json --output-dir A-mesaj-otomasyonu
```

Çıktılar her çalıştırmada yenilenir:

- `A-mesaj-otomasyonu/talepler.json`: her mesaj için tam olarak
  `{ id, konu, devret, cevap_taslagi, not }`.
- `A-mesaj-otomasyonu/ozet.html`: altı konu sayısı, toplam mesaj ve devredilen mesaj
  sayısını gösteren tek sayfalık özet; tarayıcıda doğrudan açılır.

Yalnızca taslak üretilir; WhatsApp/Instagram'a mesaj gönderilmez. `devret: true`
temsilci iş listesi işaretidir; gerçek bir destek sistemine aktarım yapılmaz.

## Düzeltilmiş plan ve uygulanan kurallar

1. UTF-8 girdiyi oku; alanları, türleri ve benzersiz mesaj kimliklerini doğrula.
2. Her mesaja tek konu ata. Öncelik:
   `siparis-durumu → istenmeyen-etki → iade-sikayet → fiyat → urun-sorusu → diger`.
3. Konudan bağımsız hassasiyet kontrolü uygula. İstenmeyen etki veya iade/şikayet
   tespit edilen mesaj her durumda devredilir; cevap yalnızca temsilciye
   yönlendirmedir. Sipariş de içeren hassas bir mesajın konusu `siparis-durumu`
   olabilir, ancak güvenlik katmanı normal cevap üretimini durdurur. Böyle bir
   mesajda API çağrısı yapılmaz, sipariş ayrıntısı eklenmez ve ürün önerilmez.
4. Diğer sipariş mesajlarında numarayı metindeki sipariş bağlamından çıkar ve
   `GET https://dummyjson.com/carts/{id}` çağrısı yap. Hacim/fiyat gibi sayıları
   kullanma. Eksik, geçersiz veya birden çok belirsiz numarada temsilciye devret.
5. API'deki sepet kimliğini ve `userId` alanını doğrula; `userId` ile girdideki
   `musteri_id` eşleşmeden ürünleri veya tutarı cevap üretiminde kullanma.
6. Sahiplik uyuşmazlığında kesinlikle devret. Ürünler, toplam ve gerçek sipariş
   sahibinin kimliği cevap, `not`, özet veya loglara yazılmaz. API gövdesi saklanmaz.
7. Sahiplik eşleşirse ürün adları ve `total` kullanılır; `discountedTotal` kullanılmaz.
8. API gerçekten ilgili sipariş için `Cart with id '...' not found` döndürürse
   numaranın kontrol edilmesini iste; `devret: false` bırak. Ağ geçidinin genel
   404 sayfası bu durumla karıştırılmaz.
9. Ağ, zaman aşımı, HTTP veya veri biçimi sorunlarında güvenli uyarı ve
   `devret: true` üret. Her istek 10 saniyelik zaman aşımıyla sınırlıdır;
   geçici ağ hataları, HTTP 429 ve 5xx için en fazla iki deneme yapılır.
10. `urun-sorusu` ve `fiyat` için doğrulanmış veri yoksa eksik bilgiyi açıkça
    belirt ve güvenli bir açıklama iste. Yalnızca veri eksikliği nedeniyle
    otomatik devir yapılmaz; fiyat, stok, içerik veya indirim kodu uydurulmaz.
11. Talepleri ve aynı kayıtlardan hesaplanan özeti UTF-8 olarak yaz; sonuçları
    gerçek API çalıştırması ve güvenlik testleriyle kontrol et.

Bozuk girdi veya dosya yazma hatasında komut açıklayıcı hata ve çıkış kodu 1 verir.
Sipariş API'sinin başarısızlığı diğer mesajları durdurmaz; durum ilgili kaydın
`not` alanında görünür. İş listesi başarıyla yazılmışsa çıkış kodu 0'dır; bu kod
bütün sipariş sorgularının başarılı olduğu anlamına gelmez.

## Kontrol sonuçları

25 Eylül 2026, 16:43:08 (+03:00) canlı çalıştırmasında:

| Konu | Sayı |
|---|---:|
| urun-sorusu | 4 |
| fiyat | 2 |
| siparis-durumu | 5 |
| iade-sikayet | 1 |
| istenmeyen-etki | 1 |
| diger | 2 |
| **Toplam** | **15** |

**Devredilen: 3 mesaj (1, 4, 5).**

- Mesaj 1: sahiplik uyuşmazlığı; sipariş ayrıntıları paylaşılmadı.
- Mesaj 2, 6, 8: sahiplik doğrulandı; ürün adları ve toplam taslakta yer aldı.
- Mesaj 3: sipariş gerçekten bulunamadı; numaranın kontrolü istendi, devir yapılmadı.
- Mesaj 4 ve 5: yalnızca temsilciye yönlendirme üretildi.
- Ürün/fiyat soruları veri eksikliği nedeniyle devredilmedi.
- JSON kayıtları ile HTML konu sayıları ve devir sayısı karşılaştırıldı.
- **23 otomatik test geçti.** Testler, bu veri setinin konularını, hassas içerik ile
  siparişin birleşmesini, fiyat + sipariş önceliğini, İngilizce mesajı, numara
  çıkarımını, sahiplik uyuşmazlığını, geçersiz sahiplik/veri alanlarını, gerçek
  404 ayrımını, zaman aşımını, yeniden denemeyi ve bozuk girdiyi kapsar.
- Sızıntı testinde başka müşteriye ait ayırt edici ürün adı, toplam ve sahip
  kimliğinin üretilen JSON, HTML, standart çıktı ve hata çıktısında bulunmadığı
  doğrulanır. Bu kontrol yalnızca cevap taslağıyla sınırlı değildir.

Canlı API verileri değişirse sahiplik sonuçları ve devredilen mesaj sayısı da
değişebilir; yukarıdaki sayılar belirtilen çalıştırmaya aittir.

## Varsayımlar ve sınırlar

- `musteri_id`, bu görev için güvenilir müşteri kimliği kabul edilir. Gerçek
  WhatsApp/Instagram kimlik doğrulaması bu araçta uygulanmaz.
- Sınıflandırma Türkçe ve sınırlı İngilizce kurallarla yapılır. Mesaj kimliklerine
  özel cevap yoktur. Kurallar serbest dilin bütün varyasyonlarını, olumsuzlamayı,
  yazım hatalarını veya örtük şikayetleri eksiksiz anlamaz; bu bir üretim ortamı
  için genel amaçlı dil/safety sistemi değildir.
- Genel kargo firması sorusu (mesaj 12), belirli bir sipariş sorgusu olmadığı için
  `diger` kabul edilir. Takipçi reklamı (mesaj 7) yanıtsız bırakılır, devredilmez
  ve bağlantısı açılmaz. İngilizce olarak algılanan mesajlara İngilizce, Türkçe
  mesajlara Türkçe cevap taslağı üretilir; API'deki ürün adları değiştirilmez.
- DummyJSON sepeti görev gereği sipariş kabul edilir. API'de kargo durumu, teslim
  tarihi veya para birimi verilmediğinden bunlar uydurulmaz. Bu veri eksikliklerine
  ilişkin teknik açıklamalar müşteri cevaplarına eklenmez. Genel mağaza test
  verisindeki kozmetik dışı ürün adları, sahibine aitse olduğu gibi kullanılır.
- Ürün arama bonusu uygulanmadı; ürün ve fiyat yanıtları doğrulanmış katalog
  verisine sahip olmadığını açıkça belirtir.
- Bölüm B, depo yayınlama ve e-posta gönderimi mevcut kapsamda değildir.
- `promptlar/A-codex.md` oluşturulmadı veya yeniden yazılmadı. Kullanıcı gerçek
  prompt geçmişini birebir kendisi ekleyecek; bu teslim parçası kullanıcıya aittir.

## Çalışma kaydı

- İlk kod dosyasının oluşturulması: 25 Eylül 2026, 16:37:49 (+03:00).
  Bu dosya zamanı olup planlama başlangıcı değildir; planlama başlangıcı ayrıca kaydedilmedi.
- Son canlı çıktı: 25 Eylül 2026, 16:43:08 (+03:00); ardından 23 test yeniden geçti.
- İlk test denemesinde sandbox'ın geçici dizin izinleri dosya testlerini engelledi;
  izinli tekrar çalıştırmada testler geçti.
- İlk API denemelerinde HTTP 403 alındı. İsteklere uygulamayı tanıtan
  `User-Agent: NuredermCase/1.0` eklendikten sonra canlı sorgular başarılı oldu.
  TLS doğrulaması kapatılmadı, sahte API çıktıları teslim verisine konulmadı.

API başvurusu: https://dummyjson.com/docs/carts
