import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.agenziaentrate.gov.it"

ARCHIVE_URL = (
    "https://www.agenziaentrate.gov.it/portale/web/guest/"
    "normativa-e-prassi/risposte-agli-interpelli/interpelli/"
    "archivio-interpelli"
)

OUTPUT_DIR = Path("documents")
OUTPUT_DIR.mkdir(exist_ok=True)

MONTHS = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url: str) -> BeautifulSoup:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def make_safe_text(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text or "")
    text = re.sub(r"\s+", "_", text.strip())
    return text[:120]


def get_year_links(archive_url: str) -> list[tuple[str, str]]:
    soup = get_soup(archive_url)
    year_links = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        href = link["href"]

        if "interpelli-" not in href.lower():
            continue

        match = re.search(r"interpelli-(\d{4})", href.lower())

        if not match:
            continue

        year = match.group(1)
        year_url = urljoin(BASE, href)

        year_links.append((year, year_url))

    return list(dict.fromkeys(year_links))


def get_month_links(year: str, year_url: str) -> list[tuple[str, str]]:
    soup = get_soup(year_url)
    month_links = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)

        if not any(month in title for month in MONTHS):
            continue

        month_url = urljoin(BASE, link["href"])
        month_links.append((title, month_url))

    return list(dict.fromkeys(month_links))


def get_pdf_links(month_title: str, month_url: str) -> list[tuple[str, str]]:
    soup = get_soup(month_url)
    pdf_links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if ".pdf" not in href.lower():
            continue

        pdf_url = urljoin(BASE, href)
        title = link.get_text(" ", strip=True) or Path(pdf_url).stem

        pdf_links.append((title, pdf_url))

    return pdf_links


def make_filename(year: str, month: str, title: str) -> str:
    safe_year = make_safe_text(year)
    safe_month = make_safe_text(month)
    safe_title = make_safe_text(title) or "interpello"

    filename = f"{safe_year}_{safe_month}_{safe_title}.pdf"
    filename = re.sub(r"_+", "_", filename)

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def download_pdf(year: str, month: str, title: str, url: str) -> bool:
    filename = make_filename(year, month, title)
    output_path = OUTPUT_DIR / filename

    if output_path.exists():
        print(f"Already exists: {filename}")
        return False

    response = session.get(url, timeout=60)
    response.raise_for_status()

    output_path.write_bytes(response.content)
    print(f"Downloaded: {filename}")
    return True


def main():
    print(f"Checking archive: {ARCHIVE_URL}")

    year_links = get_year_links(ARCHIVE_URL)
    print(f"Found {len(year_links)} year pages")

    downloaded = 0

    for year, year_url in year_links:
        print(f"Checking year: {year}")

        month_links = get_month_links(year, year_url)
        print(f"Found {len(month_links)} month pages")

        for month_title, month_url in month_links:
            print(f"Checking month: {month_title}")

            pdf_links = get_pdf_links(month_title, month_url)
            print(f"Found {len(pdf_links)} PDF links")

            for title, pdf_url in pdf_links:
                if download_pdf(year, month_title, title, pdf_url):
                    downloaded += 1

    print(f"New PDFs downloaded: {downloaded}")


if __name__ == "__main__":
    main()