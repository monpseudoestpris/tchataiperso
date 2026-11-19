import asyncio
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from docx import Document
import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.config import Settings
from app.finance_reports import (
    _SINGLE_PASS_LLM_CHARS,
    analyze_quarterly_report,
    count_report_pages,
    extract_markdown_tables,
    extract_report_content,
    extract_report_text,
    split_report_into_page_chunks,
)
from app.models import FinanceQuarterlyReport
from app.serializers import quarterly_report_json


def _build_pdf_bytes(page_texts: list[str]) -> bytes:
    writer = PdfWriter()
    font_dict = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in page_texts:
        page = writer.add_blank_page(width=450, height=500)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_dict})}
        )
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 11 Tf 36 440 Td ({safe}) Tj ET".encode("latin-1", errors="replace"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_docx_table_conversion_and_markdown_table_extraction() -> None:
    doc = Document()
    doc.add_heading("Compte de resultat consolide", level=2)
    table = doc.add_table(rows=3, cols=3)
    rows_data = [
        ["Poste", "T3 2026", "T3 2025"],
        ["Chiffre d'affaires", "6 800 M€", "6 400 M€"],
        ["EBITDA", "1 950 M€", "1 820 M€"],
    ]
    for r_idx, row_vals in enumerate(rows_data):
        for c_idx, val in enumerate(row_vals):
            table.rows[r_idx].cells[c_idx].text = val
    buf = io.BytesIO()
    doc.save(buf)

    source_type, extracted = extract_report_text(buf.getvalue(), "rapport_t3.docx")
    assert source_type == "docx"
    assert "| Poste | T3 2026 | T3 2025 |" in extracted
    assert "| --- | --- | --- |" in extracted

    tables = extract_markdown_tables(extracted)
    assert len(tables) == 1
    assert tables[0]["page"] == 1
    assert tables[0]["title"] == "Compte de resultat consolide"
    assert tables[0]["rows_count"] == 2
    assert tables[0]["cols_count"] == 3
    assert "6 800 M€" in tables[0]["markdown"]


def test_html_table_colspan_conversion_and_page_tracking() -> None:
    raw = (
        "[Page 12]\n\n"
        "## Ventilation par activite\n\n"
        '<table><tr><th colspan="2">Activite</th><th>Croissance</th></tr>'
        "<tr><td>Industrie</td><td>Europe</td><td>+7,4%</td></tr></table>"
    )
    tables = extract_markdown_tables(raw)
    assert len(tables) == 1
    assert tables[0]["page"] == 12
    assert tables[0]["title"] == "Ventilation par activite"
    assert tables[0]["cols_count"] == 3
    assert tables[0]["rows_count"] == 1
    assert "<table" not in tables[0]["markdown"].lower()
    assert "| Industrie | Europe | +7,4% |" in tables[0]["markdown"]


