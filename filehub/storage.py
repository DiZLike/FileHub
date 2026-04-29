"""
Управление хранением данных
"""

import os
import json
from datetime import datetime

class DataStorage:
    """Менеджер хранения данных"""
    
    def __init__(self, config, logger):
        """
        Инициализация хранилища данных
        
        Аргументы:
            config: конфигурация сервера
            logger: система логирования
        """
        self.shares_file = config.shares_config['storage_file']
        self.users_file = config.shares_config['users_file']
        self.logger = logger
        self.shares = {}
        self.users = {}
        self.stats = {
            'total_connections': 0,
            'total_shares': 0,
            'total_downloads': 0,
            'total_bytes_transferred': 0
        }
        
        # Создаем директории для файлов данных
        self._ensure_directories()
        
        self.load_users()
        self.load_shares()
    
    def _ensure_directories(self):
        """Создание необходимых директорий для файлов данных"""
        for file_path in [self.shares_file, self.users_file]:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                try:
                    os.makedirs(directory, exist_ok=True)
                    self.logger.log('INFO', f'Создана директория: {directory}')
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка создания директории {directory}: {e}')
    
    def load_users(self):
        """Загрузка пользователей из файла"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                self.logger.log('INFO', f'Загружено {len(self.users)} пользователей')
            except Exception as e:
                self.logger.log('ERROR', f'Ошибка загрузки пользователей: {e}')
                self.users = {}
    
    def save_users(self):
        """Сохранение пользователей в файл"""
        try:
            # Проверяем существование директории перед сохранением
            directory = os.path.dirname(self.users_file)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            data = {
                'users': self.users,
                'last_saved': datetime.now().isoformat(),
                'total_users': len(self.users)
            }
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка сохранения пользователей: {e}')
    
    def load_shares(self):
        """Загрузка раздач из файла"""
        if os.path.exists(self.shares_file):
            try:
                with open(self.shares_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.shares = data.get('shares', {})
                    self.stats = data.get('stats', self.stats)
                
                # Инициализация статуса онлайн
                for share in self.shares.values():
                    share['owner_online'] = False
                
                self.logger.log('INFO', f'Загружено {len(self.shares)} раздач')
            except Exception as e:
                self.logger.log('ERROR', f'Ошибка загрузки раздач: {e}')
                self.shares = {}
    
    def save_shares(self):
        """Сохранение раздач в файл"""
        try:
            # Проверяем существование директории перед сохранением
            directory = os.path.dirname(self.shares_file)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            data = {
                'shares': self.shares,
                'stats': self.stats,
                'last_saved': datetime.now().isoformat(),
                'total_shares': len(self.shares)
            }
            with open(self.shares_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка сохранения раздач: {e}')
    
    def validate_shares(self, inactive_timeout):
        """
        Валидация раздач при загрузке
        
        Аргументы:
            inactive_timeout: таймаут неактивности
        """
        current_time = __import__('time').time()
        to_remove = []
        
        for share_id, share in self.shares.items():
            # Проверяем обязательные поля
            if 'username' not in share or 'name' not in share:
                to_remove.append(share_id)
                continue
            
            # Проверяем таймаут неактивности
            if current_time - share.get('last_seen', 0) > inactive_timeout:
                to_remove.append(share_id)
        
        for share_id in to_remove:
            del self.shares[share_id]
            self.logger.log('INFO', f'Удалена устаревшая раздача при загрузке: {share_id}')
        
        if to_remove:
            self.save_shares()