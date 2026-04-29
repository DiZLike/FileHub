"""
Конфигурация клиента
"""

import os

DEFAULT_CONFIG = """# Конфигурация клиента FileHub

[connection]
# Адрес сервера
server_host = localhost
# Порт управляющих команд
server_port = 5000
# Порт передачи данных
data_port = 5001
# Таймаут подключения (секунд)
connection_timeout = 30

[downloads]
# Директория для скачанных файлов
download_dir = downloads
# Максимум попыток скачивания
max_retries = 3
# Проверять целостность файлов
verify_files = false

[shares]
# Директория хранения информации о раздачах
st_dir = my_shares
# Шаблон имени файла раздачи
st_file = {share_id}.json
# Синхронизировать раздачи при подключении
sync_shares_on_connect = true

[interface]
# Показывать прогресс передачи
show_progress = true
# Подтверждать скачивание
confirm_downloads = false
# Автопереподключение
auto_reconnect = false

[security]
# Запоминать пароль (сохраняется хеш)
remember_password = false
# Файл хешей паролей
password_hash_file = client_pass.hash
"""

class ClientConfig:
    """Менеджер конфигурации клиента"""
    
    def __init__(self, config_path='client.conf'):
        """
        Инициализация конфигурации
        
        Аргументы:
            config_path: путь к файлу конфигурации
        """
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self):
        """
        Загрузка конфигурации
        
        Возвращает:
            словарь с конфигурацией
        """
        config = {}
        current_section = 'global'
        
        if not os.path.exists(self.config_path):
            self.create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith(';'):
                        continue
                    
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1].strip()
                        if current_section not in config:
                            config[current_section] = {}
                        continue
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if '#' in value:
                            value = value.split('#')[0].strip()
                        if ';' in value:
                            value = value.split(';')[0].strip()
                        
                        if current_section not in config:
                            config[current_section] = {}
                        config[current_section][key] = value
        except Exception as e:
            print(f'Ошибка загрузки конфигурации клиента: {e}')
            config = {}
        
        return config
    
    def create_default_config(self):
        """Создание конфигурации по умолчанию"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_CONFIG)
            print(f'Создан конфигурационный файл: {self.config_path}')
        except Exception as e:
            print(f'Ошибка создания конфигурации: {e}')
    
    def get_config(self, section, key, default=None):
        """
        Получение значения конфигурации
        
        Аргументы:
            section: секция
            key: ключ
            default: значение по умолчанию
            
        Возвращает:
            значение параметра
        """
        return self.config.get(section, {}).get(key, default)
    
    @property
    def connection_config(self):
        """Конфигурация подключения"""
        return {
            'server_host': self.get_config('connection', 'server_host', 'localhost'),
            'server_port': int(self.get_config('connection', 'server_port', '5000')),
            'data_port': int(self.get_config('connection', 'data_port', '5001')),
            'connection_timeout': int(self.get_config('connection', 'connection_timeout', '30'))
        }
    
    @property
    def downloads_config(self):
        """Конфигурация загрузок"""
        return {
            'download_dir': self.get_config('downloads', 'download_dir', 'downloads'),
            'max_retries': int(self.get_config('downloads', 'max_retries', '3')),
            'verify_files': self.get_config('downloads', 'verify_files', 'false').lower() == 'true'
        }
    
    @property
    def shares_config(self):
        """Конфигурация хранения раздач"""
        return {
            'st_dir': self.get_config('shares', 'st_dir', 'my_shares'),
            'st_file': self.get_config('shares', 'st_file', '{share_id}.json'),
            'sync_shares_on_connect': self.get_config('shares', 'sync_shares_on_connect', 'true').lower() == 'true'
        }
    
    @property
    def interface_config(self):
        """Конфигурация интерфейса"""
        return {
            'show_progress': self.get_config('interface', 'show_progress', 'true').lower() == 'true',
            'confirm_downloads': self.get_config('interface', 'confirm_downloads', 'false').lower() == 'true',
            'auto_reconnect': self.get_config('interface', 'auto_reconnect', 'false').lower() == 'true'
        }
    
    @property
    def security_config(self):
        """Конфигурация безопасности"""
        return {
            'remember_password': self.get_config('security', 'remember_password', 'false').lower() == 'true',
            'password_hash_file': self.get_config('security', 'password_hash_file', 'client_pass.hash')
        }