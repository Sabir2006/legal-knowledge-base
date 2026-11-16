"""Конвертация PDF из interpelli/ в Markdown с YAML-фронтматтером в md/."""
from __future__ import annotations

import argparse
import logging
import re
from datetime import date
from pathlib import Path

import yaml

from ocr import extract_text_from_pdf

log = logging.getLogger(__name__)

SRC_DIR = Path("interpelli")
OUT_DIR = Path("md")


def _slug(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^\w\-]+", "-", name)
    return re.sub(r"-{2,}", "-", name).strip("-")


def _build_md(pdf_path: Path, text: str, used_ocr: bool) -> str:
    meta = {
        "title": pdf_path.stem,
        "source_file": str(pdf_path.as_posix()),
        "date": date.today().isoformat(),
        "ocr": used_ocr,
        "lang": "it",
    }
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    return f"---\n{front}---\n\n# {pdf_path.stem}\n\n{text}\n"


def convert_all(src: Path, out: Path, force: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(src.rglob("*.pdf"))
    log.info("Найдено PDF: %d", len(pdfs))

    for pdf in pdfs:
        rel = pdf.relative_to(src)
        target = out / rel.with_suffix(".md")
        if target.exists() and not force:
            log.debug("Пропуск (уже есть): %s", target)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            text, used_ocr = extract_text_from_pdf(pdf)
            if not text:
                log.warning("Пустой текст: %s", pdf)
                continue
            target.write_text(_build_md(pdf, text, used_ocr), encoding="utf-8")
            log.info("OK %s -> %s (ocr=%s)", pdf.name, target, used_ocr)
        except Exception as e:
            log.exception("Ошибка при %s: %s", pdf, e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=SRC_DIR, type=Path)
    parser.add_argument("--out", default=OUT_DIR, type=Path)
    parser.add_argument("--force", action="store_true", help="Перезаписывать существующие MD")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    convert_all(args.src, args.out, force=args.force)


if __name__ == "__main__":
    main()
