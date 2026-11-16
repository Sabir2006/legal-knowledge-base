import os
import re
import time
import logging
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://www.agenziaentrate.gov.it/portale/normativa-e-prassi/risposte-agli-interpelli/interpelli/archivio-interpelli"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

MONTHS_IT = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 
             'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']

def get_soup(url):
    logging.info(f"Запрос страницы: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        logging.error(f"Не удалось загрузить {url}: {e}")
        return None

def download_file(url, filepath):
    if os.path.exists(filepath):
        logging.info(f"Файл уже существует, пропуск: {filepath}")
        return True
    
    logging.info(f"Скачивание PDF: {url} -> {filepath}")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        response = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # Небольшая задержка, чтобы не перегружать сервер
        time.sleep(0.5)
        return True
    except Exception as e:
        logging.error(f"Ошибка при скачивании PDF {url}: {e}")
        return False

def parse_years():
    soup = get_soup(BASE_URL)
    if not soup:
        return []
        
    year_links = []
    anchors = soup.find_all('a')
    for a in anchors:
        href = a.get('href')
        text = a.get_text(strip=True)
        if href and ('interpelli-20' in href or '/portale/interpelli-20' in href):
            year_match = re.search(r'20\d{2}', text)
            if not year_match:
                year_match = re.search(r'20\d{2}', href)
            
            if year_match:
                year = year_match.group(0)
                full_url = urljoin(BASE_URL, href)
                year_links.append((year, full_url))
                
    # Сортируем по убыванию годов (сначала новые)
    year_links.sort(key=lambda x: x[0], reverse=True)
    return year_links

def parse_months(year_url):
    soup = get_soup(year_url)
    if not soup:
        return []
        
    month_links = []
    anchors = soup.find_all('a')
    for a in anchors:
        href = a.get('href')
        text = a.get_text(strip=True)
        if not href:
            continue
            
        text_lower = text.lower()
        has_month = any(m in text_lower for m in MONTHS_IT)
        is_valid_link = any(kw in href.lower() for kw in ['interpelli', 'risposte-interpello', 'giugno-2019', '/portale/'])
        
        if has_month and is_valid_link:
            full_url = urljoin(year_url, href)
            month_links.append(full_url)
            
    # Убираем дубликаты
    seen = set()
    unique_months = []
    for m in month_links:
        if m not in seen:
            seen.add(m)
            unique_months.append(m)
            
    return unique_months

def process_month_page(month_url, year_str):
    soup = get_soup(month_url)
    if not soup:
        return
    
    divs = soup.find_all('div', class_='indcart_gn')
    logging.info(f"Найдено {len(divs)} документов на странице {month_url}")
    
    for div in divs:
        # Извлекаем метаданные документа (Номер ответа и дату)
        strong_tag = div.find('strong')
        if not strong_tag:
            continue
        meta_text = strong_tag.get_text(strip=True)
        
        # Находим ссылку на PDF
        a_tag = div.find('a')
        if not a_tag or not a_tag.get('href'):
            continue
            
        pdf_href = a_tag['href']
        pdf_url = urljoin(month_url, pdf_href)
        raw_title = a_tag.get_text(strip=True)
        
        # Парсим Номер и Дату из метаданных (например, "Risposta n. 18 del 31/01/2025")
        num_match = re.search(r'n\.\s*(\d+)', meta_text, re.IGNORECASE)
        date_match = re.search(r'del\s+(\d{2}/\d{2}/\d{4})', meta_text, re.IGNORECASE)
        
        num = num_match.group(1) if num_match else "unknown"
        date_str = date_match.group(1) if date_match else "unknown"
        
        # Чистим заголовок
        clean_title = re.sub(r'\s+', ' ', raw_title).strip()
        if clean_title.lower().endswith('- pdf'):
            clean_title = clean_title[:-5].strip()
        elif clean_title.lower().endswith('-pdf'):
            clean_title = clean_title[:-4].strip()
            
        # Формируем пути сохранения
        pdf_filename = f"Risposta_{num}.pdf"
        md_filename = f"Risposta_{num}.md"
        
        year_dir = os.path.join("interpelli", year_str)
        pdf_path = os.path.join(year_dir, pdf_filename)
        md_path = os.path.join(year_dir, md_filename)
        
        # Скачиваем PDF
        download_success = download_file(pdf_url, pdf_path)
        
        # Если скачалось успешно (или файл уже был), пишем/обновляем .md файл с метаданными
        if download_success:
            md_content = f"""# Risposta n. {num} del {date_str}

**Дата:** {date_str}  
**Номер:** {num}  
**Год архива:** {year_str}  

### Описание / Юридическое содержание:
{clean_title}

### Документ:
* [Локальный PDF файл]({pdf_filename})
* [Ссылка на оригинальный PDF]({pdf_url})
"""
            os.makedirs(year_dir, exist_ok=True)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
def main():
    logging.info("Запуск парсера Interpelli...")
    years = parse_years()
    logging.info(f"Найдено годов в архиве: {[y[0] for y in years]}")
    
    for year_str, year_url in years:
        logging.info(f"=== Обработка {year_str} года ===")
        months = parse_months(year_url)
        logging.info(f"Найдено {len(months)} месяцев для {year_str}")
        
        for month_url in months:
            process_month_page(month_url, year_str)
            # Небольшая пауза между страницами месяцев
            time.sleep(1.0)

if __name__ == "__main__":
    main()