def test_pdf_mistral_ocr_multibatch_10_pages_and_no_120k_truncation(tmp_path: Path) -> None:
    pdf_bytes = _build_pdf_bytes([f"Page {i} texte brut" for i in range(1, 11)])
    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        mistral_api_key="test-mistral-key",
        ocr_model="mistral-ocr-4-1",
    )

    recorded_batches: list[list[int]] = []

    class _FakeStreamCtx:
        def __init__(self, payload: dict):
            self._payload = payload

        async def __aenter__(self):
            batches = list(self._payload["pages"])
            recorded_batches.append(batches)
            pages_resp = []
            for p_idx in batches:
                if p_idx == 8:
                    # Page 9 (index 8) : reference externe `[tbl-0.md](tbl-0.md)`
                    pages_resp.append(
                        {
                            "index": p_idx,
                            "markdown": "### Chiffres par segment\n\n[tbl-0.md](tbl-0.md)",
                            "tables": [
                                {
                                    "id": "tbl-0.md",
                                    "content": "| Segment | CA 2026 |\n| --- | --- |\n| Gaz industriels | 5 100 M€ |",
                                }
                            ],
                        }
                    )
                else:
                    # > 15 000 car par page -> depasse 120 000 car au total sans etre tronque
                    pages_resp.append(
                        {
                            "index": p_idx,
                            "markdown": f"Contenu detaille page {p_idx + 1}. " + ("A" * 15000),
                        }
                    )
            req = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
            self._resp = httpx.Response(200, request=req, json={"pages": pages_resp})
            return self._resp

        async def __aexit__(self, exc_type, exc, tb):
            return None

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.stream = MagicMock(side_effect=lambda method, url, **kwargs: _FakeStreamCtx(kwargs["json"]))

    with patch("app.finance_reports.httpx.AsyncClient", return_value=fake_client):
        source_type, extracted = asyncio.run(extract_report_content(s, pdf_bytes, "rapport_10p.pdf"))

    assert source_type == "pdf-ocr"
    assert recorded_batches == [list(range(0, 8)), [8, 9]]
    assert count_report_pages(extracted) == 10
    assert len(extracted) > 130_000
    assert "[Page 10]" in extracted

    tables = extract_markdown_tables(extracted)
    assert len(tables) == 1
    assert tables[0]["page"] == 9
    assert tables[0]["title"] == "Chiffres par segment"
    assert "Gaz industriels" in tables[0]["markdown"]
    assert "5 100 M€" in tables[0]["markdown"]


def test_pdf_ocr_fallback_to_pypdf_on_missing_key_or_error(tmp_path: Path) -> None:
    pdf_bytes = _build_pdf_bytes(["Premiere page CA 100M", "Deuxieme page EBITDA 25M"])

    # Sans cle Mistral -> repli pypdf direct
    s_no_key = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False, mistral_api_key="")
    src1, txt1 = asyncio.run(extract_report_content(s_no_key, pdf_bytes, "sans_ocr.pdf"))
    assert src1 == "pdf"
    assert count_report_pages(txt1) == 2
    assert "Premiere page CA 100M" in txt1
    assert "Deuxieme page EBITDA 25M" in txt1

    # Avec cle Mistral mais HTTP 502 -> repli pypdf transparent
    s_with_key = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False, mistral_api_key="test-mistral")

    class _ErrStreamCtx:
        async def __aenter__(self):
            req = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
            return httpx.Response(502, request=req, text="Bad Gateway")

        async def __aexit__(self, exc_type, exc, tb):
            return None

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.stream = MagicMock(return_value=_ErrStreamCtx())

    with patch("app.finance_reports.httpx.AsyncClient", return_value=fake_client):
        src2, txt2 = asyncio.run(extract_report_content(s_with_key, pdf_bytes, "repli.pdf"))

    assert src2 == "pdf"
    assert count_report_pages(txt2) == 2
    assert "Deuxieme page EBITDA 25M" in txt2


