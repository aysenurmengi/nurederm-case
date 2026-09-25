"""Bölüm A: standart kütüphaneyle müşteri mesajlarından cevap taslakları üretir."""

import argparse
from collections import Counter
from datetime import datetime
from html import escape
from http.client import HTTPException
import json
import math
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOPICS = (
    "urun-sorusu", "fiyat", "siparis-durumu",
    "iade-sikayet", "istenmeyen-etki", "diger",
)
BASE_DIR = Path(__file__).resolve().parent
API_URL = "https://dummyjson.com/carts/{}"


class CartNotFound(Exception):
    """API, istenen sepetin bulunmadığını açıkça bildirdi."""


class ApiProblem(Exception):
    """Sipariş verisi güvenilir biçimde alınamadı; ayrıntılar dışarı taşınmaz."""


def normalize(text):
    text = text.lower().replace("ı", "i")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def sensitive_reason(text):
    """Konu seçiminden bağımsız güvenlik katmanı; normalize metin alır."""
    if re.search(
        r"\b(kizar\w*|yanma\w*|yandi\w*|yaniyor\w*|yakti\w*|alerji\w*|kasinti\w*|"
        r"sisti\w*|sislik\w*|tahris\w*|dokuntu\w*|nefes\w*|"
        r"rash|burning|burned|swelling|allerg\w*|irritat\w*)\b|\byan etki\w*\b", text
    ):
        return "istenmeyen-etki"
    if re.search(
        r"\b(iade\w*|sikayet\w*|ezik\w*|kirik\w*|hasar\w*|bozuk\w*|"
        r"sizdir\w*|refund\w*|return\w*|complain\w*|damaged|broken)\b|"
        r"\b(yanlis|eksik) urun\b|\bmemnun degil", text
    ):
        return "iade-sikayet"
    return None


def is_order_status(text):
    if not re.search(r"\b(siparis\w*|order\w*)\b", text):
        return False
    return bool(re.search(
        r"\bsiparisim\w*\b|\bmy order\b|\b(durum\w*|nerede|ulasma\w*|"
        r"gelmedi|gecikti|where|status|arriv\w*|delayed)\b|"
        r"\bne zaman\b|#\s*\d+|\b\d+\s+numarali\s+siparis|"
        r"\b(?:siparis\w*|order)\s+(?:numar\w*|no\.?|number|id|[0-9]+)\b", text
    ))


def classify(text):
    if is_order_status(text):
        return "siparis-durumu"
    sensitive = sensitive_reason(text)
    if sensitive:
        return sensitive
    if re.search(r"\b(fiyat\w*|indirim\w*|price\w*|discount\w*)\b|ne kadar|how much", text):
        return "fiyat"
    if re.search(
        r"\b(urun\w*|serum\w*|krem\w*|tonik\w*|retinol\w*|cilt\w*|"
        r"icerik\w*|alkol\w*|product\w*|ingredient\w*)\b", text
    ):
        return "urun-sorusu"
    return "diger"


def extract_order_id(text):
    # Hacim/fiyat gibi bağlamsız sayıları sipariş numarası kabul etme.
    patterns = (
        r"(?<![\w#])#\s*([0-9]+)\b",
        r"\b([0-9]+)\s*(?:numarali|nolu|no'lu)\s+siparis\w*\b",
        r"\b(?:siparis\w*|order)\s*(?:(?:numar\w*|no\.?|number|id)\s*)?[:#-]?\s*([0-9]+)\b",
    )
    matches = {value for pattern in patterns for value in re.findall(pattern, text)}
    if not matches or any(len(value) > 10 for value in matches):
        return None
    numbers = {int(value) for value in matches}
    if len(numbers) != 1 or next(iter(numbers)) <= 0:
        return None
    return numbers.pop()


def is_not_found(payload, order_id):
    return (
        isinstance(payload, dict)
        and payload.get("message") == f"Cart with id '{order_id}' not found"
    )


def fetch_cart(order_id):
    """Yalnızca sabit API'ye GET; en fazla iki deneme, her birinde 10 sn timeout."""
    request = Request(API_URL.format(order_id), headers={
        "Accept": "application/json", "User-Agent": "NuredermCase/1.0",
    })
    for attempt in range(2):
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
            if is_not_found(payload, order_id):
                raise CartNotFound
            if not isinstance(payload, dict):
                raise ApiProblem
            return payload
        except HTTPError as error:
            # Bir proxy'nin HTML 404 sayfası, gerçek "sipariş yok" yanıtı değildir.
            with error:
                if error.code == 404:
                    try:
                        payload = json.load(error)
                    except (ValueError, OSError):
                        raise ApiProblem from None
                    if is_not_found(payload, order_id):
                        raise CartNotFound from None
                    raise ApiProblem from None
                retryable = error.code == 429 or 500 <= error.code <= 599
            if not retryable or attempt == 1:
                raise ApiProblem from None
        except (URLError, OSError, HTTPException):
            if attempt == 1:
                raise ApiProblem from None
        except ValueError:
            raise ApiProblem from None
        time.sleep(0.5)
    raise ApiProblem


