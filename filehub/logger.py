"""
Система логирования
"""

import os
from datetime import datetime

class Logger:
    """Менеджер логирования"""
    
    LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3}
    
    def __init__(self, config):
        """
        Инициализация логгера
        
        Аргументы:
            config: конфигурация сервера
        """
        self.enabled = config.get_config('logging', 'enabled', 'true').lower() == 'true'
        self.log_file = config.get_config('logging', 'log_file', 'hub.log')
        self.log_level = config.get_config('logging', 'log_level', 'INFO').upper()
        self.log_transfers = config.get_config('logging', 'log_transfers', 'true').lower() == 'true'
        self.max_log_size = int(config.get_config('logging', 'max_log_size_mb', '10')) * 1024 * 1024
        
        self.stats = {
            'total_connections': 0,
            'total_shares': 0,
            'total_downloads': 0,
            'total_bytes_transferred': 0
        }
        
        # Создаем директорию для лог-файла при инициализации
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """Создание директории для лог-файла если её нет"""
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                print(f'Создана директория для логов: {log_dir}')
            except Exception as e:
                print(f'Ошибка создания директории для логов: {e}')
    
    def log(self, level, message):
        """
        Запись в лог
        
        Аргументы:
            level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
            message: сообщение для записи
        """
        if not self.enabled:
            return
        
        if self.LEVELS.get(level, 0) < self.LEVELS.get(self.log_level, 1):
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f'[{timestamp}] [{level}] {message}'
        print(log_message)
        
        try:
            self._rotate_log_if_needed()
            
            # Проверяем существование директории перед записью
            log_dir = os.path.dirname(self.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f'Ошибка записи в лог: {e}')
    
    def _rotate_log_if_needed(self):
        """Ротация лог-файла при превышении размера"""
        try:
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > self.max_log_size:
                archive_name = f'{self.log_file}.{datetime.now().strftime("%Y%m%d_%H%M%S")}.old'
                os.rename(self.log_file, archive_name)
        except Exception:
            pass
    
    def update_stat(self, stat_name, value=1):
        """
        Обновление статистики
        
        Аргументы:
            stat_name: название параметра статистики
            value: значение для добавления
        """
        if stat_name in self.stats:
            if stat_name == 'total_bytes_transferred':
                self.stats[stat_name] += value
            else:
                self.stats[stat_name] += value
    
    def get_stats(self):
        """
        Получение статистики
        
        Возвращает:
            копия словаря со статистикой
        """
        return self.stats.copy()