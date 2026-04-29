"""
Модуль шифрования для сервера FileHub
Ключи генерируются на лету, не сохраняются
"""

import base64
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

class EncryptionManager:
    """Менеджер шифрования сервера - координатор защищенной передачи"""
    
    def __init__(self, config, logger):
        """
        Инициализация менеджера шифрования
        
        Аргументы:
            config: конфигурация сервера
            logger: система логирования
        """
        self.config = config
        self.logger = logger
        self.enabled = self._is_enabled()
        
        # Хранилище сессионных ключей (только в памяти)
        self.session_keys = {}  # transfer_id -> {key, created_at}
    
    def _is_enabled(self):
        """Проверка, включено ли шифрование"""
        return self.config.get_config(
            'security', 
            'encryption_enabled', 
            'false'
        ).lower() == 'true'
    
    def get_encryption_params(self):
        """
        Получение параметров шифрования для клиентов
        
        Возвращает:
            словарь с параметрами или None
        """
        if not self.enabled:
            return None
        
        return {
            'enabled': True,
            'algorithm': 'AES-256-GCM',
            'key_exchange': 'server_generated'
        }
    
    def generate_session_key(self, transfer_id):
        """
        Генерация сессионного ключа AES-256
        
        Аргументы:
            transfer_id: ID трансфера
            
        Возвращает:
            сессионный ключ в base64
        """
        if not self.enabled:
            return None
        
        # Генерируем 256-битный ключ
        session_key = AESGCM.generate_key(bit_length=256)
        session_key_b64 = base64.b64encode(session_key).decode('utf-8')
        
        # Сохраняем ключ в памяти для второго участника
        self.session_keys[transfer_id] = {
            'key': session_key_b64,
            'created_at': datetime.now()
        }
        
        self.logger.log('DEBUG', 
            f'Сгенерирован сессионный ключ для трансфера {transfer_id}')
        
        return session_key_b64
    
    def get_session_key(self, transfer_id):
        """
        Получение сессионного ключа для получателя
        
        Аргументы:
            transfer_id: ID трансфера
            
        Возвращает:
            сессионный ключ в base64 или None
        """
        if not self.enabled or transfer_id not in self.session_keys:
            return None
        
        return self.session_keys[transfer_id]['key']
    
    def remove_session_key(self, transfer_id):
        """
        Удаление использованного сессионного ключа
        
        Аргументы:
            transfer_id: ID трансфера
        """
        if transfer_id in self.session_keys:
            del self.session_keys[transfer_id]
            self.logger.log('DEBUG', 
                f'Удален сессионный ключ для трансфера {transfer_id}')
    
    def cleanup_expired_keys(self):
        """
        Очистка просроченных сессионных ключей
        
        Возвращает:
            количество удаленных ключей
        """
        current_time = datetime.now()
        to_remove = []
        
        for transfer_id, session_data in self.session_keys.items():
            age = (current_time - session_data['created_at']).total_seconds()
            if age > 300:  # 5 минут
                to_remove.append(transfer_id)
        
        for transfer_id in to_remove:
            del self.session_keys[transfer_id]
            self.logger.log('DEBUG', 
                f'Удален просроченный сессионный ключ {transfer_id}')
        
        return len(to_remove)
    
    def get_stats(self):
        """
        Получение статистики шифрования
        
        Возвращает:
            словарь со статистикой
        """
        return {
            'enabled': self.enabled,
            'active_session_keys': len(self.session_keys)
        }