def result(message_id, topic, transfer, reply, note):
    return {
        "id": message_id, "konu": topic, "devret": transfer,
        "cevap_taslagi": reply, "not": note,
    }


def process_message(message, fetch=fetch_cart):
    text = normalize(message["mesaj"])
    topic = classify(text)
    english = bool(re.search(r"\b(my order|where|hi|hello)\b", text))

    def output(transfer, tr, en, note):
        return result(message["id"], topic, transfer, en if english else tr, note)

    sensitive = sensitive_reason(text)
    if sensitive:
        # Sipariş/fiyat niyeti güvenlik katmanını geçersiz kılamaz.
        return output(
            True, "Talebinizi incelemesi için müşteri temsilcisine yönlendiriyorum.",
            "I am referring your request to a customer representative for review.",
            f"Hassas içerik: {sensitive}; yalnızca temsilciye yönlendirme.",
        )

    if topic == "siparis-durumu":
        order_id = extract_order_id(text)
        if order_id is None:
            return output(
                True, "Sipariş numaranızı netleştirmek için talebinizi müşteri temsilcisine yönlendiriyorum.",
                "I am referring your request to a representative to clarify your order number.",
                "Sipariş numarası eksik, geçersiz veya birden fazla; sorgu yapılmadı.",
            )
        try:
            cart = fetch(order_id)
        except CartNotFound:
            return output(
                False, "Bu numarayla sipariş bulunamadı. Lütfen sipariş numaranızı kontrol edip tekrar paylaşın.",
                "No order was found with this number. Please check your order number and send it again.",
                "API siparişin bulunamadığını doğruladı.",
            )
        except ApiProblem:
            return output(
                True, "Sipariş bilgilerinizi şu anda doğrulayamıyorum. Talebinizi müşteri temsilcisine yönlendiriyorum.",
                "I cannot verify your order information right now. I am referring your request to a representative.",
                "API erişim veya yanıt hatası; sipariş ayrıntısı paylaşılmadı.",
            )

        # Ürün ve tutar alanlarına bakmadan önce kaynak ve sahiplik doğrulaması.
        if (
            not isinstance(cart, dict) or type(cart.get("id")) is not int
            or cart["id"] != order_id or type(cart.get("userId")) is not int
            or cart["userId"] <= 0
        ):
            return output(
                True, "Sipariş bilgilerinizi doğrulayamıyorum. Talebinizi müşteri temsilcisine yönlendiriyorum.",
                "I cannot verify your order information. I am referring your request to a representative.",
                "API kimlik alanları geçersiz; sipariş ayrıntısı paylaşılmadı.",
            )
        if cart["userId"] != message["musteri_id"]:
            return output(
                True, "Bu siparişin hesabınıza ait olduğunu doğrulayamadım. Talebinizi müşteri temsilcisine yönlendiriyorum.",
                "I could not verify that this order belongs to your account. I am referring your request to a representative.",
                "Sipariş sahipliği eşleşmedi; sipariş ayrıntısı paylaşılmadı.",
            )

        products, total = cart.get("products"), cart.get("total")
        if (
            not isinstance(products, list) or not products
            or any(not isinstance(p, dict) or not isinstance(p.get("title"), str)
                   or not p["title"].strip() for p in products)
            or type(total) not in (int, float) or total < 0
            or not math.isfinite(total)
        ):
            return output(
                True, "Sipariş ayrıntılarını doğrulayamıyorum. Talebinizi müşteri temsilcisine yönlendiriyorum.",
                "I cannot verify the order details. I am referring your request to a representative.",
                "API ürün veya toplam alanları geçersiz; ayrıntılar paylaşılmadı.",
            )
        titles = ", ".join(p["title"].strip() for p in products)
        return output(
            False, f"Siparişinizdeki ürünler: {titles}. Toplam tutar: {total:.2f}.",
            f"Your order contains: {titles}. Total: {total:.2f}.",
            "Sahiplik doğrulandı; ürün adları ve total kullanıldı. Kargo bilgisi üretilmedi.",
        )

    if topic == "urun-sorusu":
        return output(
            False, "Doğrulanmış ürün bilgisine erişimim olmadığı için stok, içerik, kullanım uygunluğu veya marka politikası hakkında kesin bilgi veremiyorum. İlgilendiğiniz ürünün tam adını veya bağlantısını paylaşabilir misiniz?",
            "I do not have verified product information to confirm availability, ingredients, suitability or brand policy. Could you share the full product name or link?",
            "Doğrulanmış ürün verisi yok; bilgi veya öneri üretilmedi, otomatik devir yapılmadı.",
        )
    if topic == "fiyat":
        return output(
            False, "Doğrulanmış güncel fiyat ve kampanya bilgisine erişimim yok. Bu nedenle bir tutar veya indirim kodu paylaşamıyorum. İlgilendiğiniz ürünün tam adını veya bağlantısını paylaşabilir misiniz?",
            "I do not have verified current prices or promotions, so I cannot provide a price or discount code. Could you share the full product name or link?",
            "Doğrulanmış fiyat verisi yok; tutar veya kampanya uydurulmadı, otomatik devir yapılmadı.",
        )
    if re.search(r"takipci|follower|bit\.ly", text):
        return output(False, "", "", "İstenmeyen tanıtım mesajı; yanıt taslağı oluşturulmadı, bağlantı açılmadı.")
    if "kargo" in text:
        return output(
            False, "Kullanılan kargo firması hakkında doğrulanmış bilgim bulunmuyor. Siparişinize özel bilgi için sipariş numaranızı paylaşabilir misiniz?",
            "I do not have verified carrier information. Could you share your order number for an order-specific inquiry?",
            "Genel kargo politikası sorusu; belirli bir sipariş durumu sorgusu değil.",
        )
    return output(False, "Size yardımcı olabilmem için talebinizi biraz daha açıklayabilir misiniz?",
                  "Could you describe your request in a little more detail?", "Diğer konu; açıklama istendi.")


