
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from docx import Document as WordDocument
from openpyxl import load_workbook


@dataclass
class ExtractedDocumentContent:
    """Structured content extracted from a business document."""

    text: str
    tables: list[list[list[str | None]]]


class UnsupportedDocumentError(Exception):
    """Raised when the document format is not supported."""


def extract_pdf(file_path: Path) -> ExtractedDocumentContent:
    text_parts = []
    extracted_tables = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()

            if page_text:
                text_parts.append(page_text)

            for table in page.extract_tables():
                extracted_tables.append(
                    [
                        [
                            str(cell).strip() if cell is not None else None
                            for cell in row
                        ]
                        for row in table
                    ]
                )

    return ExtractedDocumentContent(
        text="\n\n".join(text_parts),
        tables=extracted_tables,
    )


def extract_docx(file_path: Path) -> ExtractedDocumentContent:
    document = WordDocument(file_path)

    text_parts = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    extracted_tables = []

    for table in document.tables:
        rows = []

        for row in table.rows:
            rows.append(
                [
                    cell.text.strip() or None
                    for cell in row.cells
                ]
            )

        extracted_tables.append(rows)

    return ExtractedDocumentContent(
        text="\n".join(text_parts),
        tables=extracted_tables,
    )


def extract_txt(file_path: Path) -> ExtractedDocumentContent:
    text = file_path.read_text(encoding="utf-8-sig")

    return ExtractedDocumentContent(
        text=text,
        tables=[],
    )


def extract_xlsx(file_path: Path) -> ExtractedDocumentContent:
    workbook = load_workbook(
        filename=file_path,
        read_only=True,
        data_only=True,
    )

    extracted_tables = []
    text_parts = []

    try:
        for worksheet in workbook.worksheets:
            rows = []

            for row in worksheet.iter_rows(values_only=True):
                normalized_row = [
                    str(cell).strip() if cell is not None else None
                    for cell in row
                ]

                if any(cell is not None for cell in normalized_row):
                    rows.append(normalized_row)

            if rows:
                extracted_tables.append(rows)
                text_parts.append(f"Sheet: {worksheet.title}")

    finally:
        workbook.close()

    return ExtractedDocumentContent(
        text="\n".join(text_parts),
        tables=extracted_tables,
    )


def extract_document(file_path: str | Path) -> ExtractedDocumentContent:
    """
    Extract text and tables from a supported business document.
    """

    path = Path(file_path)

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")

    extension = path.suffix.lower()

    extractors = {
        ".pdf": extract_pdf,
        ".docx": extract_docx,
        ".txt": extract_txt,
        ".xlsx": extract_xlsx,
    }

    extractor = extractors.get(extension)

    if extractor is None:
        raise UnsupportedDocumentError(
            f"Unsupported document format: {extension or 'none'}"
        )

    return extractor(path)
