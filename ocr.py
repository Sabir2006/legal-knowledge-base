"""Извлечение текста из PDF: сначала текстовый слой, при необходимости — OCR."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import fitz  # pymupdf
from PIL import Image
import pytesseract

log = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = 40  # если меньше — считаем страницу «пустой» и идём в OCR


def _clean_text(text: str) -> str:
    """Нормализация: убираем лишние пробелы, склеиваем переносы, чистим мусор."""
    text = text.replace("\u00ad", "")           # мягкие переносы
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # склеиваем слова, разорванные переносом строки (эвристика)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text.strip()


def _ocr_page(page: "fitz.Page", lang: str = "ita+eng") -> str:
    """Рендер страницы в изображение и OCR через tesseract."""
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def extract_text_from_pdf(
    pdf_path: Path,
    lang: str = "ita+eng",
    force_ocr: bool = False,
) -> tuple[str, bool]:
    """
    Возвращает (текст, использовался_ли_ocr).
    force_ocr=True — игнорировать текстовый слой.
    """
    pdf_path = Path(pdf_path)
    used_ocr = False
    parts: list[str] = []

    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = "" if force_ocr else page.get_text("text")
            if len(text.strip()) < MIN_CHARS_PER_PAGE:
                log.info("%s: стр. %d — мало текста, запускаю OCR", pdf_path.name, i)
                text = _ocr_page(page, lang=lang)
                used_ocr = True
            parts.append(text)

    full = _clean_text("\n\n".join(parts))
    return full, used_ocr
