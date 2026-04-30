import os
from datetime import datetime
from pathlib import Path
from typing import Dict

class LogLevel:
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    
    _names = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3}
    
    @classmethod
    def from_string(cls, level: str) -> int:
        return cls._names.get(level.upper(), cls.INFO)

class ServerLogger:
    """Система логирования сервера"""
    
    def __init__(self, log_config: dict):
        self._enabled = log_config['enabled']
        self._log_file = log_config['log_file']
        self._log_level = LogLevel.from_string(log_config['log_level'])
        self._log_transfers = log_config['log_transfers']
        self._max_log_size = log_config['max_log_size_mb'] * 1024 * 1024
        
        self.stats = {
            'total_connections': 0,
            'total_shares': 0,
            'total_downloads': 0,
            'total_bytes_transferred': 0
        }
        
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """Создание директории для логов"""
        log_dir = os.path.dirname(self._log_file)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    def log(self, level: str, message: str):
        """Запись в лог"""
        if not self._enabled or LogLevel.from_string(level) < self._log_level:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f'[{timestamp}] [{level}] {message}'
        print(log_message)
        
        try:
            self._rotate_if_needed()
            log_dir = os.path.dirname(self._log_file)
            if log_dir:
                Path(log_dir).mkdir(parents=True, exist_ok=True)
            
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f'Ошибка записи в лог: {e}')
    
    def _rotate_if_needed(self):
        """Ротация лог-файла при превышении размера"""
        try:
            if os.path.exists(self._log_file) and os.path.getsize(self._log_file) > self._max_log_size:
                archive = f'{self._log_file}.{datetime.now().strftime("%Y%m%d_%H%M%S")}.old'
                os.rename(self._log_file, archive)
        except Exception:
            pass
    
    def update_stat(self, name: str, value: int = 1):
        """Обновление статистики"""
        if name in self.stats:
            self.stats[name] += value
    
    def get_stats(self) -> Dict:
        return self.stats.copy()