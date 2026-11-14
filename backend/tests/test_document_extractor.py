
from types import SimpleNamespace

import pytest
from docx import Document
from openpyxl import Workbook

from app.services.document_extractor import (
    UnsupportedDocumentError,
    extract_document,
)


def test_extract_txt(tmp_path):
    file_path = tmp_path / "invoice.txt"
    file_path.write_text(
        "Supplier: ABC Company\nInvoice: INV-001\nTotal: 250.00",
        encoding="utf-8",
    )

    result = extract_document(file_path)

    assert "ABC Company" in result.text
    assert "INV-001" in result.text
    assert "250.00" in result.text
    assert result.tables == []


def test_extract_docx_with_table(tmp_path):
    file_path = tmp_path / "invoice.docx"

    document = Document()
    document.add_paragraph("Invoice from ABC Company")

    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Description"
    table.cell(0, 1).text = "Amount"
    table.cell(1, 0).text = "Software"
    table.cell(1, 1).text = "100.00"

    document.save(file_path)

    result = extract_document(file_path)

    assert "ABC Company" in result.text
    assert len(result.tables) == 1
    assert result.tables[0][0] == ["Description", "Amount"]
    assert result.tables[0][1] == ["Software", "100.00"]


def test_extract_xlsx(tmp_path):
    file_path = tmp_path / "invoice.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Invoice"

    worksheet.append(["Description", "Amount"])
    worksheet.append(["Laptop", 500])

    workbook.save(file_path)

    result = extract_document(file_path)

    assert "Sheet: Invoice" in result.text
    assert len(result.tables) == 1
    assert result.tables[0][0] == ["Description", "Amount"]
    assert result.tables[0][1] == ["Laptop", "500"]


def test_extract_pdf(tmp_path, monkeypatch):
    file_path = tmp_path / "invoice.pdf"
    file_path.touch()

    fake_page = SimpleNamespace(
        extract_text=lambda: "Invoice from ABC Company",
        extract_tables=lambda: [
            [
                ["Description", "Amount"],
                ["Service", "200.00"],
            ]
        ],
    )

    class FakePDF:
        pages = [fake_page]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(
        "app.services.document_extractor.pdfplumber.open",
        lambda path: FakePDF(),
    )

    result = extract_document(file_path)

    assert "ABC Company" in result.text
    assert len(result.tables) == 1
    assert result.tables[0][1] == ["Service", "200.00"]


def test_unsupported_document_format(tmp_path):
    file_path = tmp_path / "invoice.csv"
    file_path.write_text("Invoice data")

    with pytest.raises(UnsupportedDocumentError):
        extract_document(file_path)


def test_missing_document():
    with pytest.raises(FileNotFoundError):
        extract_document("missing_invoice.pdf")
