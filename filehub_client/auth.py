"""
Аутентификация клиента
"""

import json
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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
        self._cipher = None
    
    def _get_cipher(self):
        """Создание или получение шифра для защиты паролей"""
        if self._cipher is None:
            # Используем ключ на основе имени компьютера (простая защита)
            import platform
            key_material = platform.node().encode()
            salt = b'filehub_salt_2024'
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_material))
            self._cipher = Fernet(key)
        return self._cipher
    
    def get_saved_password(self, username):
        """
        Получение сохранённого пароля
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            пароль или None
        """
        if not self.remember_password:
            return None
        
        try:
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
                    encrypted_password = data.get(username)
                    if encrypted_password:
                        cipher = self._get_cipher()
                        return cipher.decrypt(encrypted_password.encode()).decode()
        except Exception:
            pass
        return None
    
    def save_password(self, username, password):
        """
        Сохранение пароля в зашифрованном виде
        
        Аргументы:
            username: имя пользователя
            password: пароль
        """
        if not password or not self.remember_password:
            return
        
        try:
            data = {}
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
            
            # Шифруем пароль перед сохранением
            cipher = self._get_cipher()
            encrypted_password = cipher.encrypt(password.encode()).decode()
            data[username] = encrypted_password
            
            with open(self.password_hash_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    
    def has_saved_password(self, username):
        """
        Проверка наличия сохранённого пароля
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            True если пароль сохранён
        """
        if not self.remember_password:
            return False
        
        return self.get_saved_password(username) is not None
    
    def delete_saved_password(self, username):
        """
        Удаление сохранённого пароля
        
        Аргументы:
            username: имя пользователя
        """
        try:
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
                
                if username in data:
                    del data[username]
                    
                    with open(self.password_hash_file, 'w') as f:
                        json.dump(data, f)
        except Exception:
            pass