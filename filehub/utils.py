"""
Вспомогательные утилиты
"""

import os
import hashlib
import secrets
import time
from datetime import datetime

class Utils:
    """Вспомогательные функции"""
    
    @staticmethod
    def format_bytes(b):
        """
        Форматирование байт в читаемый вид
        
        Аргументы:
            b: количество байт
            
        Возвращает:
            отформатированная строка
        """
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if b < 1024:
                return f'{b:.1f} {unit}'
            b /= 1024
        return f'{b:.1f} ПБ'
    
    @staticmethod
    def generate_unique_id(username, name):
        """
        Генерация уникального ID
        
        Аргументы:
            username: имя пользователя
            name: имя раздачи
            
        Возвращает:
            уникальный идентификатор
        """
        data = f'{username}_{name}_{time.time()}_{secrets.token_hex(4)}'
        return hashlib.sha256(data.encode()).hexdigest()[:12]
    
    @staticmethod
    def format_timestamp(timestamp):
        """
        Форматирование временной метки
        
        Аргументы:
            timestamp: временная метка Unix
            
        Возвращает:
            отформатированная дата/время
        """
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def validate_username(username):
        """
        Проверка валидности имени пользователя
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            (валидность, сообщение об ошибке)
        """
        if not username or len(username) < 2 or len(username) > 32:
            return False, 'Имя пользователя должно быть от 2 до 32 символов'
        if not username.replace('_', '').isalnum():
            return False, 'Имя пользователя содержит недопустимые символы'
        return True, ''
    
    @staticmethod
    def validate_password(password, min_length=4):
        """
        Проверка валидности пароля
        
        Аргументы:
            password: пароль
            min_length: минимальная длина
            
        Возвращает:
            (валидность, сообщение об ошибке)
        """
        if len(password) < min_length:
            return False, f'Пароль должен быть не менее {min_length} символов'
        return True, ''
    
    @staticmethod
    def get_base_username(username):
        """
        Получение базового имени пользователя
        
        Аргументы:
            username: полное имя пользователя
            
        Возвращает:
            базовое имя
        """
        return username.replace('_listener', '')