"""
Аутентификация клиента
"""

import json
import os
import hashlib
from utils import Utils

class AuthManager:
    """Менеджер аутентификации клиента"""
    
    def __init__(self, config):
        """
        Инициализация менеджера аутентификации
        
        Аргументы:
            config: конфигурация клиента
        """
        self.remember_password = config.security_config['remember_password']
        self.password_hash_file = config.security_config['password_hash_file']
    
    def get_saved_password_hash(self, username):
        """
        Получение сохранённого хеша пароля
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            хеш пароля или None
        """
        try:
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
                    return data.get(username)
        except Exception:
            pass
        return None
    
    def save_password_hash(self, username, password):
        """
        Сохранение хеша пароля
        
        Аргументы:
            username: имя пользователя
            password: пароль
        """
        if not password:
            return
        
        try:
            data = {}
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
            
            password_hash = Utils.hash_password(password)
            data[username] = password_hash
            
            with open(self.password_hash_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    
    def check_saved_password(self, username):
        """
        Проверка наличия сохранённого пароля
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            True если пароль сохранён
        """
        if not self.remember_password:
            return False
        
        saved_hash = self.get_saved_password_hash(username)
        return saved_hash is not None