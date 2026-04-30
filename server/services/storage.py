import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

class DataStorage:
    """Менеджер хранения данных"""
    
    def __init__(self, config, logger):
        self._shares_file = config.shares.storage_file
        self._users_file = config.shares.users_file
        self._logger = logger
        self.shares: Dict = {}
        self.users: Dict = {}
        self.stats = {
            'total_connections': 0,
            'total_shares': 0,
            'total_downloads': 0,
            'total_bytes_transferred': 0
        }
        
        self._ensure_directories()
        self.load_users()
        self.load_shares()
    
    def _ensure_directories(self):
        """Создание необходимых директорий"""
        for file_path in (self._shares_file, self._users_file):
            directory = os.path.dirname(file_path)
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
    
    def load_users(self):
        """Загрузка пользователей из файла"""
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, 'r', encoding='utf-8') as f:
                    self.users = json.load(f).get('users', {})
                self._logger.log('INFO', f'Загружено {len(self.users)} пользователей')
            except Exception as e:
                self._logger.log('ERROR', f'Ошибка загрузки пользователей: {e}')
                self.users = {}
    
    def save_users(self):
        """Сохранение пользователей в файл"""
        try:
            directory = os.path.dirname(self._users_file)
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
            
            with open(self._users_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'users': self.users,
                    'last_saved': datetime.now().isoformat(),
                    'total_users': len(self.users)
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка сохранения пользователей: {e}')
    
    def load_shares(self):
        """Загрузка раздач из файла"""
        if os.path.exists(self._shares_file):
            try:
                with open(self._shares_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.shares = data.get('shares', {})
                    self.stats = data.get('stats', self.stats)
                
                for share in self.shares.values():
                    share['owner_online'] = False
                
                self._logger.log('INFO', f'Загружено {len(self.shares)} раздач')
            except Exception as e:
                self._logger.log('ERROR', f'Ошибка загрузки раздач: {e}')
                self.shares = {}
    
    def save_shares(self):
        """Сохранение раздач в файл"""
        try:
            directory = os.path.dirname(self._shares_file)
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
            
            with open(self._shares_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'shares': self.shares,
                    'stats': self.stats,
                    'last_saved': datetime.now().isoformat(),
                    'total_shares': len(self.shares)
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка сохранения раздач: {e}')
    
    def validate_shares(self, inactive_timeout: int):
        """Валидация раздач при загрузке"""
        import time
        current_time = time.time()
        to_remove = []
        
        for share_id, share in self.shares.items():
            if 'username' not in share or 'name' not in share:
                to_remove.append(share_id)
            elif current_time - share.get('last_seen', 0) > inactive_timeout:
                to_remove.append(share_id)
        
        for share_id in to_remove:
            del self.shares[share_id]
            self._logger.log('INFO', f'Удалена устаревшая раздача: {share_id}')
        
        if to_remove:
            self.save_shares()