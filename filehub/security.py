"""
Модуль безопасности
"""

import ipaddress
import os
import hashlib
import secrets

class SecurityManager:
    """Менеджер безопасности"""
    
    def __init__(self, config):
        """
        Инициализация менеджера безопасности
        
        Аргументы:
            config: конфигурация сервера
        """
        self.local_only = config.security_config['local_only']
        self.allowed_ips = config.security_config['allowed_ips']
        self.blocked_ips = config.security_config['blocked_ips']
        self.blocked_extensions = config.security_config['blocked_extensions']
        self.password_min_length = config.security_config['password_min_length']
        self.require_password = config.security_config['require_password']
    
    def is_ip_allowed(self, ip_address):
        """
        Проверка, разрешён ли IP-адрес
        
        Аргументы:
            ip_address: IP-адрес для проверки
            
        Возвращает:
            True если разрешён, иначе False
        """
        try:
            ip = ipaddress.ip_address(ip_address)
            
            if self.local_only and not ip.is_loopback:
                return False
            
            # Проверка заблокированных IP
            for blocked in self.blocked_ips:
                if isinstance(blocked, ipaddress.ip_network):
                    if ip in blocked:
                        return False
                elif ip == blocked:
                    return False
            
            # Проверка разрешенных IP
            if self.allowed_ips:
                for allowed in self.allowed_ips:
                    if isinstance(allowed, ipaddress.ip_network):
                        if ip in allowed:
                            return True
                    elif ip == allowed:
                        return True
                return False
            
            return True
        except ValueError:
            return False
    
    def is_extension_allowed(self, filename):
        """
        Проверка, разрешено ли расширение файла
        
        Аргументы:
            filename: имя файла
            
        Возвращает:
            True если расширение разрешено
        """
        if not self.blocked_extensions:
            return True
        ext = os.path.splitext(filename)[1].lower()
        return ext not in self.blocked_extensions
    
    def hash_password(self, password, salt=None):
        """
        Хеширование пароля с солью
        
        Аргументы:
            password: пароль
            salt: соль (генерируется если не указана)
            
        Возвращает:
            хеш пароля в формате соль:хеш
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return salt + ':' + key.hex()
    
    def verify_password(self, password, password_hash):
        """
        Проверка пароля
        
        Аргументы:
            password: пароль для проверки
            password_hash: сохранённый хеш
            
        Возвращает:
            True если пароль верный
        """
        try:
            salt, key = password_hash.split(':')
            new_key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return key == new_key.hex()
        except Exception:
            return False