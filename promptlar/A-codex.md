Seninle bir çalışma yapacağız. Çalışma için gerekli olan veri dosyasını ve adımlarını ayrı bir dosya olarak sana ileteceğim. Ayrıca ben sana belirlediğim zorunlu gereksinimleri iletiyorum. Zorunlu gereksinimlere eksiksiz uymalısın. Bir uygulama planı çıkaralım daha sonra implentasyona geçeceğiz. 
Zorunlu gereksinimler; 
Her mesaja tam olarak bir konu ata:\
`urun-sorusu`, `fiyat`, `siparis-durumu`, `iade-sikayet`, `istenmeyen-etki`, `diger`

- `iade-sikayet` ve `istenmeyen-etki` için `devret: true` yap.
- Bu hassas konularda teşhis veya ürün önerisi üretme; yalnızca temsilciye yönlendir.
- `siparis-durumu` mesajlarında metinden sipariş numarasını çıkar ve `https://dummyjson.com/carts/{id}` endpointini kullan.
- API'den dönen `userId` ile mesajdaki `musteri_id` eşleşmiyorsa sipariş bilgisini kesinlikle cevapta gösterme; `devret: true` yap.
- Sipariş bulunamazsa düzgün ve güvenli bir hata/uyarı cevabı üret.
- Sipariş sahibi eşleşiyorsa ürün adlarını ve toplam tutarı cevap taslağına ekle.
- Bir mesaj birden fazla niyet içeriyorsa yine yalnızca tek konu seç. Sipariş durumu içeren mesajlarda `siparis-durumu`nu öncelikli değerlendir.
- Çıktı olarak:
  - `A-mesaj-otomasyonu/talepler.json`
  - konu bazında sayıları ve devredilen mesaj sayısını gösteren tek sayfalık bir özet oluştur.
- Kodu okunabilir, sade ve çalıştırılabilir tut.
- Gereksiz framework kullanma.
- Hata yönetimi ekle.
- Sonunda kodu çalıştırıp çıktıları kontrol et ve özellikle başka müşterinin sipariş bilgisinin sızmadığını doğrula.
- Yaptığın varsayımları ve varsa eksik kalan noktaları açıkça belirt.



Plan genel olarak uygun ama implementasyona geçmeden önce şu düzeltmeleri uygulamalısın: 1. urun-sorusu ve fiyat mesajlarını doğrulanmış ürün verisi olmadığı için otomatik devret:true yapma. briefte devret zorunlulupu hassas konular ve güvenlik/sahiplik problemleri için denmiş. veri yoksa güvenli bir cevap taslağı üretelim, bilgi uydurma. 2. hassas içerik tespitini konu önceleğinden ayrı bir güvenlik katmanı olarak ele al. bir mesaj istenmeyen etki veya iade/şikayet içeriyorsa, sipariş ifadesi de bulunsa hassasiyet göz ardı edilmesin. ayrıca fiyat + sipariş durumu içeren mesajlarda siparis-durumu öncelikli olabilir. 3.sipariş bulunamaması hakkında; -sipariş gerçekten not found ise kullanıcıya numarayı kontrol etmesini söyleyelim, devret:true yapmayalım gereksiz yere -api erişim/yanıt problemi varsa devret:true yapabilirsin. -sahiplik uyuşmazlığında kesinlikle devret:true ve hiçbir sipariş detayı sızmasın. 4. promptlar/A-codex.md içeriğini kendin yeniden yazma ya da özetleme. prompt geçmişini ben birebir ekleyeceğim. bunları plana uygula ve implementasyonuna geç.



cevap-taslagi dönerken (veri kaynağında para birimi belirtilmiyor) ve Kargo durumu ve teslim tarihi bilgisine bu kaynaktan ulaşılamıyor. bilgisini müşteriye dönmemelisin, profesyonel görünmüyor. onun dışındaki tüm bilgiler aynı kalsın. 


**Ayrıca Bölüm A'ya ait olan ReadMe yapay zeka aracı ile hazırlanmıştır.