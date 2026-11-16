import os
import re
import time
import json
import logging
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://www.agenziaentrate.gov.it/portale/normativa-e-prassi/risposte-agli-interpelli/interpelli/archivio-interpelli"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

MONTHS_IT = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 
             'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']

# Получаем переменные из секретов GitHub
COZE_API_KEY = os.environ.get("COZE_API_KEY")
COZE_DATASET_ID = os.environ.get("COZE_DATASET_ID")

def get_soup(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        logging.error(f"Не удалось загрузить {url}: {e}")
        return None

def upload_to_coze(filepath):
    if not COZE_API_KEY or not COZE_DATASET_ID:
        logging.warning("COZE_API_KEY или COZE_DATASET_ID не заданы. Пропуск загрузки в Coze.")
        return False
        
    filename = os.path.basename(filepath)
    logging.info(f"Загрузка {filename} в Coze.com...")
    
    try:
        # Шаг 1: Загружаем файл во временное файловое хранилище Coze
        upload_url = "https://api.coze.com/open_api/v1/files/upload"
        upload_headers = {
            "Authorization": f"Bearer {COZE_API_KEY}"
        }
        
        with open(filepath, 'rb') as f:
            upload_files = {
                'file': (filename, f, 'text/markdown' if filename.endswith('.md') else 'application/pdf')
            }
            response = requests.post(upload_url, headers=upload_headers, files=upload_files, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            
            if res_data.get("code") != 0:
                logging.error(f"Ошибка загрузки файла в хранилище Coze: {res_data.get('msg')}")
                return False
                
            file_id = res_data["data"]["id"]
            logging.info(f"Файл успешно загружен в Coze, получен ID: {file_id}")
            
        # Шаг 2: Привязываем загруженный файл к нашей базе знаний (Dataset)
        create_url = "https://api.coze.com/open_api/v1/dataset/document/create"
        create_headers = {
            "Authorization": f"Bearer {COZE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        create_payload = {
            "dataset_id": COZE_DATASET_ID,
            "document_bases": [
                {
                    "name": filename,
                    "source_info": {
                        "type": 1,  # 1 означает локальный файл
                        "file_id": file_id
                    }
                }
            ],
            "chunk_strategy": {
                "chunk_type": 0  # 0 означает автоматическое разбиение на чанки
            }
        }
        
        create_response = requests.post(create_url, headers=create_headers, json=create_payload, timeout=30)
        create_response.raise_for_status()
        create_res_data = create_response.json()
        
        if create_res_data.get("code") != 0:
            logging.error(f"Не удалось привязать файл к базе знаний Coze: {create_res_data.get('msg')}")
            return False
            
        logging.info(f"Файл {filename} успешно импортирован в базу знаний Coze!")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка интеграции с Coze для файла {filename}: {e}")
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
        date_match = re.search(r'del\s+(\d{2}/\d{2}/\d{4})', meta_text, re.IGNORECASE)
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
        
        download_success, is_new = download_file(pdf_url, pdf_path)
        
        if download_success and is_new:
            md_content = f"""# Risposta n. {num} del {date_str}
**Data:** {date_str}  
**Numero:** {num}  
**Anno:** {year_str}  

### Descrizione:
{clean_title}

### Link:
* [Original PDF]({pdf_url})
"""
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
            # Загружаем ТОЛЬКО текстовый карточку (.md) в базу знаний Coze
            upload_to_coze(md_path)

def main():
    logging.info("Старт синхронизации с Coze...")
    years = parse_years()
    
    # Ограничиваемся только 2025 и 2026 годами (свежие данные)
    ALLOWED_YEARS = ['2025', '2026']
    filtered_years = [y for y in years if y[0] in ALLOWED_YEARS]
    
    for year_str, year_url in filtered_years:
        logging.info(f"=== Проверка {year_str} года ===")
        months = parse_months(year_url)
        for month_url in months:
            process_month_page(month_url, year_str)
            time.sleep(0.5)

if __name__ == "__main__":
    main()
