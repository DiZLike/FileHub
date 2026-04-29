"""
Модуль аутентификации пользователей
"""

from datetime import datetime
from utils import Utils

class AuthManager:
    """Менеджер аутентификации"""
    
    def __init__(self, storage, security, logger):
        """
        Инициализация менеджера аутентификации
        
        Аргументы:
            storage: хранилище данных
            security: менеджер безопасности
            logger: система логирования
        """
        self.storage = storage
        self.security = security
        self.logger = logger
        self.active_users = {}
    
    def authenticate_user(self, username, password):
        """
        Аутентификация пользователя
        
        Аргументы:
            username: имя пользователя
            password: пароль
            
        Возвращает:
            (успех, сообщение)
        """
        # Валидация имени пользователя
        valid, message = Utils.validate_username(username)
        if not valid:
            return False, message
        
        # Автоматическая регистрация при необходимости
        if self.security.require_password and username not in self.storage.users:
            valid, message = Utils.validate_password(password, self.security.password_min_length)
            if not valid:
                return False, message
            return self._register_user(username, password, auto=True)
        
        # Если пароль не требуется
        if not self.security.require_password:
            if username not in self.storage.users:
                self._create_user(username, '')
            return True, 'Вход выполнен'
        
        # Проверка существующего пользователя
        if username not in self.storage.users:
            return False, 'Пользователь не найден'
        
        if not self.security.verify_password(password, self.storage.users[username]['password_hash']):
            return False, 'Неверный пароль'
        
        # Обновление информации о входе
        self._update_login_info(username)
        return True, 'Вход выполнен'
    
    def _register_user(self, username, password, auto=False):
        """
        Регистрация нового пользователя
        
        Аргументы:
            username: имя пользователя
            password: пароль
            auto: автоматическая регистрация
        """
        if username in self.storage.users:
            return False, 'Пользователь уже существует'
        
        password_hash = self.security.hash_password(password)
        self._create_user(username, password_hash)
        
        if auto:
            self.logger.log('INFO', f'Автоматическая регистрация: {username}')
        return True, 'Регистрация успешна'
    
    def _create_user(self, username, password_hash):
        """Создание пользователя"""
        self.storage.users[username] = {
            'username': username,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat(),
            'last_login': datetime.now().isoformat(),
            'login_count': 1,
            'shares_count': 0
        }
        self.storage.save_users()
    
    def _update_login_info(self, username):
        """Обновление информации о входе"""
        if username in self.storage.users:
            self.storage.users[username]['last_login'] = datetime.now().isoformat()
            self.storage.users[username]['login_count'] = \
                self.storage.users[username].get('login_count', 0) + 1
            self.storage.save_users()
    
    def add_active_user(self, username, socket, address):
        """
        Добавление активного пользователя
        
        Аргументы:
            username: имя пользователя
            socket: сокет подключения
            address: адрес подключения
        """
        base_name = Utils.get_base_username(username)
        
        # Закрываем старое соединение если есть
        if username in self.active_users:
            old_socket = self.active_users[username].get('socket')
            if old_socket and old_socket != socket:
                try:
                    old_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    old_socket.close()
                except Exception:
                    pass
                self.logger.log('DEBUG', f'Закрыто старое соединение для {username}')
        
        self.active_users[username] = {
            'socket': socket,
            'address': address,
            'last_seen': __import__('time').time(),
            'base_name': base_name
        }
    
    def remove_active_user(self, username):
        """Удаление активного пользователя"""
        if username in self.active_users:
            del self.active_users[username]
    
    def is_user_online(self, username):
        """
        Проверка, онлайн ли пользователь
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            True если онлайн, иначе False
        """
        base_name = Utils.get_base_username(username)
        for uname, uinfo in self.active_users.items():
            if uinfo.get('base_name') == base_name:
                return True
        return False
    
    def get_user_socket(self, username):
        """
        Получение сокета пользователя
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            сокет пользователя или None
        """
        if username in self.active_users:
            return self.active_users[username]['socket']
        return None
    
    def update_user_activity(self, username):
        """
        Обновление времени активности пользователя
        
        Аргументы:
            username: имя пользователя
        """
        if username in self.active_users:
            self.active_users[username]['last_seen'] = __import__('time').time()