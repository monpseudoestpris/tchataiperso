import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.finance import (
    _fmt_num,
    _fmt_pct,
    build_eodhd_markdown,
    build_finance_markdown,
    clean_entity_candidate,
    detect_financial_entities,
    extract_ticker_from_url,
    fetch_and_parse_yahoo_finance,
    fetch_dual_financial_attachments,
    fetch_eodhd_historical_eod,
    fetch_eodhd_quote_data,
    fetch_eodhd_realtime,
    fetch_yahoo_chart,
    fetch_yahoo_financials_data,
    fetch_yahoo_quote_summary,
    get_financial_dashboard_data,
    is_eodhd_url,
    is_financial_url,
    is_yahoo_finance_url,
    process_message_finance_inquiries,
    query_variants,
    score_eodhd_search_item,
    search_eodhd_ticker,
    search_yahoo_ticker,
)
from app.web import fetch_and_parse_web_url


class TestYahooFinanceUrl(unittest.TestCase):
    def test_is_yahoo_finance_url(self):
        self.assertTrue(is_yahoo_finance_url("https://finance.yahoo.com/quote/AAPL"))
        self.assertTrue(is_yahoo_finance_url("https://fr.finance.yahoo.com/quote/MC.PA/"))
        self.assertTrue(is_yahoo_finance_url("http://query1.finance.yahoo.com/v8/finance/chart/AAPL"))
        self.assertFalse(is_yahoo_finance_url("https://example.com/finance"))
        self.assertFalse(is_yahoo_finance_url("https://google.com/search?q=yahoo+finance"))
        self.assertFalse(is_yahoo_finance_url("not a url"))

    def test_is_eodhd_url(self):
        self.assertTrue(is_eodhd_url("https://eodhd.com/financial-summary/STLA.US"))
        self.assertTrue(is_eodhd_url("https://eodhistoricaldata.com/financial-summary/MC.PA"))
        self.assertFalse(is_eodhd_url("https://google.com/"))
        self.assertTrue(is_financial_url("https://eodhd.com/financial-summary/AAPL.US"))
        self.assertTrue(is_financial_url("https://finance.yahoo.com/quote/AAPL"))

    def test_extract_ticker_from_url(self):
        self.assertEqual(extract_ticker_from_url("https://finance.yahoo.com/quote/AAPL"), "AAPL")
        self.assertEqual(extract_ticker_from_url("https://fr.finance.yahoo.com/quote/MC.PA?p=MC.PA"), "MC.PA")
        self.assertEqual(extract_ticker_from_url("https://finance.yahoo.com/quote/^FCHI/"), "^FCHI")
        self.assertEqual(extract_ticker_from_url("https://eodhd.com/financial-summary/STLA.US"), "STLA.US")
        self.assertIsNone(extract_ticker_from_url("https://finance.yahoo.com/news/some-article.html"))


