import json
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class AuthManager:
    """Менеджер аутентификации клиента"""
    
    def __init__(self, config):
        self.remember_password = config.security.remember_password
        self.password_hash_file = config.security.password_hash_file
        self._cipher = None
    
    def _get_cipher(self):
        """Создание или получение шифра для защиты паролей"""
        if self._cipher is None:
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
    
    def get_saved_password(self, username: str) -> str:
        """Получение сохранённого пароля"""
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
    
    def save_password(self, username: str, password: str):
        """Сохранение пароля в зашифрованном виде"""
        if not password or not self.remember_password:
            return
        
        try:
            data = {}
            if os.path.exists(self.password_hash_file):
                with open(self.password_hash_file, 'r') as f:
                    data = json.load(f)
            
            cipher = self._get_cipher()
            encrypted_password = cipher.encrypt(password.encode()).decode()
            data[username] = encrypted_password
            
            with open(self.password_hash_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    
    def has_saved_password(self, username: str) -> bool:
        """Проверка наличия сохранённого пароля"""
        if not self.remember_password:
            return False
        return self.get_saved_password(username) is not None
    
    def delete_saved_password(self, username: str):
        """Удаление сохранённого пароля"""
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