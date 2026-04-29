"""
Управление конфигурацией сервера
"""

import os
import ipaddress
from protocols import DEFAULT_CONFIG

class Config:
    """Менеджер конфигурации"""
    
    def __init__(self, config_path='filehub.conf'):
        """
        Инициализация конфигурации
        
        Аргументы:
            config_path: путь к файлу конфигурации
        """
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self):
        """
        Загрузка конфигурации из файла
        
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
                        
                        # Удаляем комментарии
                        if '#' in value:
                            value = value.split('#')[0].strip()
                        if ';' in value:
                            value = value.split(';')[0].strip()
                        
                        if current_section not in config:
                            config[current_section] = {}
                        config[current_section][key] = value
        except Exception as e:
            print(f'Ошибка загрузки конфигурации: {e}')
            config = {}
        
        return config
    
    def create_default_config(self):
        """Создание конфигурации по умолчанию"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_CONFIG)
        except Exception as e:
            print(f'Ошибка создания конфигурации: {e}')
    
    def get_config(self, section, key, default=None):
        """
        Получение значения конфигурации
        
        Аргументы:
            section: секция конфигурации
            key: ключ параметра
            default: значение по умолчанию
            
        Возвращает:
            значение параметра или default
        """
        return self.config.get(section, {}).get(key, default)
    
    def parse_ip_list(self, ip_string):
        """
        Парсинг списка IP-адресов
        
        Аргументы:
            ip_string: строка с IP-адресами через запятую
            
        Возвращает:
            список объектов IP-адресов
        """
        if not ip_string:
            return []
        
        ips = []
        for item in ip_string.split(','):
            item = item.strip()
            if not item:
                continue
            try:
                if '/' in item:
                    ips.append(ipaddress.ip_network(item))
                else:
                    ips.append(ipaddress.ip_address(item))
            except ValueError:
                pass
        return ips
    
    def parse_list(self, string):
        """
        Парсинг списка, разделенного запятыми
        
        Аргументы:
            string: исходная строка
            
        Возвращает:
            список элементов
        """
        if not string:
            return []
        return [item.strip() for item in string.split(',') if item.strip()]
    
    @property
    def server_config(self):
        """Конфигурация сервера"""
        return {
            'host': self.get_config('server', 'host', '0.0.0.0'),
            'port': int(self.get_config('server', 'port', '5000')),
            'data_port': int(self.get_config('server', 'data_port', '5001')),
            'max_connections': int(self.get_config('server', 'max_connections', '10')),
            'connection_timeout': int(self.get_config('server', 'connection_timeout', '300'))
        }
    
    @property
    def shares_config(self):
        """Конфигурация раздач"""
        return {
            'storage_file': self.get_config('shares', 'storage_file', 'shares_data.json'),
            'users_file': self.get_config('shares', 'users_file', 'users_data.json'),
            'cleanup_interval': int(self.get_config('shares', 'cleanup_interval_hours', '1')) * 3600,
            'inactive_timeout': int(self.get_config('shares', 'inactive_days', '3')) * 86400,
            'save_interval': int(self.get_config('shares', 'save_interval_minutes', '5')) * 60,
            'max_file_size': int(self.get_config('shares', 'max_file_size_mb', '0')) * 1024 * 1024,
            'max_files_in_folder': int(self.get_config('shares', 'max_files_in_folder', '1000'))
        }
    
    @property
    def network_config(self):
        """Конфигурация сети"""
        return {
            'buffer_size': int(self.get_config('network', 'buffer_size', '8192')),
            'max_json_size': int(self.get_config('network', 'max_json_size', '1048576'))
        }
    
    @property
    def security_config(self):
        """Конфигурация безопасности"""
        return {
            'local_only': self.get_config('security', 'local_only', 'false').lower() == 'true',
            'allowed_ips': self.parse_ip_list(self.get_config('security', 'allowed_ips', '')),
            'blocked_ips': self.parse_ip_list(self.get_config('security', 'blocked_ips', '')),
            'max_shares_per_user': int(self.get_config('security', 'max_shares_per_user', '50')),
            'blocked_extensions': self.parse_list(self.get_config('security', 'blocked_extensions', '')),
            'password_min_length': int(self.get_config('security', 'password_min_length', '4')),
            'require_password': self.get_config('security', 'require_password', 'true').lower() == 'true'
        }