class TestFinanceEntityDetection(unittest.TestCase):
    def test_clean_entity_candidate(self):
        self.assertEqual(clean_entity_candidate("l'action Apple"), ["Apple"])
        self.assertEqual(clean_entity_candidate("la société TotalEnergies aujourd'hui"), ["TotalEnergies"])
        self.assertEqual(clean_entity_candidate("Apple et de Tesla"), ["Apple", "Tesla"])
        self.assertEqual(clean_entity_candidate("LVMH vs Kering"), ["LVMH", "Kering"])

    def test_detect_financial_entities(self):
        self.assertEqual(
            detect_financial_entities("Quel est le cours de bourse d'Apple et de Tesla ?"),
            ["Apple", "Tesla"],
        )
        self.assertEqual(
            detect_financial_entities("Donne-moi les données financières de LVMH"),
            ["LVMH"],
        )
        self.assertEqual(
            detect_financial_entities("Action TotalEnergies"),
            ["TotalEnergies"],
        )
        self.assertEqual(
            detect_financial_entities("C'est quoi le cours du CAC 40 aujourd'hui ?"),
            ["CAC 40"],
        )
        self.assertEqual(
            detect_financial_entities("Infos sur l'entreprise Microsoft"),
            ["Microsoft"],
        )
        self.assertEqual(
            detect_financial_entities("Combien vaut l'action Nvidia en ce moment ?"),
            ["Nvidia"],
        )
        self.assertEqual(
            detect_financial_entities("@finance AIR.PA"),
            ["AIR.PA"],
        )
        self.assertEqual(
            detect_financial_entities("$TSLA vs $AAPL"),
            ["TSLA", "AAPL"],
        )
        self.assertEqual(
            detect_financial_entities("https://finance.yahoo.com/quote/MSFT"),
            ["MSFT"],
        )
        self.assertEqual(
            detect_financial_entities("analyse stellantis"),
            ["stellantis"],
        )
        self.assertEqual(
            detect_financial_entities("bilan tesla"),
            ["tesla"],
        )

    def test_detect_non_financial_queries(self):
        self.assertEqual(detect_financial_entities(""), [])
        self.assertEqual(detect_financial_entities("Raconte-moi une blague sur les grenouilles"), [])
        self.assertEqual(detect_financial_entities("Fais-moi un poème sur la mer"), [])
        self.assertEqual(detect_financial_entities("Comment faire des crêpes ?"), [])


class TestFinanceFormatters(unittest.TestCase):
    def test_fmt_num(self):
        self.assertEqual(_fmt_num(None), "N/A")
        self.assertEqual(_fmt_num(3.5e12, "USD"), "3.50 T USD")
        self.assertEqual(_fmt_num(2.5e9, "EUR"), "2.50 Mrd EUR")
        self.assertEqual(_fmt_num(1.2e6), "1.20 M")
        self.assertEqual(_fmt_num(1234.5), "1 234.50")
        self.assertEqual(_fmt_num({"fmt": "3.2T"}, "USD"), "3.2T USD")

    def test_fmt_pct(self):
        self.assertEqual(_fmt_pct(None), "N/A")
        self.assertEqual(_fmt_pct(0.045), "+4.50%")
        self.assertEqual(_fmt_pct(-0.021), "-2.10%")
        self.assertEqual(_fmt_pct({"fmt": "+3.40%"}), "+3.40%")


class TestFinanceMarkdownBuilder(unittest.TestCase):
    def test_build_finance_markdown(self):
        top_quote = {
            "symbol": "AAPL",
            "shortname": "Apple Inc.",
            "longname": "Apple Inc.",
            "exchDisp": "NASDAQ",
        }
        chart_data = {
            "meta": {
                "currency": "USD",
                "symbol": "AAPL",
                "regularMarketPrice": 345.0,
                "chartPreviousClose": 340.0,
                "regularMarketChangePercent": 1.47,
                "regularMarketDayLow": 342.0,
                "regularMarketDayHigh": 346.0,
                "fiftyTwoWeekLow": 240.0,
                "fiftyTwoWeekHigh": 350.0,
            },
            "timestamp": [1729500000, 1729600000],
            "indicators": {
                "quote": [
                    {
                        "open": [341.0, 342.0],
                        "high": [344.0, 346.0],
                        "low": [340.0, 341.0],
                        "close": [343.0, 345.0],
                        "volume": [30000000, 35000000],
                    }
                ]
            },
        }
        summary_data = {
            "price": {
                "shortName": "Apple Inc.",
                "longName": "Apple Inc.",
                "regularMarketPrice": {"raw": 345.0},
                "currency": "USD",
                "marketCap": {"raw": 5e12, "fmt": "5T"},
            },
            "financialData": {
                "totalRevenue": {"raw": 3.8e11, "fmt": "380B"},
                "revenueGrowth": {"raw": 0.05, "fmt": "5%"},
                "targetMeanPrice": {"raw": 380.0, "fmt": "380.00"},
                "recommendationKey": "buy",
                "numberOfAnalystOpinions": {"raw": 42},
            },
            "defaultKeyStatistics": {
                "trailingPE": {"raw": 35.0, "fmt": "35.00"},
                "pegRatio": {"raw": 2.5, "fmt": "2.50"},
            },
            "assetProfile": {
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "United States",
                "longBusinessSummary": "Apple designs and manufactures electronic devices.",
            },
        }

        title, markdown, meta = build_finance_markdown("AAPL", top_quote, chart_data, summary_data)
        self.assertIn("Apple Inc.", title)
        self.assertIn("AAPL", title)
        self.assertIn("# 📈 Apple Inc. (AAPL)", markdown)
        self.assertIn("345.00 USD", markdown)
        self.assertIn("Capitalisation boursière", markdown)
        self.assertIn("Ratio C/B (P/E Trailing)", markdown)
        self.assertIn("Performance financière & Rentabilité", markdown)
        self.assertIn("Consensus & Objectifs des analystes", markdown)
        self.assertIn("Historique récent des cotations", markdown)
        self.assertIn("Profil de l'entreprise", markdown)
        self.assertEqual(meta["symbol"], "AAPL")
        self.assertEqual(meta["price"], 345.0)


