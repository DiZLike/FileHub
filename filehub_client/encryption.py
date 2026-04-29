"""
Модуль шифрования для клиента FileHub
Ключи генерируются на лету, не сохраняются
"""

import base64
import secrets
import struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

class ClientEncryption:
    """Менеджер шифрования клиента"""
    
    def __init__(self):
        """Инициализация шифрования клиента"""
        self.enabled = False
        self.algorithm = None
    
    def enable(self, encryption_params):
        """
        Включение шифрования с параметрами от сервера
        
        Аргументы:
            encryption_params: параметры шифрования от сервера
            
        Возвращает:
            True если шифрование включено
        """
        if encryption_params and encryption_params.get('enabled'):
            self.enabled = True
            self.algorithm = encryption_params.get('algorithm', 'AES-256-GCM')
            return True
        return False
    
    def encrypt_file_data(self, data, session_key_b64):
        """
        Шифрование данных файла
        
        Аргументы:
            data: данные для шифрования (bytes)
            session_key_b64: сессионный ключ в base64
            
        Возвращает:
            (длина_данных + nonce + encrypted_data) или None при ошибке
        """
        if not self.enabled:
            return data
        
        try:
            session_key = base64.b64decode(session_key_b64)
            aesgcm = AESGCM(session_key)
            
            # Генерируем уникальный nonce (12 байт для GCM)
            nonce = secrets.token_bytes(12)
            
            # Шифруем данные
            encrypted_data = aesgcm.encrypt(nonce, data, None)
            
            # Формируем пакет: [4 байта длина оригинальных данных][12 байт nonce][зашифрованные данные]
            original_length = len(data)
            length_bytes = struct.pack('!I', original_length)
            
            return length_bytes + nonce + encrypted_data
            
        except Exception as e:
            print(f'[ERROR] Ошибка шифрования: {e}')
            return None
    
    def decrypt_file_data(self, data, session_key_b64):
        """
        Расшифровка данных файла
        
        Аргументы:
            data: [4 байта длина][12 байт nonce][зашифрованные данные]
            session_key_b64: сессионный ключ в base64
            
        Возвращает:
            расшифрованные данные или None при ошибке
        """
        if not self.enabled:
            return data
        
        try:
            session_key = base64.b64decode(session_key_b64)
            aesgcm = AESGCM(session_key)
            
            # Извлекаем длину оригинальных данных (первые 4 байта)
            if len(data) < 4:
                print('[ERROR] Данные слишком короткие (заголовок длины)')
                return None
            
            original_length = struct.unpack('!I', data[:4])[0]
            
            # Извлекаем nonce (следующие 12 байт)
            if len(data) < 16:  # 4 заголовок + 12 nonce
                print('[ERROR] Данные слишком короткие (nonce)')
                return None
            
            nonce = data[4:16]
            ciphertext = data[16:]
            
            # Расшифровываем
            decrypted_data = aesgcm.decrypt(nonce, ciphertext, None)
            
            # Проверяем длину
            if len(decrypted_data) != original_length:
                print(f'[WARN] Длина расшифрованных данных ({len(decrypted_data)}) не совпадает с ожидаемой ({original_length})')
            
            return decrypted_data
            
        except Exception as e:
            print(f'[ERROR] Ошибка расшифровки: {e}')
            return None
    
    def get_encrypted_chunk_size(self, original_size):
        """
        Получение размера зашифрованного чанка
        
        Аргументы:
            original_size: размер оригинальных данных
            
        Возвращает:
            размер зашифрованного пакета
        """
        if not self.enabled:
            return original_size
        
        # 4 байта заголовок длины + 12 байт nonce + данные + 16 байт тег GCM
        return 4 + 12 + original_size + 16
    
    def is_enabled(self):
        """
        Проверка, включено ли шифрование
        
        Возвращает:
            True если шифрование включено
        """
        return self.enabled