def test_analyze_quarterly_report_map_reduce_long_document(tmp_path: Path) -> None:
    # Genere un rapport de 10 pages (~70 000 car) depassant `_SINGLE_PASS_LLM_CHARS`
    pages = [f"[Page {i}]\nAnalyse detaillee page {i}. " + ("B" * 6800) for i in range(1, 10)]
    pages.append(
        "[Page 10]\n## Tableau annexe\n\n| Poste | 2026 |\n| --- | --- |\n| Dette nette | 9,1 Md€ |\n" + ("C" * 3000)
    )
    full_text = "\n\n".join(pages)
    assert len(full_text) > _SINGLE_PASS_LLM_CHARS

    chunks = split_report_into_page_chunks(full_text)
    assert len(chunks) >= 2
    assert chunks[0]["page_start"] == 1
    assert chunks[-1]["page_end"] == 10

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="test-llm-key",
        summary_model="test-summary-model",
    )

    llm_calls: list[str] = []

    async def _fake_post(url: str, headers=None, json: dict | None = None):  # noqa: A002
        user_msg = json["messages"][1]["content"]
        llm_calls.append(user_msg)
        req = httpx.Request("POST", url)
        if "Relevés exhaustifs par lots de pages" in user_msg:
            final_payload = {
                "key_metrics": {
                    "revenue": "14,2 Md€",
                    "net_debt": "9,1 Md€",
                    "guidance": "Marge +50 bps",
                },
                "summary_markdown": "## 1. Synthèse exécutive\n\n| Poste | Valeur |\n| --- | --- |\n| Chiffre d'affaires | 14,2 Md€ |\n| Dette nette | 9,1 Md€ |",
            }
            return httpx.Response(
                200,
                request=req,
                json={"choices": [{"message": {"content": json_lib_dumps(final_payload)}}]},
            )
        return httpx.Response(
            200,
            request=req,
            json={"choices": [{"message": {"content": "## Relevé lot\n| Dette nette | 9,1 Md€ |\n| --- | --- |"}}]},
        )

    import json as _json

    json_lib_dumps = _json.dumps

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.post = AsyncMock(side_effect=_fake_post)

    with patch("app.finance_reports.httpx.AsyncClient", return_value=fake_client):
        summary_md, metrics = asyncio.run(
            analyze_quarterly_report(
                s,
                symbol="AI.PA",
                company_name="Air Liquide",
                title="Rapport Annuel 2026",
                period_label="FY 2026",
                text=full_text,
            )
        )

    assert len(llm_calls) == len(chunks) + 1
    last_range = f"Pages {chunks[-1]['page_start']}–{chunks[-1]['page_end']}"
    assert any(last_range in c and "[Page 10]" in c for c in llm_calls[:-1])
    assert "Relevés exhaustifs par lots de pages" in llm_calls[-1]
    assert metrics["revenue"] == "14,2 Md€"
    assert metrics["net_debt"] == "9,1 Md€"
    assert "| Chiffre d'affaires | 14,2 Md€ |" in summary_md


def test_quarterly_report_serializer_and_router_expose_tables(tmp_path: Path) -> None:
    from tests.test_api import authenticated_client

    sample_text = (
        "[Page 1]\n\n"
        "### Chiffres cles\n\n"
        "| Indicateur | T3 2026 |\n| --- | --- |\n| CA | 6,8 Md€ |\n\n"
        "[Page 2]\n\n"
        "### Flux de tresorerie\n\n"
        "| Flux | Montant |\n| --- | --- |\n| FCF | 910 M€ |"
    )
    item = FinanceQuarterlyReport(
        id="rep-1",
        user_id="u-1",
        symbol="AI.PA",
        company_name="Air Liquide",
        title="Communique T3 2026",
        period_label="T3 2026",
        source_type="pdf-ocr",
        filename="t3_2026.pdf",
        storage_name="finrep-1",
        extracted_text=sample_text,
        summary_markdown="## Resume",
        key_metrics={"revenue": "6,8 Md€"},
        created_at=datetime.now(timezone.utc),
    )

    compact = quarterly_report_json(item, include_extracted=False)
    assert compact["page_count"] == 2
    assert compact["tables_count"] == 2
    assert "extracted_tables" not in compact

    full = quarterly_report_json(item, include_extracted=True)
    assert full["page_count"] == 2
    assert full["tables_count"] == 2
    assert len(full["extracted_tables"]) == 2
    assert full["extracted_tables"][0]["title"] == "Chiffres cles"
    assert full["extracted_tables"][1]["page"] == 2

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        openrouter_api_key="",
        mistral_api_key="",
    )
    with authenticated_client(s) as client:
        res_post = client.post(
            "/api/finance/reports",
            data={"symbol": "AI.PA", "company_name": "Air Liquide", "period_label": "T3 2026"},
            files={"file": ("t3.md", sample_text.encode("utf-8"), "text/markdown")},
        )
        assert res_post.status_code == 201
        created = res_post.json()
        assert created["page_count"] == 2
        assert created["tables_count"] == 2
        assert len(created["extracted_tables"]) == 2

        res_list = client.get("/api/finance/reports?symbol=AI.PA")
        assert res_list.status_code == 200
        assert res_list.json()["items"][0]["tables_count"] == 2
