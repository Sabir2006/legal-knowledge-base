import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SITE_URL = os.getenv("SITE_URL", "")
OUTPUT_DIR = Path("documents")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def get_pdf_links(page_url: str) -> list[str]:
    response = requests.get(page_url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    links = []

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().endswith(".pdf"):
            full_url = urljoin(page_url, href)
            links.append(full_url)

    return list(dict.fromkeys(links))


def make_safe_filename(url: str) -> str:
    filename = url.split("/")[-1].split("?")[0]
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def download_pdf(pdf_url: str) -> bool:
    filename = make_safe_filename(pdf_url)
    output_path = OUTPUT_DIR / filename

    if output_path.exists():
        print(f"Already exists: {filename}")
        return False

    response = requests.get(pdf_url, headers=HEADERS, timeout=60)
    response.raise_for_status()

    output_path.write_bytes(response.content)
    print(f"Downloaded: {filename}")
    return True


def main():
    if not SITE_URL:
        raise ValueError("SITE_URL is not set. Add it to GitHub Secrets.")

    print(f"Checking page: {SITE_URL}")

    pdf_links = get_pdf_links(SITE_URL)
    print(f"Found {len(pdf_links)} PDF links")

    downloaded = 0

    for pdf_url in pdf_links:
        if download_pdf(pdf_url):
            downloaded += 1

    print(f"New files downloaded: {downloaded}")


if __name__ == "__main__":
    main()