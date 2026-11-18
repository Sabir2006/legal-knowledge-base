import os
import json
import logging
import requests
import time
from pypdf import PdfReader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "https://sabir2006-legal-webui.hf.space")
OPEN_WEBUI_API_KEY = os.environ.get("OPEN_WEBUI_API_KEY", "sk-...")
OPEN_WEBUI_KNOWLEDGE_ID = os.environ.get("OPEN_WEBUI_KNOWLEDGE_ID", "2af088c1-bb62-4d0d-96b6-f7f16955a1ec") 


BACKUP_DIR = "backup"
STATE_FILE = "processed_files.json"

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

def extract_text_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)
    except Exception as e:
        logging.error(f"Не удалось прочитать Word-файл {docx_path}: {e}")
        return ""

def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text_chunks = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                clean_page_text = page_text.replace('\xa0', ' ').replace('\xad', '-')
                text_chunks.append(clean_page_text)
        return "\n".join(text_chunks)
    except Exception as e:
        logging.error(f"Не удалось извлечь текст из PDF {pdf_path}: {e}")
        return ""

def extract_text_general(filepath):
    filename = os.path.basename(filepath).lower()
    if filename.endswith('.txt') or filename.endswith('.md'):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Не удалось прочитать текстовый файл {filepath}: {e}")
            return ""
    elif filename.endswith('.docx'):
        return extract_text_from_docx(filepath)
    elif filename.endswith('.pdf'):
        return extract_text_from_pdf(filepath)
    return ""

def get_webui_files():
    base_url = OPEN_WEBUI_URL.rstrip('/')
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    
    all_files = []
    page = 1
    
    logging.info("Считывание базы файлов (пролистываем страницы)...")
    
    while True:
        # Запрашиваем по страницам
        url = f"{base_url}/api/v1/files/?page={page}&limit=50"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            res_data = response.json()
            
            items = []
            if isinstance(res_data, list):
                items = res_data
            elif isinstance(res_data, dict):
                items = res_data.get("items", []) or res_data.get("data", []) or res_data.get("files", [])
                
            if not items:
                break
                
            all_files.extend(items)
            
            # Если на странице вернулось меньше 50 файлов, значит это была последняя страница!
            if len(items) < 50:
                break
                
            page += 1
            
            # Защитный лимит на 100 страниц, чтобы не зациклиться
            if page > 100:
                break
                
        except Exception as e:
            logging.error(f"Ошибка при чтении страницы {page}: {e}")
            break
            
    return all_files

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
    logging.info(f"Отправка обработанного {filename} обратно в Open WebUI...")
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
    logging.info("=== Старт ЛЕГКОГО процессора файлов Open WebUI ===")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    state = {}  # load_state() - принудительно игнорируем историю!
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
            if "id" in raw_files:
                files_list = [raw_files]
            else:
                logging.error(f"Неподдерживаемый формат ответа от сервера. Доступные ключи: {list(raw_files.keys())}")
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
            
        allowed_extensions = (".pdf", ".docx", ".txt", ".md")
        if not filename.lower().endswith(allowed_extensions):
            continue
            
        logging.info(f"Найдено новое пользовательское сырье: {filename}")
        
        local_path = os.path.join(BACKUP_DIR, filename)
        if download_file_from_webui(file_id, local_path):
            extracted_text = extract_text_general(local_path)
            
            # Если это отсканированный PDF (мало текста), мы его пропускаем!
            # Его обработает наш тяжелый OCR-скрипт.
            if filename.lower().endswith(".pdf") and len(extracted_text.strip()) < 200:
                logging.info(f"Файл {filename} похож на скан. Пропускаем его для обработки через OCR-скрипт.")
                # Удаляем скачанный пустой скан, чтобы не захламлять папку
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                continue
            
            clean_filename = filename.rsplit(".", 1)[0]
            md_filename = clean_filename + ".md"
            md_path = os.path.join(BACKUP_DIR, md_filename)
            
            md_content = f"""# {filename}
**ID исходного файла в WebUI:** {file_id}

### Полное текстовое содержание документа:
{extracted_text}
"""
            with open(md_path, 'w', encoding='utf-8') as md_f:
                md_f.write(md_content)
            logging.info(f"Создана текстовая .md версия: {md_filename}")
            
            new_md_id = upload_to_open_webui(md_path)
            if new_md_id:
                state[file_id] = {
                    "filename": filename,
                    "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "generated_md_id": new_md_id,
                    "type": "standard"
                }
                processed_count += 1
                
    save_state(state)
    logging.info(f"Легкая обработка завершена. Добавлено новых документов: {processed_count}")

if __name__ == "__main__":
    main()