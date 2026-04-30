import os
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Union

DEFAULT_CONFIG = """# Конфигурация FileHub
[server]
host = 0.0.0.0
port = 5000
data_port = 5001
max_connections = 10
connection_timeout = 300

[shares]
storage_file = shares_data.json
users_file = users_data.json
cleanup_interval_hours = 1
inactive_days = 3
save_interval_minutes = 5
max_file_size_mb = 0
max_files_in_folder = 1000

[network]
buffer_size = 8192
max_json_size = 1048576

[logging]
enabled = true
log_file = hub.log
log_level = INFO
log_transfers = true
max_log_size_mb = 10

[security]
local_only = false
allowed_ips = 
blocked_ips = 
max_shares_per_user = 50
blocked_extensions = 
password_min_length = 4
require_password = true
tls_enabled = false
tls_cert_dir = certs
"""

@dataclass
class ServerConfigData:
    host: str = '0.0.0.0'
    port: int = 5000
    data_port: int = 5001
    max_connections: int = 10
    connection_timeout: int = 300

@dataclass
class SharesConfigData:
    storage_file: str = 'shares_data.json'
    users_file: str = 'users_data.json'
    cleanup_interval: int = 3600
    inactive_timeout: int = 259200
    save_interval: int = 300
    max_file_size: int = 0
    max_files_in_folder: int = 1000

@dataclass
class NetworkConfigData:
    buffer_size: int = 8192
    max_json_size: int = 1048576

@dataclass
class SecurityConfigData:
    local_only: bool = False
    allowed_ips: list = field(default_factory=list)
    blocked_ips: list = field(default_factory=list)
    max_shares_per_user: int = 50
    blocked_extensions: list = field(default_factory=list)
    password_min_length: int = 4
    require_password: bool = True
    tls_enabled: bool = False
    tls_cert_dir: str = 'certs'

class ServerConfig:
    """Менеджер конфигурации сервера"""
    
    def __init__(self, config_path='filehub.conf'):
        self.config_path = Path(config_path)
        self._raw: Dict[str, Dict[str, str]] = {}
        self._load()
    
    def _load(self):
        """Загрузка конфигурации из файла"""
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
            print(f'Ошибка загрузки конфигурации: {e}')
            self._raw = {}
    
    def _create_default(self):
        """Создание конфигурации по умолчанию"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_CONFIG)
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
    
    def get_list(self, section: str, key: str, default='') -> List[str]:
        value = self.get(section, key, default)
        return [item.strip() for item in value.split(',') if item.strip()] if value else []
    
    def get_ip_list(self, section: str, key: str) -> List:
        ips = []
        for item in self.get_list(section, key):
            try:
                ips.append(
                    ipaddress.ip_network(item) if '/' in item
                    else ipaddress.ip_address(item)
                )
            except ValueError:
                pass
        return ips
    
    @property
    def server(self) -> ServerConfigData:
        return ServerConfigData(
            host=self.get('server', 'host', '0.0.0.0'),
            port=self.get_int('server', 'port', 5000),
            data_port=self.get_int('server', 'data_port', 5001),
            max_connections=self.get_int('server', 'max_connections', 10),
            connection_timeout=self.get_int('server', 'connection_timeout', 300)
        )
    
    @property
    def shares(self) -> SharesConfigData:
        return SharesConfigData(
            storage_file=self.get('shares', 'storage_file', 'shares_data.json'),
            users_file=self.get('shares', 'users_file', 'users_data.json'),
            cleanup_interval=self.get_int('shares', 'cleanup_interval_hours', 1) * 3600,
            inactive_timeout=self.get_int('shares', 'inactive_days', 3) * 86400,
            save_interval=self.get_int('shares', 'save_interval_minutes', 5) * 60,
            max_file_size=self.get_int('shares', 'max_file_size_mb', 0) * 1024 * 1024,
            max_files_in_folder=self.get_int('shares', 'max_files_in_folder', 1000)
        )
    
    @property
    def network(self) -> NetworkConfigData:
        return NetworkConfigData(
            buffer_size=self.get_int('network', 'buffer_size', 8192),
            max_json_size=self.get_int('network', 'max_json_size', 1048576)
        )
    
    @property
    def security(self) -> SecurityConfigData:
        return SecurityConfigData(
            local_only=self.get_bool('security', 'local_only'),
            allowed_ips=self.get_ip_list('security', 'allowed_ips'),
            blocked_ips=self.get_ip_list('security', 'blocked_ips'),
            max_shares_per_user=self.get_int('security', 'max_shares_per_user', 50),
            blocked_extensions=self.get_list('security', 'blocked_extensions'),
            password_min_length=self.get_int('security', 'password_min_length', 4),
            require_password=self.get_bool('security', 'require_password', True),
            tls_enabled=self.get_bool('security', 'tls_enabled'),
            tls_cert_dir=self.get('security', 'tls_cert_dir', 'certs')
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