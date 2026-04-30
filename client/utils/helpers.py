import os
from pathlib import Path
from typing import Tuple, List

def format_size(size: int) -> str:
    """Форматирование размера в читаемый вид"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} ПБ'

def ensure_dir(directory: str):
    """Создание директории, если не существует"""
    os.makedirs(directory, exist_ok=True)

def safe_remove(path: str):
    """Безопасное удаление файла"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def get_file_list(folder_path) -> Tuple[List[dict], int]:
    """Получение списка файлов в папке рекурсивно"""
    files_list = []
    total_size = 0
    
    for file_path in Path(folder_path).rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(folder_path)
            file_size = file_path.stat().st_size
            files_list.append({
                'path': str(rel_path).replace('\\', '/'),
                'size': file_size
            })
            total_size += file_size
    
    return files_list, total_size