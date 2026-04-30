import hashlib
import secrets
import time
from datetime import datetime
from typing import Tuple

def format_bytes(b: float) -> str:
    """Форматирование байт в читаемый вид"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if b < 1024:
            return f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} ПБ'

def generate_unique_id(username: str, name: str) -> str:
    """Генерация уникального ID"""
    data = f'{username}_{name}_{time.time()}_{secrets.token_hex(4)}'
    return hashlib.sha256(data.encode()).hexdigest()[:12]

def format_timestamp(timestamp: float) -> str:
    """Форматирование временной метки"""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

def validate_username(username: str) -> Tuple[bool, str]:
    """Проверка валидности имени пользователя"""
    if not username or len(username) < 2 or len(username) > 32:
        return False, 'Имя пользователя должно быть от 2 до 32 символов'
    if not username.replace('_', '').isalnum():
        return False, 'Имя пользователя содержит недопустимые символы'
    return True, ''

def validate_password(password: str, min_length: int = 4) -> Tuple[bool, str]:
    """Проверка валидности пароля"""
    if len(password) < min_length:
        return False, f'Пароль должен быть не менее {min_length} символов'
    return True, ''

def get_base_username(username: str) -> str:
    """Получение базового имени пользователя"""
    return username.replace('_listener', '')