class TestFinanceApiMocked(unittest.IsolatedAsyncioTestCase):
    async def test_search_yahoo_ticker(self):
        mock_response = httpx.Response(
            200,
            json={
                "quotes": [
                    {"symbol": "MC.PA", "shortname": "LVMH", "quoteType": "EQUITY", "score": 20000}
                ]
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        res = await search_yahoo_ticker(mock_client, "LVMH")
        self.assertIsNotNone(res)
        self.assertEqual(res["symbol"], "MC.PA")

    async def test_fetch_yahoo_chart(self):
        mock_response = httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {"symbol": "AAPL", "regularMarketPrice": 345.0},
                            "timestamp": [1729500000],
                            "indicators": {"quote": [{}]},
                        }
                    ]
                }
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        res = await fetch_yahoo_chart(mock_client, "AAPL")
        self.assertIsNotNone(res)
        self.assertEqual(res["meta"]["symbol"], "AAPL")

    async def test_fetch_and_parse_yahoo_finance(self):
        settings = Settings(_env_file=None, demo_mode=False, eod_historical_data_key="")

        with patch("app.finance.get_yahoo_crumb_and_client") as mock_get_client, \
             patch("app.finance.search_yahoo_ticker") as mock_search, \
             patch("app.finance.fetch_yahoo_chart") as mock_chart, \
             patch("app.finance.fetch_yahoo_quote_summary") as mock_summary:

            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.aclose = AsyncMock()
            mock_get_client.return_value = (mock_client, "test-crumb")

            mock_search.return_value = {"symbol": "TTE", "shortname": "TotalEnergies SE"}
            mock_chart.return_value = {
                "meta": {"symbol": "TTE", "regularMarketPrice": 62.5, "currency": "EUR"},
                "timestamp": [1729500000],
                "indicators": {"quote": [{"open": [62.0], "high": [63.0], "low": [61.5], "close": [62.5], "volume": [1000000]}]},
            }
            mock_summary.return_value = {
                "price": {"shortName": "TotalEnergies SE", "regularMarketPrice": {"raw": 62.5}, "currency": "EUR"},
                "financialData": {"totalRevenue": {"raw": 2.2e11}},
                "defaultKeyStatistics": {},
                "assetProfile": {"sector": "Energy"},
            }

            fn, content, mime, text, extraction = await fetch_and_parse_yahoo_finance(settings, "TotalEnergies")
            self.assertIn("TotalEnergies", fn)
            self.assertIn("TTE", fn)
            self.assertEqual(mime, "text/html; type=finance; source=yahoo-finance")
            self.assertIn("62.5", text)
            self.assertEqual(extraction["model"], "yahoo-finance")
            self.assertEqual(extraction["symbol"], "TTE")

    async def test_score_eodhd_search_item(self):
        item_exact = {"Code": "STLA", "Exchange": "US", "Name": "Stellantis NV", "Type": "Common Stock"}
        item_other = {"Code": "OTHER", "Exchange": "FR", "Name": "Other Co", "Type": "Bond"}
        self.assertGreater(score_eodhd_search_item("STLA", item_exact), score_eodhd_search_item("STLA", item_other))

    async def test_search_eodhd_ticker(self):
        mock_response = httpx.Response(
            200,
            json=[
                {"Code": "STLAP", "Exchange": "PA", "Name": "Stellantis NV", "Type": "Common Stock", "Country": "France", "Currency": "EUR"},
                {"Code": "STLA", "Exchange": "US", "Name": "Stellantis NV", "Type": "Common Stock", "Country": "USA", "Currency": "USD"},
            ],
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        res = await search_eodhd_ticker(mock_client, "Stellantis", "fake-token")
        self.assertIsNotNone(res)
        self.assertEqual(res["Code"], "STLAP")
        self.assertEqual(res["Exchange"], "PA")
        self.assertEqual(res["ticker"], "STLAP.PA")

    async def test_fetch_eodhd_realtime(self):
        mock_response = httpx.Response(
            200,
            json={
                "code": "STLA.US",
                "timestamp": 1729500000,
                "open": 12.0,
                "high": 12.5,
                "low": 11.9,
                "close": 12.35,
                "volume": 20000000,
                "previousClose": 12.15,
                "change": 0.20,
                "change_p": 1.646,
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        res = await fetch_eodhd_realtime(mock_client, "STLA.US", "fake-token")
        self.assertIsNotNone(res)
        self.assertEqual(res["code"], "STLA.US")
        self.assertEqual(res["close"], 12.35)

    async def test_fetch_eodhd_historical_eod(self):
        mock_response = httpx.Response(
            200,
            json=[
                {"date": "2026-10-22", "open": 12.0, "high": 12.5, "low": 11.9, "close": 12.35, "volume": 20000000},
                {"date": "2026-10-21", "open": 12.1, "high": 12.2, "low": 11.8, "close": 12.15, "volume": 18000000},
            ],
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        bars = await fetch_eodhd_historical_eod(mock_client, "STLA.US", "fake-token", limit=5)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["date"], "2026-10-22")

    async def test_build_eodhd_markdown(self):
        rt_data = {
            "code": "STLA.US",
            "close": 12.35,
            "previousClose": 12.15,
            "open": 12.0,
            "high": 12.5,
            "low": 11.9,
            "volume": 20000000,
            "change": 0.20,
            "change_p": 1.646,
        }
        search_item = {"Name": "Stellantis NV", "Exchange": "US", "Country": "USA", "Currency": "USD"}
        eod_bars = [{"date": "2026-10-22", "close": 12.35, "open": 12.0, "high": 12.5, "low": 11.9, "volume": 20000000}]

        title, md, meta = build_eodhd_markdown("STLA.US", search_item, rt_data, eod_bars)
        self.assertIn("Stellantis NV", title)
        self.assertIn("EOD Historical Data", md)
        self.assertIn("12.35 USD", md)
        self.assertEqual(meta["provider"], "eodhd")
        self.assertEqual(meta["symbol"], "STLA.US")
        self.assertEqual(meta["price"], 12.35)

    async def test_fetch_and_parse_eodhd(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-secret-key", demo_mode=False)

        with patch("app.finance.search_eodhd_ticker") as mock_search, \
             patch("app.finance.fetch_eodhd_realtime") as mock_rt, \
             patch("app.finance.fetch_eodhd_historical_eod") as mock_bars, \
             patch("app.finance.fetch_eodhd_fundamentals") as mock_funds, \
             patch("app.finance.get_yahoo_crumb_and_client") as mock_y_client:

            mock_search.return_value = {
                "Code": "STLA",
                "Exchange": "US",
                "Name": "Stellantis NV",
                "ticker": "STLA.US",
                "Currency": "USD",
                "Country": "USA",
            }
            mock_rt.return_value = {
                "code": "STLA.US",
                "close": 12.35,
                "previousClose": 12.15,
                "open": 12.0,
                "high": 12.5,
                "low": 11.9,
                "volume": 20000000,
                "change": 0.20,
                "change_p": 1.646,
            }
            mock_bars.return_value = [
                {"date": "2026-10-22", "close": 12.35, "open": 12.0, "high": 12.5, "low": 11.9, "volume": 20000000}
            ]
            mock_funds.return_value = None

            y_c = AsyncMock(spec=httpx.AsyncClient)
            y_c.aclose = AsyncMock()
            mock_y_client.return_value = (y_c, "crumb")

            fn, content, mime, text, extraction = await fetch_and_parse_yahoo_finance(settings, "Stellantis")
            self.assertIn("Stellantis", fn)
            self.assertIn("EOD Historical Data", fn)
            self.assertEqual(mime, "text/html; type=finance; source=eod-historical-data")
            self.assertEqual(extraction["model"], "eod-historical-data")
            self.assertEqual(extraction["symbol"], "STLA.US")
            self.assertEqual(extraction["provider"], "eodhd")

    async def test_eodhd_fallback_to_yahoo_on_error(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-secret-key", demo_mode=False)

        with patch("app.finance.search_eodhd_ticker", side_effect=Exception("EODHD network timeout")), \
             patch("app.finance.get_yahoo_crumb_and_client") as mock_y_client, \
             patch("app.finance.search_yahoo_ticker") as mock_y_search, \
             patch("app.finance.fetch_yahoo_chart") as mock_y_chart, \
             patch("app.finance.fetch_yahoo_quote_summary") as mock_y_summary:

            y_c = AsyncMock(spec=httpx.AsyncClient)
            y_c.aclose = AsyncMock()
            mock_y_client.return_value = (y_c, "crumb")

            mock_y_search.return_value = {"symbol": "STLA", "shortname": "Stellantis N.V."}
            mock_y_chart.return_value = {
                "meta": {"symbol": "STLA", "regularMarketPrice": 12.35, "currency": "USD"},
                "timestamp": [1729500000],
                "indicators": {"quote": [{}]},
            }
            mock_y_summary.return_value = {
                "price": {"shortName": "Stellantis N.V.", "regularMarketPrice": {"raw": 12.35}, "currency": "USD"},
            }

            fn, content, mime, text, extraction = await fetch_and_parse_yahoo_finance(settings, "Stellantis")
            self.assertIn("Yahoo Finance", fn)
            self.assertEqual(mime, "text/html; type=finance; source=yahoo-finance")
            self.assertEqual(extraction["model"], "yahoo-finance")

    async def test_web_routing_to_yahoo_finance(self):
        settings = Settings()
        with patch("app.finance.fetch_and_parse_yahoo_finance") as mock_finance:
            mock_finance.return_value = (
                "📈 Apple Inc. (AAPL) · Yahoo Finance",
                b"test",
                "text/html; type=finance; source=yahoo-finance",
                "markdown",
                {"model": "yahoo-finance", "symbol": "AAPL"},
            )
            fn, cnt, mime, txt, extr = await fetch_and_parse_web_url(settings, "https://finance.yahoo.com/quote/AAPL")
            self.assertEqual(extr["model"], "yahoo-finance")
            self.assertEqual(extr["symbol"], "AAPL")

    async def test_process_message_finance_inquiries(self):
        settings = Settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            upload_dir = Path(tmp_dir)

            with patch("app.finance.fetch_and_parse_yahoo_finance") as mock_fetch:
                mock_fetch.return_value = (
                    "📈 Apple Inc. (AAPL) · Yahoo Finance",
                    b"markdown-content",
                    "text/html; type=finance; source=yahoo-finance",
                    "# Apple Stock",
                    {"model": "yahoo-finance", "symbol": "AAPL", "url": "https://finance.yahoo.com/quote/AAPL"},
                )

                attachments = await process_message_finance_inquiries(
                    settings,
                    "Donne-moi le cours de bourse d'Apple",
                    [],
                    user_id="user-123",
                    message_id="msg-456",
                    upload_dir=upload_dir,
                )

                self.assertEqual(len(attachments), 1)
                att = attachments[0]
                self.assertEqual(att.filename, "📈 Apple Inc. (AAPL) · Yahoo Finance")
                self.assertEqual(att.user_id, "user-123")
                self.assertEqual(att.message_id, "msg-456")
                self.assertEqual(att.extracted_text, "# Apple Stock")
                self.assertTrue((upload_dir / att.storage_name).is_file())

    async def test_process_message_with_finance_mode(self):
        settings = Settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            upload_dir = Path(tmp_dir)

            with patch("app.finance.fetch_and_parse_yahoo_finance") as mock_fetch:
                mock_fetch.return_value = (
                    "📈 Stellantis N.V. (STLA) · Yahoo Finance",
                    b"markdown-content",
                    "text/html; type=finance; source=yahoo-finance",
                    "# Stellantis",
                    {"model": "yahoo-finance", "symbol": "STLA", "url": "https://finance.yahoo.com/quote/STLA"},
                )

                attachments = await process_message_finance_inquiries(
                    settings,
                    "stellantis",
                    [],
                    user_id="user-123",
                    message_id="msg-456",
                    upload_dir=upload_dir,
                    finance_mode=True,
                )

                self.assertEqual(len(attachments), 1)
                self.assertEqual(attachments[0].filename, "📈 Stellantis N.V. (STLA) · Yahoo Finance")

    def test_query_variants_shrinks_noisy_candidates(self):
        variants = query_variants("en détail air liquide")
        self.assertEqual(variants[0], "en détail air liquide")
        self.assertIn("air liquide", variants)
        self.assertEqual(query_variants("AAPL"), ["AAPL"])

    def test_detect_strips_detail_prefix(self):
        self.assertEqual(detect_financial_entities("analyse en détail air liquide en ce moment"), ["air liquide"])

    async def test_entity_resolver_supersedes_heuristics(self):
        settings = Settings()
        seen: dict = {}

        async def resolver(text, previous):
            seen["text"], seen["previous"] = text, previous
            return ["Air Liquide"]

        with tempfile.TemporaryDirectory() as tmp_dir, patch("app.finance.fetch_and_parse_yahoo_finance") as mock_fetch:
            mock_fetch.return_value = (
                "📈 Air Liquide (AI.PA) · EOD Historical Data", b"x",
                "text/html; type=finance; source=eod-historical-data", "# AI",
                {"model": "eod-historical-data", "symbol": "AI.PA"},
            )
            attachments = await process_message_finance_inquiries(
                settings, "analyse les données financières stp", [], user_id="u", message_id="m",
                upload_dir=Path(tmp_dir), finance_mode=True, previous_targets=["AI.PA"], entity_resolver=resolver,
            )
        self.assertEqual(seen["previous"], ["AI.PA"])
        mock_fetch.assert_called_once_with(settings, "Air Liquide")
        self.assertEqual(len(attachments), 1)

    async def test_resolver_empty_list_fetches_nothing(self):
        async def resolver(text, previous):
            return []

        with tempfile.TemporaryDirectory() as tmp_dir, patch("app.finance.fetch_and_parse_yahoo_finance") as mock_fetch:
            attachments = await process_message_finance_inquiries(
                Settings(), "t'as cherché sur eod finance et yahoo finances ?", [], user_id="u", message_id="m",
                upload_dir=Path(tmp_dir), finance_mode=True, entity_resolver=resolver,
            )
        mock_fetch.assert_not_called()
        self.assertEqual(attachments, [])

    async def test_resolver_failure_falls_back_to_previous_targets_and_reports_failures(self):
        async def resolver(text, previous):
            raise RuntimeError("LLM down")

        failures: list[str] = []
        with tempfile.TemporaryDirectory() as tmp_dir, patch("app.finance.fetch_and_parse_yahoo_finance") as mock_fetch:
            mock_fetch.side_effect = RuntimeError("API down")
            attachments = await process_message_finance_inquiries(
                Settings(), "et maintenant ?", [], user_id="u", message_id="m", upload_dir=Path(tmp_dir),
                finance_mode=True, previous_targets=["AI.PA"], entity_resolver=resolver, failures=failures,
            )
        mock_fetch.assert_called_once_with(mock_fetch.call_args[0][0], "AI.PA")
        self.assertEqual(attachments, [])
        self.assertEqual(failures, ["AI.PA"])

    async def test_fetch_dual_financial_attachments_both_succeed(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-key", demo_mode=False)
        eod_tuple = (
            "📈 Air Liquide (AI.PA) · EOD Historical Data",
            b"# EOD Quote",
            "text/html; type=finance; source=eod-historical-data",
            "# EOD Quote",
            {"model": "eod-historical-data", "symbol": "AI.PA", "provider": "eodhd"},
        )
        yahoo_tuple = (
            "📈 Air Liquide (AI.PA) · Yahoo Finance",
            b"# Yahoo Financials",
            "text/html; type=finance; source=yahoo-finance",
            "# Yahoo Financials",
            {"model": "yahoo-finance", "symbol": "AI.PA", "provider": "yahoo_finance"},
        )

        with patch("app.finance.fetch_eodhd_quote_data", return_value=eod_tuple), \
             patch("app.finance.fetch_yahoo_financials_data", return_value=yahoo_tuple):
            results = await fetch_dual_financial_attachments(settings, "Air Liquide")
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0][4]["provider"], "eodhd")
            self.assertEqual(results[1][4]["provider"], "yahoo_finance")

    async def test_fetch_dual_financial_attachments_eod_only(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-key", demo_mode=False)
        eod_tuple = (
            "📈 Air Liquide (AI.PA) · EOD Historical Data",
            b"# EOD Quote",
            "text/html; type=finance; source=eod-historical-data",
            "# EOD Quote",
            {"model": "eod-historical-data", "symbol": "AI.PA", "provider": "eodhd"},
        )
        with patch("app.finance.fetch_eodhd_quote_data", return_value=eod_tuple), \
             patch("app.finance.fetch_yahoo_financials_data", return_value=None):
            results = await fetch_dual_financial_attachments(settings, "Air Liquide")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][4]["provider"], "eodhd")

    async def test_fetch_dual_financial_attachments_yahoo_only_when_no_key(self):
        settings = Settings(_env_file=None, eod_historical_data_key="", demo_mode=False)
        yahoo_tuple = (
            "📈 Air Liquide (AI.PA) · Yahoo Finance",
            b"# Yahoo Financials",
            "text/html; type=finance; source=yahoo-finance",
            "# Yahoo Financials",
            {"model": "yahoo-finance", "symbol": "AI.PA", "provider": "yahoo_finance"},
        )
        with patch("app.finance.fetch_yahoo_financials_data", return_value=yahoo_tuple):
            results = await fetch_dual_financial_attachments(settings, "Air Liquide")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][4]["provider"], "yahoo_finance")

    async def test_process_message_creates_dual_attachments(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-key", demo_mode=False)
        eod_tuple = (
            "📈 Air Liquide (AI.PA) · EOD Historical Data",
            b"# EOD Quote Live",
            "text/html; type=finance; source=eod-historical-data",
            "# EOD Quote Live",
            {"model": "eod-historical-data", "symbol": "AI.PA", "provider": "eodhd", "price": 174.24},
        )
        yahoo_tuple = (
            "📈 Air Liquide (AI.PA) · Yahoo Finance",
            b"# Yahoo Financial Statements",
            "text/html; type=finance; source=yahoo-finance",
            "# Yahoo Financial Statements",
            {"model": "yahoo-finance", "symbol": "AI.PA", "provider": "yahoo_finance", "price": 174.24},
        )

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("app.finance.fetch_dual_financial_attachments", return_value=[eod_tuple, yahoo_tuple]):
            attachments = await process_message_finance_inquiries(
                settings,
                "Donne-moi le cours et les données financières d'Air Liquide",
                [],
                user_id="user-123",
                message_id="msg-456",
                upload_dir=Path(tmp_dir),
            )
            self.assertEqual(len(attachments), 2)
            self.assertEqual(attachments[0].extraction["provider"], "eodhd")
            self.assertEqual(attachments[1].extraction["provider"], "yahoo_finance")
            self.assertEqual(attachments[0].user_id, "user-123")
            self.assertEqual(attachments[1].user_id, "user-123")
            self.assertTrue((Path(tmp_dir) / attachments[0].storage_name).is_file())
            self.assertTrue((Path(tmp_dir) / attachments[1].storage_name).is_file())

    async def test_get_financial_dashboard_data(self):
        settings = Settings(_env_file=None, eod_historical_data_key="valid-key", demo_mode=False)

        mock_eod_item = {
            "Code": "AI",
            "Exchange": "PA",
            "Name": "Air Liquide SA",
            "ticker": "AI.PA",
            "Currency": "EUR",
            "Country": "France",
        }
        mock_eod_rt = {
            "code": "AI.PA",
            "close": 174.24,
            "previousClose": 174.0,
            "open": 173.5,
            "high": 175.0,
            "low": 173.0,
            "volume": 800000,
            "change": 0.24,
            "change_p": 0.138,
        }
        mock_bars = [
            {"date": "2026-10-28", "close": 174.24, "open": 173.5, "high": 175.0, "low": 173.0, "volume": 800000},
            {"date": "2026-10-27", "close": 174.0, "open": 173.0, "high": 174.5, "low": 172.5, "volume": 750000},
        ]
        mock_yahoo_sum = {
            "price": {"shortName": "Air Liquide", "longName": "L'Air Liquide S.A.", "currency": "EUR"},
            "financialData": {
                "totalRevenue": {"raw": 27045900288},
                "revenueGrowth": {"raw": 0.052},
                "ebitda": {"raw": 7624500224},
                "freeCashflow": {"raw": 2850000000},
                "recommendationKey": "buy",
                "targetMeanPrice": {"raw": 195.5},
            },
            "defaultKeyStatistics": {
                "trailingPE": {"raw": 31.4},
                "forwardPE": {"raw": 24.2},
                "netIncomeToCommon": {"raw": 3540000000},
            },
            "assetProfile": {
                "sector": "Basic Materials",
                "industry": "Specialty Chemicals",
                "longBusinessSummary": "Fournisseur mondial de gaz industriels.",
            },
            "summaryDetail": {
                "dividendYield": {"raw": 0.019},
            },
        }

        with patch("app.finance.search_eodhd_ticker", return_value=mock_eod_item), \
             patch("app.finance.fetch_eodhd_realtime", return_value=mock_eod_rt), \
             patch("app.finance.fetch_eodhd_historical_eod", return_value=mock_bars), \
             patch("app.finance.get_yahoo_crumb_and_client") as mock_y_client, \
             patch("app.finance.search_yahoo_ticker", return_value={"symbol": "AI.PA"}), \
             patch("app.finance.fetch_yahoo_quote_summary", return_value=mock_yahoo_sum), \
             patch("app.finance.fetch_yahoo_chart", return_value=None):

            y_c = AsyncMock(spec=httpx.AsyncClient)
            y_c.aclose = AsyncMock()
            mock_y_client.return_value = (y_c, "crumb")

            data = await get_financial_dashboard_data(settings, "Air Liquide")
            self.assertEqual(data["symbol"], "AI.PA")
            self.assertEqual(data["price"], 174.24)
            self.assertEqual(data["currency"], "EUR")
            self.assertTrue(data["has_eod"])
            self.assertTrue(data["has_yahoo"])
            self.assertEqual(len(data["eod_bars"]), 2)
            # Oldest first in eod_bars for graphing
            self.assertEqual(data["eod_bars"][0]["date"], "2026-10-27")
            self.assertEqual(data["eod_bars"][1]["date"], "2026-10-28")
            self.assertIn("valuation", data["financial_stats"])
            self.assertIn("profitability", data["financial_stats"])
            self.assertIn("balance_sheet", data["financial_stats"])
            self.assertIn("analysts", data["financial_stats"])
            self.assertIn("profile", data["financial_stats"])
            self.assertEqual(data["financial_stats"]["analysts"]["recommendation"], "BUY")


if __name__ == "__main__":
    unittest.main()
