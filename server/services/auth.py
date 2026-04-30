import socket
import time
from datetime import datetime
from typing import Tuple

class AuthManager:
    """Менеджер аутентификации пользователей"""
    
    def __init__(self, storage, security, logger):
        self._storage = storage
        self._security = security
        self._logger = logger
        self.active_users: dict = {}
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str]:
        """Аутентификация пользователя"""
        from utils.helpers import validate_username, validate_password
        
        valid, message = validate_username(username)
        if not valid:
            return False, message
        
        if self._security.require_password and username not in self._storage.users:
            valid, message = validate_password(password, self._security.password_min_length)
            if not valid:
                return False, message
            return self._register_user(username, password, auto=True)
        
        if not self._security.require_password:
            if username not in self._storage.users:
                self._create_user_record(username, '')
            return True, 'Вход выполнен'
        
        if username not in self._storage.users:
            return False, 'Пользователь не найден'
        
        if not self._security.verify_password(password, self._storage.users[username]['password_hash']):
            return False, 'Неверный пароль'
        
        self._update_login_info(username)
        return True, 'Вход выполнен'
    
    def _register_user(self, username: str, password: str, auto: bool = False) -> Tuple[bool, str]:
        """Регистрация нового пользователя"""
        if username in self._storage.users:
            return False, 'Пользователь уже существует'
        
        password_hash = self._security.hash_password(password)
        self._create_user_record(username, password_hash)
        
        if auto:
            self._logger.log('INFO', f'Автоматическая регистрация: {username}')
        return True, 'Регистрация успешна'
    
    def _create_user_record(self, username: str, password_hash: str):
        """Создание записи пользователя"""
        now = datetime.now().isoformat()
        self._storage.users[username] = {
            'username': username,
            'password_hash': password_hash,
            'created_at': now,
            'last_login': now,
            'login_count': 1,
            'shares_count': 0
        }
        self._storage.save_users()
    
    def _update_login_info(self, username: str):
        """Обновление информации о входе"""
        if username in self._storage.users:
            self._storage.users[username]['last_login'] = datetime.now().isoformat()
            self._storage.users[username]['login_count'] = self._storage.users[username].get('login_count', 0) + 1
            self._storage.save_users()
    
    def add_active_user(self, username: str, sock, address):
        """Добавление активного пользователя"""
        from utils.helpers import get_base_username
        
        base_name = get_base_username(username)
        
        if username in self.active_users:
            old_socket = self.active_users[username].get('socket')
            if old_socket and old_socket != sock:
                self._close_socket(old_socket)
                self._logger.log('DEBUG', f'Закрыто старое соединение для {username}')
        
        self.active_users[username] = {
            'socket': sock,
            'address': address,
            'last_seen': time.time(),
            'base_name': base_name
        }
    
    def remove_active_user(self, username: str):
        """Удаление активного пользователя"""
        self.active_users.pop(username, None)
    
    def is_user_online(self, username: str) -> bool:
        """Проверка, онлайн ли пользователь"""
        from utils.helpers import get_base_username
        base_name = get_base_username(username)
        return any(u.get('base_name') == base_name for u in self.active_users.values())
    
    def get_user_socket(self, username: str):
        """Получение сокета пользователя"""
        user = self.active_users.get(username)
        return user['socket'] if user else None
    
    def update_activity(self, username: str):
        """Обновление времени активности пользователя"""
        if username in self.active_users:
            self.active_users[username]['last_seen'] = time.time()
    
    def get_online_count(self) -> int:
        """Получение количества пользователей онлайн"""
        return len(self.active_users)
    
    @staticmethod
    def _close_socket(sock):
        """Безопасное закрытие сокета"""
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass