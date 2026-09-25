# Bölüm B — n8n Otomasyon Akışı Açıklaması

## Amaç

Bu workflow, Webscraper.io test sitesindeki laptop ürünlerini günlük olarak tarar, ürün bilgilerini çıkarır, geçmiş fiyatlarla karşılaştırır ve yeni ürün veya fiyat değişikliği tespit edildiğinde e-posta bildirimi üretir.

Kaynak site:

https://webscraper.io/test-sites/e-commerce/static/computers/laptops

---

## Başlangıç Olarak Kullanılan n8n Şablonu

Başlangıç noktası olarak aşağıdaki n8n workflow şablonunu kullandım:

**Competitor price monitoring with web scraping, Google Sheets & Discord alerts**

https://n8n.io/workflows/6179-competitor-price-monitoring-with-web-scraping-google-sheets-and-discord-alerts/

Bu şablonu birebir kullanmak yerine case gereksinimlerine göre sadeleştirip değiştirdim.

Şablondan temel olarak şu fikirleri korudum:

- zamanlanmış tetikleyici
- HTTP Request ile web sayfası çekme
- HTML içinden fiyat bilgisi çıkarma
- fiyatı sayısal değere dönüştürme
- Google Sheets üzerinde geçmiş veri tutma
- fiyat değişikliğini kontrol etme
- değişiklik olduğunda bildirim gönderme

Case gereksinimlerine uymayan mevcut Discord ve checked-row mantığını kaldırdım.

---

## Workflow Akışı

### 1. Schedule Trigger

Workflow her gün bir kez çalışacak şekilde `Schedule Trigger` ile başlar.

Bu sayede fiyat kontrolü manuel olarak başlatılmadan günlük olarak tekrar edebilir.

---

### 2. Generate Page URLs

Kaynak site `?page=N` ile sayfalıdır.

Sadece ilk sayfayı kontrol etmek yerine bir Code node kullanarak sayfa URL'leri oluşturulur.

Örnek:

```text
https://webscraper.io/test-sites/e-commerce/static/computers/laptops?page=1
https://webscraper.io/test-sites/e-commerce/static/computers/laptops?page=2
...
```

Workflow mevcut test sitesi için yeterli olacak şekilde 1–20 arasındaki sayfaları üretir.

Her URL ayrı bir n8n item'ı olarak sonraki adıma gönderilir.

---

### 3. HTTP Request to Product Page

Oluşturulan her sayfa URL'si HTTP Request node ile çekilir.

HTML yanıtı bir sonraki scraping adımına gönderilir.

HTTP isteğinin başarısız olması durumunda hata çıktısı normal akıştan ayrılarak hata bildirim koluna yönlendirilir.

---

### 4. Price Extract From Page

HTML extraction node ile her sayfadaki laptoplardan şu bilgiler çıkarılır:

- ürün adı
- fiyat
- yorum sayısı
- ürün linki

Kullanılan alanlar:

```text
name
price
reviews
link
```

Bir sayfada birden fazla ürün olduğu için değerler array olarak alınır.

---

### 5. Normalize Products

Scraping sonucunda gelen array'ler Code node ile tek tek ürün kayıtlarına dönüştürülür.

Her ürün aşağıdaki yapıya çevrilir:

```json
{
  "name": "Packard 255 G2",
  "price": 416.99,
  "reviews": 2,
  "link": "https://webscraper.io/test-sites/e-commerce/static/product/31"
}
```

Bu adımda:

- fiyatın başındaki `$` kaldırılır
- fiyat `Number` tipine çevrilir
- yorum sayısı numeric değere çevrilir
- relative ürün linkleri tam URL haline getirilir

Bu sayede fiyatlar string yerine sayısal olarak saklanır ve karşılaştırılabilir.

---

## Google Sheets Yapısı

Veri saklama yöntemi olarak Google Sheets kullandım.

Tek bir Google Sheets dokümanı içinde iki ayrı sheet bulunmaktadır.

### `price_history`

Her çalışmadaki tüm ürün snapshot'larını tutar.

Kolonlar:

```text
timestamp
name
price
reviews
link
```

### `latest_prices`

Her ürün için en son bilinen bilgiyi tutar.

Kolonlar:

```text
name
price
reviews
link
updated_at
```

Ürünleri eşleştirmek için unique key olarak ürün linki kullanılır.

---

### 6. Read Latest Prices

`latest_prices` sheet'i okunur.

Bu node sadece bir kez çalışacak şekilde ayarlanmıştır; her ürün için Google Sheets'in tekrar tekrar okunması önlenmiştir.

