import hashlib
import ipaddress
import os
import secrets
from typing import Optional

class SecurityManager:
    """Менеджер безопасности"""
    
    def __init__(self, security_config):
        self._local_only = security_config.local_only
        self._allowed_ips = security_config.allowed_ips
        self._blocked_ips = security_config.blocked_ips
        self._blocked_extensions = security_config.blocked_extensions
        self.password_min_length = security_config.password_min_length
        self.require_password = security_config.require_password
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """Проверка, разрешён ли IP-адрес"""
        try:
            ip = ipaddress.ip_address(ip_address)
            
            if self._local_only and not ip.is_loopback:
                return False
            
            for blocked in self._blocked_ips:
                if (isinstance(blocked, ipaddress.IPv4Network) and ip in blocked) or ip == blocked:
                    return False
            
            if self._allowed_ips:
                for allowed in self._allowed_ips:
                    if (isinstance(allowed, ipaddress.IPv4Network) and ip in allowed) or ip == allowed:
                        return True
                return False
            
            return True
        except ValueError:
            return False
    
    def is_extension_allowed(self, filename: str) -> bool:
        """Проверка, разрешено ли расширение файла"""
        if not self._blocked_extensions:
            return True
        ext = os.path.splitext(filename)[1].lower()
        return ext not in self._blocked_extensions
    
    def hash_password(self, password: str, salt: Optional[str] = None) -> str:
        """Хеширование пароля с солью"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        key = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000
        )
        return f'{salt}:{key.hex()}'
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        try:
            salt, key = password_hash.split(':')
            new_key = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000
            )
            return key == new_key.hex()
        except Exception:
            return False