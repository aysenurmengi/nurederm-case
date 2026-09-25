"""Güvenlik ve iş kuralları testleri; ağ bağlantısı gerektirmez."""

from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import main


def message(text="12 numaralı siparişim nerede?", customer=7):
    return {"id": 1, "kanal": "whatsapp", "musteri_id": customer, "mesaj": text}


def cart(owner=7):
    return {"id": 12, "userId": owner,
            "products": [{"title": "TEST_GIZLI_URUN_9X", "quantity": 2}], "total": 918273.46}


class BusinessRulesTests(unittest.TestCase):
    def test_supplied_messages_have_expected_topics(self):
        messages = main.load_messages(main.BASE_DIR / "mesajlar.json")
        expected = ["siparis-durumu"] * 3 + ["istenmeyen-etki", "iade-sikayet",
            "siparis-durumu", "diger", "siparis-durumu", "urun-sorusu", "fiyat",
            "urun-sorusu", "diger", "urun-sorusu", "fiyat", "urun-sorusu"]
        self.assertEqual([main.classify(main.normalize(m["mesaj"])) for m in messages], expected)

    def test_order_numbers_use_context(self):
        cases = {
            "12 numaralı siparişim nerede?": 12,
            "Hi, where is my order #3?": 3,
            "200 ml krem 250 TL mi? Bir de 4 numaralı siparişim nerede?": 4,
            "Sipariş numaram: 12": 12,
            "Sipariş no 12": 12,
            "Siparişim #12, 12 numaralı sipariş": 12,
            "Siparişim ne zaman gelir, 200 ml krem aldım": None,
            "Sipariş #12 ve #13 nerede?": None,
            "Sipariş #0 nerede?": None,
            "Sipariş #9999999999999999 nerede?": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(main.extract_order_id(main.normalize(text)), expected)

    def test_owner_match_includes_titles_and_total(self):
        fetch = Mock(return_value=cart())
        record = main.process_message(message(), fetch)
        fetch.assert_called_once_with(12)
        self.assertFalse(record["devret"])
        self.assertIn("TEST_GIZLI_URUN_9X", record["cevap_taslagi"])
        self.assertIn("918273.46", record["cevap_taslagi"])
        self.assertNotIn("TL", record["cevap_taslagi"])

    def test_wrong_owner_leaks_nothing_in_any_output_or_logs(self):
        captured = io.StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            record = main.process_message(message(), Mock(return_value=cart(owner=87654321)))
            with tempfile.TemporaryDirectory() as folder:
                main.write_outputs([record], Path(folder))
                artifacts = "".join(p.read_text(encoding="utf-8") for p in Path(folder).iterdir())
        self.assertTrue(record["devret"])
        for secret in ("TEST_GIZLI_URUN_9X", "918273", "87654321"):
            self.assertNotIn(secret, artifacts + captured.getvalue())

    def test_missing_or_invalid_owner_never_discloses(self):
        for owner in (None, "7", True, 0, -7):
            with self.subTest(owner=owner):
                record = main.process_message(message(), Mock(return_value=cart(owner)))
                self.assertTrue(record["devret"])
                self.assertNotIn("TEST_GIZLI_URUN_9X", json.dumps(record))

    def test_wrong_cart_id_or_invalid_details_are_withheld(self):
        variations = [None, [], {**cart(), "id": 13}, {**cart(), "products": []},
            {**cart(), "products": [{"title": None}]}, {**cart(), "total": "123"},
            {**cart(), "total": float("nan")}, {**cart(), "total": -1},
            {**cart(), "total": True}]
        for payload in variations:
            with self.subTest(payload=payload):
                record = main.process_message(message(), Mock(return_value=payload))
                self.assertTrue(record["devret"])
                self.assertNotIn("TEST_GIZLI_URUN_9X", json.dumps(record))

    def test_not_found_does_not_transfer(self):
        record = main.process_message(message(), Mock(side_effect=main.CartNotFound))
        self.assertFalse(record["devret"])
        self.assertIn("kontrol", record["cevap_taslagi"])

    def test_api_failure_transfers(self):
        record = main.process_message(message(), Mock(side_effect=main.ApiProblem))
        self.assertTrue(record["devret"])
        self.assertNotIn("bulunamadı", record["cevap_taslagi"])

    def test_ambiguous_or_missing_number_does_not_call_api(self):
        for text in ("Siparişim nerede?", "Sipariş #12 ve #13 nerede?"):
            fetch = Mock()
            record = main.process_message(message(text), fetch)
            fetch.assert_not_called()
            self.assertTrue(record["devret"])

    def test_sensitive_layer_overrides_any_response_path(self):
        cases = (
            "Serum yüzümü yaktı. Hangi ürünü önerirsiniz?",
            "12 numaralı siparişim nerede? Ürün yan etki yaptı.",
            "Serum yüzümü yaktı, kızardı. Hangi ürünü önerirsiniz?",
            "Kutu ezik geldi, iade etmek istiyorum.",
            "12 numaralı siparişim nerede? Krem yüzümü yaktı ve kızardı, ne kullanayım?",
            "Sipariş #12 nerede? Ürünü iade etmek istiyorum. Fiyatı nedir?",
            "Sipariş #12 nerede? Yanlış ürün geldi, şikayetçiyim.",
        )
        for text in cases:
            with self.subTest(text=text):
                fetch = Mock()
                record = main.process_message(message(text), fetch)
                self.assertTrue(record["devret"])
                self.assertEqual(record["cevap_taslagi"],
                    "Talebinizi incelemesi için müşteri temsilcisine yönlendiriyorum.")
                fetch.assert_not_called()
                if "sipariş" in text.lower():
                    self.assertEqual(record["konu"], "siparis-durumu")

    def test_price_plus_order_prefers_order(self):
        record = main.process_message(message("Krem ne kadar? 12 numaralı siparişim nerede?"), Mock(return_value=cart()))
        self.assertEqual(record["konu"], "siparis-durumu")
        self.assertIn("TEST_GIZLI_URUN_9X", record["cevap_taslagi"])

    def test_missing_product_data_does_not_transfer(self):
        for text, topic in (("Serumunuz var mı?", "urun-sorusu"), ("Krem ne kadar?", "fiyat")):
            fetch = Mock()
            record = main.process_message(message(text), fetch)
            self.assertEqual(record["konu"], topic)
            self.assertFalse(record["devret"])
            self.assertIn("erişimim", record["cevap_taslagi"])
            fetch.assert_not_called()

    def test_english_order_reply(self):
        record = main.process_message(message("Hi, where is my order #12?"), Mock(return_value=cart()))
        self.assertIn("Your order contains:", record["cevap_taslagi"])

    def test_spam_has_no_reply(self):
        record = main.process_message(message("Takipçi ister misiniz? bit.ly/deneme"))
        self.assertEqual(record["konu"], "diger")
        self.assertEqual(record["cevap_taslagi"], "")
        self.assertFalse(record["devret"])

    def test_schema_counts_and_summary(self):
        messages = main.load_messages(main.BASE_DIR / "mesajlar.json")
        records = [main.process_message(m, Mock(side_effect=main.CartNotFound)) for m in messages]
        self.assertEqual([r["id"] for r in records], [m["id"] for m in messages])
        self.assertEqual(len(records), 15)
        for record in records:
            self.assertEqual(set(record), {"id", "konu", "devret", "cevap_taslagi", "not"})
            self.assertIn(record["konu"], main.TOPICS)
            self.assertIs(type(record["devret"]), bool)
        html = main.summary_html(records)
        self.assertIn("<strong>15</strong>", html)
        self.assertIn("<strong>2</strong>", html)
        for topic, count in Counter(r["konu"] for r in records).items():
            self.assertIn(f"{topic}</th><td>{count}</td>", html)


class HttpTests(unittest.TestCase):
    @patch("main.time.sleep")
    @patch("main.urlopen")
    def test_transient_error_retried_then_succeeds(self, open_url, sleep):
        open_url.side_effect = [URLError("network"), io.BytesIO(json.dumps(cart()).encode())]
        self.assertEqual(main.fetch_cart(12), cart())
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(open_url.call_args.args[0].full_url, "https://dummyjson.com/carts/12")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 10)

    @patch("main.time.sleep")
    @patch("main.urlopen", side_effect=TimeoutError)
    def test_timeout_is_bounded(self, open_url, sleep):
        with self.assertRaises(main.ApiProblem):
            main.fetch_cart(12)
        self.assertEqual(open_url.call_count, 2)

    def test_real_not_found_distinguished_from_gateway_404(self):
        for body, expected in ((b'{"message":"Cart with id \'12\' not found"}', main.CartNotFound),
            (b"<html>Not Found</html>", main.ApiProblem),
            (b'{"message":"Cart with id \'99\' not found"}', main.ApiProblem)):
            with self.subTest(body=body):
                error = HTTPError("https://dummyjson.com/carts/12", 404, "Not found", {}, io.BytesIO(body))
                with patch("main.urlopen", side_effect=error) as open_url:
                    with self.assertRaises(expected):
                        main.fetch_cart(12)
                    self.assertEqual(open_url.call_count, 1)

    def test_malformed_success_response_is_api_problem(self):
        for body in (b"not json", b"[]"):
            with patch("main.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(main.ApiProblem):
                    main.fetch_cart(12)

    def test_not_found_body_with_success_status(self):
        body = b'{"message":"Cart with id \'12\' not found"}'
        with patch("main.urlopen", return_value=io.BytesIO(body)):
            with self.assertRaises(main.CartNotFound):
                main.fetch_cart(12)

    @patch("main.time.sleep")
    def test_server_errors_retry_but_permission_errors_do_not(self, sleep):
        for status, attempts in ((500, 2), (429, 2), (403, 1)):
            with self.subTest(status=status):
                errors = [HTTPError("https://dummyjson.com/carts/12", status, "Error", {}, io.BytesIO())
                          for _ in range(attempts)]
                with patch("main.urlopen", side_effect=errors) as open_url:
                    with self.assertRaises(main.ApiProblem):
                        main.fetch_cart(12)
                    self.assertEqual(open_url.call_count, attempts)


class InputTests(unittest.TestCase):
    def test_invalid_inputs_are_rejected(self):
        cases = ("not json", "{}", "[null]", json.dumps([message(), message()]),
            json.dumps([{**message(), "musteri_id": True}]),
            json.dumps([{**message(), "mesaj": " "}]),
            json.dumps([{**message(), "kanal": None}]))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            for content in cases:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        main.load_messages(path)

    def test_utf8_bom_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            path.write_text(json.dumps([message()], ensure_ascii=False), encoding="utf-8-sig")
            self.assertEqual(main.load_messages(path), [message()])


if __name__ == "__main__":
    unittest.main()