İlk çalışmada tablo boş olabileceği için workflow'un yine devam edebilmesi sağlanmıştır.

---

### 7. Compare Products

Mevcut scrape edilen ürünler ile `latest_prices` kayıtları ürün linki üzerinden karşılaştırılır.

Her ürüne üç durumdan biri atanır:

```text
new
price_changed
unchanged
```

Kurallar:

- ürün linki daha önce yoksa → `new`
- ürün daha önce varsa ve fiyat farklıysa → `price_changed`
- fiyat aynıysa → `unchanged`

Karşılaştırma sonucuna ayrıca:

```text
old_price
timestamp
```

alanları eklenir.

---

### 8. Append Price History

Her çalışmadaki ürün sonuçları timestamp ile birlikte `price_history` sheet'ine eklenir.

Bu tablo geçmiş fiyatların korunmasını sağlar.

---

### 9. Update Latest Prices

Her ürünün en güncel hali `latest_prices` sheet'ine yazılır.

Ürün linki eşleşme alanı olarak kullanılır.

Aynı ürün zaten varsa satır güncellenir, yoksa yeni kayıt eklenir.

---

### 10. New or Price Changed?

IF node ile ürünün durumu kontrol edilir.

Koşul:

```text
status != unchanged
```

Bu nedenle yalnızca:

```text
new
price_changed
```

durumundaki ürünler bildirim koluna geçer.

Değişmeyen ürünler için bildirim üretilmez.

---

### 11. Price Change Email

Yeni ürün veya fiyat değişikliği tespit edilirse e-posta bildirimi hazırlanır.

Bildirim içeriğinde şu bilgiler yer alır:

```text
Product
Status
Old price
New price
Reviews
Link
```

Başlangıç template'inde Discord kullanılıyordu. Case için bu node kaldırılarak Email node ile değiştirildi.

Email node'u için gerçek SMTP credential kurulmadı ve placeholder olarak bırakıldı. Case brief'inde workflow'un canlı çalıştırılması veya credential kurulması zorunlu olmadığı için bu tercih yapıldı.

---

## Hata Yönetimi

Workflow'un sessizce başarılı şekilde bitmemesi için iki hata durumu ele alındı.

### HTTP / Site Hatası

Kaynak siteye yapılan HTTP isteği başarısız olursa normal akış yerine hata output'u kullanılır ve `Scraping Error Email` node'una yönlendirilir.

### Ürün Bulunamaması

Scraping sonrasında toplam ürün sayısı kontrol edilir.

Eğer hiçbir ürün çıkarılamazsa:

```text
scrapingOk = false
```

olur ve workflow hata e-postası koluna geçer.

Bu sayede HTML selector değişmesi veya siteden boş sonuç gelmesi sessizce başarılı kabul edilmez.

---

## Başlangıç Şablonunda Yaptığım Değişiklikler

Orijinal şablondaki aşağıdaki yapı kaldırıldı veya değiştirildi:

- Google Sheets üzerinden "unchecked row" alma mantığı kaldırıldı.
- Tek ürün sayfası kontrolü yerine tüm liste sayfalarını gezen pagination yapısı eklendi.
- Tek fiyat extraction yerine tüm laptopların adı, fiyatı, yorum sayısı ve linki çıkarıldı.
- Fiyat numeric değere dönüştürüldü.
- Ürünlerin önceki çalışmayla karşılaştırılması için `latest_prices` yapısı eklendi.
- Yeni ürün tespiti eklendi.
- Fiyat geçmişi için ayrı `price_history` sheet'i eklendi.
- Discord bildirim node'ları kaldırılarak Email node kullanıldı.
- Site hatası ve sıfır ürün sonucu için ayrı hata dalı eklendi.
- Template'teki checked/status reset mantığı kaldırıldı.

---

## Çıktı

Teslim edilen dosyalar:

```text
B-n8n/
├── workflow.json
├── akis-aciklama.md
└── workflow-ekran-goruntusu.png
```

`workflow.json` n8n üzerinden export edilmiştir.

Workflow tasarımının ana amacı, case brief'inde istenen:

- günlük çalışma
- tüm sayfaları gezme
- ürün bilgilerini çıkarma
- fiyatı numeric tutma
- timestamp ile geçmiş kayıt
- önceki fiyatla karşılaştırma
- yeni ürün tespiti
- fiyat değişikliği bildirimi
- hata bildirimi

gereksinimlerini tek bir akışta karşılamaktır.
```