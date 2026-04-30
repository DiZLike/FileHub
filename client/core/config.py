import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

DEFAULT_CONFIG = """# Конфигурация клиента FileHub

[connection]
server_host = localhost
server_port = 5000
data_port = 5001
connection_timeout = 30

[downloads]
download_dir = downloads
max_retries = 3
verify_files = false

[shares]
st_dir = my_shares
st_file = {share_id}.json
sync_shares_on_connect = true

[interface]
show_progress = true
confirm_downloads = false
auto_reconnect = false

[logging]
enabled = true
log_file = hub.log
log_level = INFO
log_transfers = true
max_log_size_mb = 10

[security]
remember_password = false
password_hash_file = client_pass.hash

[service]
auto_reconnect = true
reconnect_interval = 30
"""

@dataclass
class ConnectionConfig:
    server_host: str = 'localhost'
    server_port: int = 5000
    data_port: int = 5001
    connection_timeout: int = 30

@dataclass
class DownloadsConfig:
    download_dir: str = 'downloads'
    max_retries: int = 3
    verify_files: bool = False

@dataclass
class SharesConfig:
    st_dir: str = 'my_shares'
    st_file: str = '{share_id}.json'
    sync_shares_on_connect: bool = True

@dataclass
class InterfaceConfig:
    show_progress: bool = True
    confirm_downloads: bool = False
    auto_reconnect: bool = False

@dataclass
class SecurityConfig:
    remember_password: bool = False
    password_hash_file: str = 'client_pass.hash'

@dataclass
class ServiceConfig:
    auto_reconnect: bool = True
    reconnect_interval: int = 30

class ClientConfig:
    """Менеджер конфигурации клиента"""
    
    def __init__(self, config_path='client.conf'):
        self.config_path = Path(config_path)
        self._raw: Dict[str, Dict[str, str]] = {}
        self._load()
    
    def _load(self):
        """Загрузка конфигурации"""
        if not self.config_path.exists():
            self._create_default()
        
        section = 'global'
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith(';'):
                        continue
                    
                    if line.startswith('[') and line.endswith(']'):
                        section = line[1:-1].strip()
                        self._raw.setdefault(section, {})
                        continue
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key, value = key.strip(), value.strip()
                        if '#' in value:
                            value = value.split('#')[0].strip()
                        if ';' in value:
                            value = value.split(';')[0].strip()
                        self._raw.setdefault(section, {})[key] = value
        except Exception as e:
            print(f'Ошибка загрузки конфигурации клиента: {e}')
            self._raw = {}
    
    def _create_default(self):
        """Создание конфигурации по умолчанию"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_CONFIG)
            print(f'Создан конфигурационный файл: {self.config_path}')
        except Exception as e:
            print(f'Ошибка создания конфигурации: {e}')
    
    def get(self, section: str, key: str, default='') -> str:
        return self._raw.get(section, {}).get(key, default)
    
    def get_int(self, section: str, key: str, default=0) -> int:
        try:
            return int(self.get(section, key, str(default)))
        except ValueError:
            return default
    
    def get_bool(self, section: str, key: str, default=False) -> bool:
        return self.get(section, key, str(default).lower()).lower() == 'true'
    
    @property
    def connection(self) -> ConnectionConfig:
        return ConnectionConfig(
            server_host=self.get('connection', 'server_host', 'localhost'),
            server_port=self.get_int('connection', 'server_port', 5000),
            data_port=self.get_int('connection', 'data_port', 5001),
            connection_timeout=self.get_int('connection', 'connection_timeout', 30)
        )
    
    @property
    def downloads(self) -> DownloadsConfig:
        return DownloadsConfig(
            download_dir=self.get('downloads', 'download_dir', 'downloads'),
            max_retries=self.get_int('downloads', 'max_retries', 3),
            verify_files=self.get_bool('downloads', 'verify_files')
        )
    
    @property
    def shares(self) -> SharesConfig:
        return SharesConfig(
            st_dir=self.get('shares', 'st_dir', 'my_shares'),
            st_file=self.get('shares', 'st_file', '{share_id}.json'),
            sync_shares_on_connect=self.get_bool('shares', 'sync_shares_on_connect', True)
        )
    
    @property
    def interface(self) -> InterfaceConfig:
        return InterfaceConfig(
            show_progress=self.get_bool('interface', 'show_progress', True),
            confirm_downloads=self.get_bool('interface', 'confirm_downloads'),
            auto_reconnect=self.get_bool('interface', 'auto_reconnect')
        )
    
    @property
    def security(self) -> SecurityConfig:
        return SecurityConfig(
            remember_password=self.get_bool('security', 'remember_password'),
            password_hash_file=self.get('security', 'password_hash_file', 'client_pass.hash')
        )
    
    @property
    def logging(self) -> dict:
        return {
            'enabled': self.get_bool('logging', 'enabled', True),
            'log_file': self.get('logging', 'log_file', 'hub.log'),
            'log_level': self.get('logging', 'log_level', 'INFO').upper(),
            'log_transfers': self.get_bool('logging', 'log_transfers', True),
            'max_log_size_mb': self.get_int('logging', 'max_log_size_mb', 10)
        }

    @property
    def service(self) -> ServiceConfig:
        return ServiceConfig(
            auto_reconnect=self.get_bool('service', 'auto_reconnect', True),
            reconnect_interval=self.get_int('service', 'reconnect_interval', 30)
        )