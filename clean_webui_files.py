import os
import json
import logging
import requests
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "https://sabir2006-legal-webui.hf.space")
OPEN_WEBUI_API_KEY = os.environ.get("OPEN_WEBUI_API_KEY", "sk-...")
KEEP_KNOWLEDGE_ID = os.environ.get("OPEN_WEBUI_KNOWLEDGE_ID", "2af088c1-bb62-4d0d-96b6-f7f16955a1ec")


def get_folder_file_ids(knowledge_id):
    base_url = OPEN_WEBUI_URL.rstrip('/')
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    folder_ids = set()
    page = 1
    
    logging.info(f"Reading files inside folder 'Interpelli' ({knowledge_id})...")
    
    while True:
        # Запрашиваем файлы конкретной папки постранично
        url = f"{base_url}/api/v1/knowledge/{knowledge_id}/files?page={page}&limit=50"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            # Если нужен слэш перед знаком вопроса, пробуем со слэшем
            if response.status_code == 404 or "text/html" in response.headers.get("Content-Type", ""):
                url = f"{base_url}/api/v1/knowledge/{knowledge_id}/files/?page={page}&limit=50"
                response = requests.get(url, headers=headers, timeout=15)
                
            if response.status_code != 200:
                logging.error(f"Folder files request status {response.status_code}: {response.text[:200]}")
                break
                
            res_data = response.json()
            items = []
            if isinstance(res_data, list):
                items = res_data
            elif isinstance(res_data, dict):
                items = res_data.get("items", []) or res_data.get("data", []) or res_data.get("files", [])
                
            if not items:
                break
                
            for f in items:
                if isinstance(f, dict):
                    fid = f.get("id") or f.get("file_id")
                    if fid:
                        folder_ids.add(fid)
                elif isinstance(f, str):
                    folder_ids.add(f)
                    
            if len(items) < 50:
                break
            page += 1
            if page > 100:
                break
        except Exception as e:
            logging.error(f"Error reading folder page {page}: {e}")
            break
            
    logging.info(f"Total files found inside 'Interpelli' folder: {len(folder_ids)}")
    return folder_ids

def get_all_webui_files():
    base_url = OPEN_WEBUI_URL.rstrip('/')
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    all_files = []
    page = 1
    
    logging.info("Fetching all files on the server...")
    while True:
        url = f"{base_url}/api/v1/files/?page={page}&limit=50"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logging.error(f"Server error {response.status_code}")
                break
                
            res_data = response.json()
            items = []
            if isinstance(res_data, list):
                items = res_data
            elif isinstance(res_data, dict):
                items = res_data.get("items", []) or res_data.get("data", []) or res_data.get("files", [])
                
            if not items:
                break
                
            all_files.extend(items)
            if len(items) < 50:
                break
            page += 1
            if page > 100:
                break
        except Exception as e:
            logging.error(f"Error reading server files page {page}: {e}")
            break
            
    return all_files

def delete_file_from_webui(file_id, filename):
    base_url = OPEN_WEBUI_URL.rstrip('/')
    url = f"{base_url}/api/v1/files/{file_id}"
    headers = {
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }
    try:
        response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info(f"Deleted: {filename} (ID: {file_id})")
        return True
    except Exception as e:
        logging.error(f"Failed to delete {filename}: {e}")
        return False

def format_size(size_bytes):
    if not size_bytes:
        return "0 B"
    size_bytes = int(size_bytes)
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def format_date(timestamp):
    if not timestamp:
        return "Unknown"
    try:
        return datetime.fromtimestamp(int(timestamp)).strftime('%d.%m.%Y %H:%M')
    except Exception:
        return "Unknown"

def main():
    logging.info("=== Start Cleaner ONLY BY PRESENCE IN 'Interpelli' FOLDER ===")
    
    if not OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY == "sk-...":
        logging.error("ERROR: Please replace 'sk-...' with your real API key on line 12!")
        return
        
    # 1. Получаем все ID файлов внутри папки Interpelli
    interpelli_file_ids = get_folder_file_ids(KEEP_KNOWLEDGE_ID)
    
    # ЖЕСТКИЙ ПРЕДОХРАНИТЕЛЬ: если не нашли файлы в папке, сразу выходим!
    if len(interpelli_file_ids) == 0:
        logging.error("SAFETY STOP: Could not load files from 'Interpelli' folder (0 files). Aborting!")
        return
        
    # 2. Получаем вообще все файлы на сервере
    all_files = get_all_webui_files()
    logging.info(f"Total files on server: {len(all_files)}")
    
    to_delete = []
    kept_count = 0
    
    for f_info in all_files:
        if not isinstance(f_info, dict):
            continue
        file_id = f_info.get("id")
        filename = f_info.get("filename")
        if not file_id or not filename:
            continue
            
        # ЕДИНСТВЕННОЕ ПРАВИЛО: если ID файла есть в папке Interpelli — НЕ ТРОГАЕМ!
        if file_id in interpelli_file_ids:
            kept_count += 1
            continue
            
        # Если ID файла НЕТ в папке Interpelli — добавляем в список на удаление
        size = int(f_info.get("size") or f_info.get("meta", {}).get("size", 0))
        created_at = int(f_info.get("created_at") or 0)
        
        to_delete.append({
            "id": file_id,
            "filename": filename,
            "size": size,
            "created_at": created_at
        })
        
    if not to_delete:
        logging.info("All server files are inside 'Interpelli'! Nothing to delete.")
        return
        
    print("\n" + "="*85)
    print(f"FILES NOT IN 'Interpelli' FOLDER (TO DELETE: {len(to_delete)} | PROTECTED IN FOLDER: {kept_count}):")
    print("="*85)
    
    total_bytes = 0
    show_limit = min(40, len(to_delete))
    for i in range(show_limit):
        item = to_delete[i]
        total_bytes += item["size"]
        size_str = format_size(item["size"])
        date_str = format_date(item["created_at"])
        print(f"[{i+1}] {item['filename']} | Size: {size_str} | Date: {date_str} | ID: {item['id']}")
        
    if len(to_delete) > 40:
        print(f"... and {len(to_delete) - 40} more files ...")
        for i in range(40, len(to_delete)):
            total_bytes += to_delete[i]["size"]
            
    print("="*85)
    print(f"TOTAL SIZE TO DELETE: {format_size(total_bytes)}")
    print(f"PROTECTED FILES IN 'Interpelli': {kept_count}")
    print("="*85 + "\n")
    
    confirm = input(f"Delete these {len(to_delete)} files that are NOT in 'Interpelli'? (type 'yes' to confirm): ")
    
    if confirm.lower().strip() == "yes":
        logging.info("Deleting files...")
        deleted_count = 0
        for item in to_delete:
            if delete_file_from_webui(item["id"], item["filename"]):
                deleted_count += 1
                time.sleep(0.05)
        logging.info(f"Done! Deleted: {deleted_count} | Kept safe in Interpelli: {kept_count}")
    else:
        logging.info("Cancelled. Nothing was deleted.")

if __name__ == "__main__":
    main()