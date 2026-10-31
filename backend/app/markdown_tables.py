"""Parse Markdown table cells and tidy verification-table presentation."""
import re


def split_table_row(row: str) -> list[str]:
    """Keep escaped pipes inside their cell instead of creating extra columns."""
    cells = re.split(r"(?<!\\)\|", row.strip())
    return [cell.strip().replace(r"\|", "|") for cell in cells[1:-1]]


def clean_verification_claim(text: str) -> str:
    """Remove leftover row delimiters and decorative block progress bars."""
    text = re.sub(r"[\u2580-\u259f]{3,}", "", text)
    text = re.sub(r"^(?:\s*\\?\|)+\s*|\s*(?:\\?\|\s*)+$", "", text)
    return re.sub(r"\s+", " ", text.replace(r"\|", "|")).strip()


def is_verification_table(headers: list[str]) -> bool:
    normalized = {header.strip().casefold() for header in headers}
    return {"statut", "confiance", "action claimevidence"} <= normalized


VERIFICATION_TABLE_CSS = """
    .report-verification-table .report-metadata-cell {
      white-space: nowrap;
      word-break: normal;
      overflow-wrap: normal;
    }
    @media print {
      .report-table-wrapper table.report-verification-table {
        table-layout: auto !important;
      }
    }
"""
