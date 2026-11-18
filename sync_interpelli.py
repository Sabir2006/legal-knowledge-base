import os
import re
import time
import logging
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader  # Подключаем библиотеку для чтения PDF

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://www.agenziaentrate.gov.it/portale/normativa-e-prassi/risposte-agli-interpelli/interpelli/archivio-interpelli"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

MONTHS_IT = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 
             'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']

# Безопасные заглушки (на GitHub ключи подтянутся автоматически из Secrets)
OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "https://sabir2006-legal-webui.hf.space")
OPEN_WEBUI_API_KEY = os.environ.get("OPEN_WEBUI_API_KEY", "sk-...")
OPEN_WEBUI_KNOWLEDGE_ID = os.environ.get("OPEN_WEBUI_KNOWLEDGE_ID", "2af088c1-bb62-4d0d-96b6-f7f16955a1ec")

def get_soup(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        logging.error(f"Не удалось загрузить {url}: {e}")
        return None

def extract_text_from_pdf(pdf_path):
    logging.info(f"Извлечение текста из PDF: {pdf_path}")
    try:
        reader = PdfReader(pdf_path)
        text_chunks = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_chunks.append(page_text)
        return "\n".join(text_chunks)
    except Exception as e:
        logging.error(f"Не удалось извлечь текст из PDF {pdf_path}: {e}")
        return ""

def upload_to_open_webui(filepath):
    if not OPEN_WEBUI_API_KEY or not OPEN_WEBUI_URL:
        logging.warning("OPEN_WEBUI_API_KEY или OPEN_WEBUI_URL не заданы. Пропуск загрузки в Open WebUI.")
        return False
        
    filename = os.path.basename(filepath)
    logging.info(f"Отправка {filename} в Open WebUI...")
    
    base_url = OPEN_WEBUI_URL.rstrip('/')
    upload_url = f"{base_url}/api/v1/files/"
    
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    
    try:
        # Шаг 1: Загружаем файл на сервер
        with open(filepath, 'rb') as f:
            files = {
                'file': (filename, f, 'text/markdown' if filename.endswith('.md') else 'application/pdf')
            }
            response = requests.post(upload_url, headers=headers, files=files, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            file_id = res_data.get("id")
            logging.info(f"Файл {filename} успешно импортирован, получен ID: {file_id}")
            
        # Шаг 2: Если задан ID базы знаний, прикрепляем файл к ней
        if OPEN_WEBUI_KNOWLEDGE_ID and file_id:
            logging.info(f"Привязка файла {filename} к базе знаний {OPEN_WEBUI_KNOWLEDGE_ID}...")
            link_url = f"{base_url}/api/v1/knowledge/{OPEN_WEBUI_KNOWLEDGE_ID}/file/add"
            link_headers = {
                "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}",
                "Content-Type": "application/json"
            }
            link_payload = {
                "file_id": file_id
            }
            link_response = requests.post(link_url, headers=link_headers, json=link_payload, timeout=30)
            link_response.raise_for_status()
            logging.info(f"Файл {filename} успешно добавлен в базу знаний!")
            
        return True
    except Exception as e:
        logging.error(f"Ошибка загрузки/привязки в Open WebUI для файла {filename}: {e}")
        return False

def download_file(url, filepath):
    if os.path.exists(filepath):
        return True, False
    
    logging.info(f"Скачивание PDF: {url} -> {filepath}")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        response = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        time.sleep(0.5)
        return True, True
    except Exception as e:
        logging.error(f"Ошибка при скачивании {url}: {e}")
        return False, False

def parse_years():
    soup = get_soup(BASE_URL)
    if not soup:
        return []
    year_links = []
    for a in soup.find_all('a'):
        href = a.get('href')
        text = a.get_text(strip=True)
        if href and ('interpelli-20' in href or '/portale/interpelli-20' in href):
            year_match = re.search(r'20\d{2}', text) or re.search(r'20\d{2}', href)
            if year_match:
                year_links.append((year_match.group(0), urljoin(BASE_URL, href)))
    year_links.sort(key=lambda x: x[0], reverse=True)
    return year_links

def parse_months(year_url):
    soup = get_soup(year_url)
    if not soup:
        return []
    month_links = []
    for a in soup.find_all('a'):
        href = a.get('href')
        text = a.get_text(strip=True).lower()
        if href and any(m in text for m in MONTHS_IT):
            if any(kw in href.lower() for kw in ['interpelli', 'risposte-interpello', 'giugno-2019', '/portale/']):
                month_links.append(urljoin(year_url, href))
    return list(dict.fromkeys(month_links))

def process_month_page(month_url, year_str):
    soup = get_soup(month_url)
    if not soup:
        return
    
    divs = soup.find_all('div', class_='indcart_gn')
    for div in divs:
        strong_tag = div.find('strong')
        a_tag = div.find('a')
        if not strong_tag or not a_tag or not a_tag.get('href'):
            continue
            
        meta_text = strong_tag.get_text(strip=True)
        pdf_url = urljoin(month_url, a_tag['href'])
        raw_title = a_tag.get_text(strip=True)
        
        num_match = re.search(r'n\.\s*(\d+)', meta_text, re.IGNORECASE)
        date_match = re.search(r'del\s+(\d{1,2}/\d{1,2}/\d{4})', meta_text, re.IGNORECASE)
        num = num_match.group(1) if num_match else "unknown"
        date_str = date_match.group(1) if date_match else "unknown"
        
        clean_title = re.sub(r'\s+', ' ', raw_title).strip()
        if clean_title.lower().endswith('- pdf') or clean_title.lower().endswith('-pdf'):
            clean_title = clean_title.rsplit('-', 1)[0].strip()
            
        pdf_filename = f"Risposta_{num}.pdf"
        md_filename = f"Risposta_{num}.md"
        year_dir = os.path.join("interpelli", year_str)
        pdf_path = os.path.join(year_dir, pdf_filename)
        md_path = os.path.join(year_dir, md_filename)
        
        # Скачиваем оригинальный PDF
        download_success, is_new = download_file(pdf_url, pdf_path)
        
        if download_success and is_new:
            # Извлекаем ПОЛНЫЙ текст из скачанного PDF
            full_pdf_text = extract_text_from_pdf(pdf_path)
            
            md_content = f"""# Risposta n. {num} del {date_str}
**Data:** {date_str}  
**Numero:** {num}  
**Anno:** {year_str}  

### Descrizione:
{clean_title}

### Contenuto Integrale del Documento:
{full_pdf_text}

### Link Originale:
* [Original PDF]({pdf_url})
"""
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
            # Загружаем ОПТИМИЗИРОВАННЫЙ .md файл с ПОЛНЫМ ТЕКСТОМ в Open WebUI!
            upload_to_open_webui(md_path)

def main():
    logging.info("Старт синхронизации с Open WebUI...")
    years = parse_years()
    
    ALLOWED_YEARS = ['2024', '2023']
    filtered_years = [y for y in years if y[0] in ALLOWED_YEARS]
    
    for year_str, year_url in filtered_years:
        logging.info(f"=== Проверка {year_str} года ===")
        months = parse_months(year_url)
        for month_url in months:
            process_month_page(month_url, year_str)
            time.sleep(0.5)

if __name__ == "__main__":
    main()