def load_messages(path):
    messages = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(messages, list):
        raise ValueError("Girdi bir JSON listesi olmalı.")
    seen = set()
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            raise ValueError(f"{index}. kayıt bir JSON nesnesi olmalı.")
        for field in ("id", "musteri_id"):
            if type(message.get(field)) is not int or message[field] <= 0:
                raise ValueError(f"{index}. kayıtta {field} pozitif tam sayı olmalı.")
        for field in ("kanal", "mesaj"):
            if not isinstance(message.get(field), str) or not message[field].strip():
                raise ValueError(f"{index}. kayıtta {field} boş olmayan metin olmalı.")
        if message["id"] in seen:
            raise ValueError(f"{index}. kayıtta tekrarlanan mesaj kimliği var.")
        seen.add(message["id"])
    return messages


def summary_html(requests):
    counts = Counter(item["konu"] for item in requests)
    transferred = sum(item["devret"] for item in requests)
    rows = "\n".join(
        f"<tr><th scope='row'>{escape(topic)}</th><td>{counts[topic]}</td></tr>"
        for topic in TOPICS
    )
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bölüm A — Mesaj özeti</title>
<style>
body {{ font: 16px/1.5 system-ui, sans-serif; color: #172b37; background: #f3f6f7; margin: 0; padding: 32px 16px; }}
main {{ max-width: 660px; margin: auto; padding: 28px; background: white; border: 1px solid #cbd6dc; border-radius: 12px; }}
h1 {{ margin: 0 0 8px; font-size: 26px; }}
.stats {{ display: flex; gap: 32px; flex-wrap: wrap; margin: 24px 0; }}
.stats strong {{ display: block; font-size: 30px; color: #126254; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 10px 4px; border-bottom: 1px solid #dce4e7; text-align: left; }}
td, thead th:last-child {{ text-align: right; }}
small {{ color: #4c606c; }}
@page {{ size: A4; margin: 15mm; }}
@media print {{ body {{ background: white; padding: 0; }} main {{ border: none; padding: 0; }} }}
</style></head><body><main>
<h1>Bölüm A · Mesaj otomasyonu</h1>
<small>Oluşturulma: {escape(timestamp)}</small>
<div class="stats"><div><strong>{len(requests)}</strong>Toplam mesaj</div>
<div><strong>{transferred}</strong>Temsilciye devredilen</div></div>
<table><thead><tr><th scope="col">Konu</th><th scope="col">Mesaj sayısı</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><small>Sayılar talepler.json kayıtlarından hesaplandı. Cevaplar taslaktır; müşterilere gönderilmemiştir.</small></p>
</main></body></html>
"""


def write_outputs(requests, directory):
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "talepler.json": json.dumps(requests, ensure_ascii=False, indent=2) + "\n",
        "ozet.html": summary_html(requests),
    }
    for name, content in outputs.items():
        target = directory / name
        temporary = directory / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE_DIR / "mesajlar.json")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR)
    args = parser.parse_args()
    try:
        messages = load_messages(args.input)
        requests = [process_message(message) for message in messages]
        write_outputs(requests, args.output_dir)
    except (OSError, ValueError) as error:
        # JSONDecodeError metni veri gövdesini içermez; ham mesaj/API içeriği basılmaz.
        print(f"Dosya/girdi hatası: {error}", file=sys.stderr)
        return 1
    print(f"{len(requests)} mesaj işlendi; {sum(r['devret'] for r in requests)} mesaj devredildi.")
    print("talepler.json ve ozet.html oluşturuldu. API sorunları varsa kayıtların not alanına işlendi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
