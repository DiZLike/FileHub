"""
Вспомогательные утилиты клиента
"""

import hashlib
import json
import os
from pathlib import Path

class Utils:
    """Вспомогательные функции"""
    
    @staticmethod
    def format_size(size):
        """
        Форматирование размера в читаемый вид
        
        Аргументы:
            size: размер в байтах
            
        Возвращает:
            отформатированная строка
        """
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} ПБ'
    
    @staticmethod
    def hash_password(password):
        """
        Хеширование пароля для локального хранения
        
        Аргументы:
            password: пароль
            
        Возвращает:
            хеш пароля
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    @staticmethod
    def format_progress(current, total, prefix=''):
        """
        Форматирование прогресса
        
        Аргументы:
            current: текущее значение
            total: общее значение
            prefix: префикс строки
            
        Возвращает:
            отформатированная строка прогресса
        """
        percent = (current / total) * 100 if total > 0 else 0
        current_str = Utils.format_size(current)
        total_str = Utils.format_size(total)
        return f'{prefix} {current_str} / {total_str} ({percent:.1f}%)'
    
    @staticmethod
    def ensure_dir(directory):
        """
        Создание директории, если не существует
        
        Аргументы:
            directory: путь к директории
        """
        os.makedirs(directory, exist_ok=True)
    
    @staticmethod
    def safe_remove(path):
        """
        Безопасное удаление файла
        
        Аргументы:
            path: путь к файлу
        """
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    
    @staticmethod
    def get_file_list(folder_path):
        """
        Получение списка файлов в папке рекурсивно
        
        Аргументы:
            folder_path: путь к папке
            
        Возвращает:
            (список файлов, общий размер)
        """
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
    
    @staticmethod
    def clear_console():
        """Очистка консоли"""
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def get_terminal_width():
        """Получение ширины терминала"""
        try:
            return os.get_terminal_size().columns
        except:
            return 80