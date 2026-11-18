import os
import json
import logging
import requests
import time
import fitz  # PyMuPDF
import easyocr

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "https://sabir2006-legal-webui.hf.space")
OPEN_WEBUI_API_KEY = os.environ.get("OPEN_WEBUI_API_KEY", "sk-...")
OPEN_WEBUI_KNOWLEDGE_ID = os.environ.get("OPEN_WEBUI_KNOWLEDGE_ID", "2af088c1-bb62-4d0d-96b6-f7f16955a1ec")

BACKUP_DIR = "backup"
STATE_FILE = "processed_files.json"  # Историю ведем в одном файле, чтобы скрипты не мешали друг другу!

_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        logging.info("Инициализация нейросети EasyOCR (модели IT/EN)...")
        _ocr_reader = easyocr.Reader(['it', 'en'])
    return _ocr_reader

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def extract_text_from_scanned_pdf(pdf_path):
    logging.info(f"Запуск распознавания ИИ для сканированного PDF: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
        ocr_reader = get_ocr_reader()
        text_pages = []
        
        for page_num in range(len(doc)):
            logging.info(f"Распознавание ИИ: страница {page_num + 1} из {len(doc)}...")
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=150)
            img_data = pix.tobytes("png")
            
            result = ocr_reader.readtext(img_data, detail=0)
            page_text = " ".join(result)
            
            # Чистим символы переносов и спецсимволы
            clean_page_text = page_text.replace('\xa0', ' ').replace('\xad', '-')
            text_pages.append(clean_page_text)
            
        return "\n\n".join(text_pages)
    except Exception as e:
        logging.error(f"Ошибка ИИ-распознавания для {pdf_path}: {e}")
        return ""

def get_webui_files():
    base_url = OPEN_WEBUI_URL.rstrip('/')
    url = f"{base_url}/api/v1/files/"
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Ошибка получения списка файлов: {e}")
        return []

def download_file_from_webui(file_id, save_path):
    base_url = OPEN_WEBUI_URL.rstrip('/')
    url = f"{base_url}/api/v1/files/{file_id}/content"
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logging.error(f"Ошибка скачивания файла {file_id}: {e}")
        return False

def upload_to_open_webui(filepath):
    filename = os.path.basename(filepath)
    logging.info(f"Отправка распознанного файла {filename} обратно в Open WebUI...")
    base_url = OPEN_WEBUI_URL.rstrip('/')
    upload_url = f"{base_url}/api/v1/files/"
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    try:
        with open(filepath, 'rb') as f:
            files = {
                'file': (filename, f, 'text/markdown')
            }
            response = requests.post(upload_url, headers=headers, files=files, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            file_id = res_data.get("id")
            logging.info(f"Файл {filename} успешно импортирован обратно.")
            
        if OPEN_WEBUI_KNOWLEDGE_ID and file_id:
            link_url = f"{base_url}/api/v1/knowledge/{OPEN_WEBUI_KNOWLEDGE_ID}/file/add"
            link_headers = {
                "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}",
                "Content-Type": "application/json"
            }
            link_payload = {"file_id": file_id}
            link_response = requests.post(link_url, headers=link_headers, json=link_payload, timeout=30)
            link_response.raise_for_status()
            logging.info(f"Файл {filename} успешно добавлен в базу знаний Knowledge!")
            
        return file_id
    except Exception as e:
        logging.error(f"Ошибка отправки/привязки файла {filename}")
        return None

def main():
    logging.info("=== Старт ТЯЖЕЛОГО OCR-процессора файлов Open WebUI (Только для сканов) ===")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    state = load_state()
    raw_files = get_webui_files()
    
    files_list = []
    if isinstance(raw_files, list):
        files_list = raw_files
    elif isinstance(raw_files, dict):
        if "items" in raw_files and isinstance(raw_files["items"], list):
            files_list = raw_files["items"]
        elif "data" in raw_files and isinstance(raw_files["data"], list):
            files_list = raw_files["data"]
        elif "files" in raw_files and isinstance(raw_files["files"], list):
            files_list = raw_files["files"]
        elif "list" in raw_files and isinstance(raw_files["list"], list):
            files_list = raw_files["list"]
        else:
            logging.error(f"Неподдерживаемый формат ответа от сервера. Ключи: {list(raw_files.keys())}")
            return

    processed_count = 0
    logging.info(f"Всего файлов обнаружено на сервере: {len(files_list)}")
    
    for f_info in files_list:
        if not isinstance(f_info, dict):
            continue
            
        file_id = f_info.get("id")
        filename = f_info.get("filename")
        
        if not file_id or not filename:
            continue
            
        if filename.startswith("Risposta_"):
            continue
            
        if file_id in state:
            continue
            
        # Нас интересуют ТОЛЬКО PDF (потому что сканы бывают только в PDF-формате)
        if not filename.lower().endswith(".pdf"):
            continue
            
        logging.info(f"Анализ PDF-скана: {filename}")
        
        local_path = os.path.join(BACKUP_DIR, filename)
        if download_file_from_webui(file_id, local_path):
            
            # Запускаем тяжелое распознавание ИИ
            extracted_text = extract_text_from_scanned_pdf(local_path)
            
            clean_filename = filename.rsplit(".", 1)[0]
            md_filename = clean_filename + "_OCR.md"  # Помечаем файл меткой OCR
            md_path = os.path.join(BACKUP_DIR, md_filename)
            
            md_content = f"""# {filename} (Распознано через ИИ-OCR)
**ID исходного скана в WebUI:** {file_id}

### Полное текстовое содержание скана (распознано через ИИ):
{extracted_text}
"""
            with open(md_path, 'w', encoding='utf-8') as md_f:
                md_f.write(md_content)
            logging.info(f"Создан текстовый .md бэкап (с OCR): {md_filename}")
            
            new_md_id = upload_to_open_webui(md_path)
            if new_md_id:
                state[file_id] = {
                    "filename": filename,
                    "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "generated_md_id": new_md_id,
                    "type": "ocr"
                }
                processed_count += 1
                
    save_state(state)
    logging.info(f"OCR-обработка завершена. Успешно распознано и добавлено сканов: {processed_count}")

if __name__ == "__main__":
    main()