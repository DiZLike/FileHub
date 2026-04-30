import os
import time
from datetime import datetime
from typing import Tuple, Optional, List

class ShareManager:
    """Менеджер раздач файлов"""
    
    def __init__(self, storage, config, auth, logger):
        self._storage = storage
        self._auth = auth
        self._logger = logger
        
        self._max_file_size = config.shares.max_file_size
        self._max_files_in_folder = config.shares.max_files_in_folder
        self._max_shares_per_user = config.security.max_shares_per_user
        self._inactive_timeout = config.shares.inactive_timeout
        self._blocked_extensions = config.security.blocked_extensions
    
    def create_share(self, username: str, name: str, share_type: str, **kwargs) -> Tuple[Optional[str], str]:
        """Создание новой раздачи"""
        from utils.helpers import get_base_username, generate_unique_id, format_bytes
        
        base_name = get_base_username(username)
        
        user_shares_count = sum(1 for s in self._storage.shares.values() if s['username'] == base_name)
        if user_shares_count >= self._max_shares_per_user:
            return None, f'Лимит раздач ({self._max_shares_per_user})'
        
        if share_type == 'file':
            if not self._is_extension_allowed(name):
                return None, 'Расширение файла запрещено'
            
            size = kwargs.get('size', 0)
            if self._max_file_size > 0 and size > self._max_file_size:
                return None, f'Файл слишком большой. Максимум: {format_bytes(self._max_file_size)}'
        
        if share_type == 'folder':
            files = kwargs.get('files', [])
            if len(files) > self._max_files_in_folder:
                return None, f'Слишком много файлов. Максимум: {self._max_files_in_folder}'
        
        share_id = generate_unique_id(base_name, name)
        
        share_info = {
            'share_id': share_id,
            'username': base_name,
            'name': name,
            'type': share_type,
            'created_at': datetime.now().isoformat(),
            'last_seen': time.time(),
            'owner_online': True,
            'downloads': 0
        }
        
        if share_type == 'file':
            share_info['size'] = kwargs.get('size', 0)
        else:
            share_info.update({
                'files': kwargs.get('files', []),
                'total_size': kwargs.get('total_size', 0),
                'files_count': kwargs.get('files_count', 0)
            })
        
        self._storage.shares[share_id] = share_info
        self._logger.update_stat('total_shares')
        
        if base_name in self._storage.users:
            self._storage.users[base_name]['shares_count'] = self._storage.users[base_name].get('shares_count', 0) + 1
        
        self._storage.save_shares()
        self._log_share_creation(share_info, base_name)
        
        return share_id, 'Раздача создана'
    
    def remove_share(self, share_id: str, username: str) -> Tuple[bool, str]:
        """Удаление раздачи"""
        from utils.helpers import get_base_username
        
        base_name = get_base_username(username)
        
        if share_id not in self._storage.shares:
            return False, 'Раздача не найдена'
        
        if self._storage.shares[share_id]['username'] != base_name:
            return False, 'Это не ваша раздача'
        
        share_name = self._storage.shares[share_id]['name']
        del self._storage.shares[share_id]
        self._storage.save_shares()
        
        self._logger.log('INFO', f'Удалена раздача: {share_name} ({base_name})')
        return True, f'Раздача {share_name} удалена'
    
    def get_share_info(self, share_id: str) -> Optional[dict]:
        """Получение информации о раздаче"""
        return self._storage.shares.get(share_id)
    
    def get_all_shares(self) -> List[dict]:
        """Получение всех раздач"""
        shares_list = [
            self._format_share_info(sid, info)
            for sid, info in self._storage.shares.items()
        ]
        shares_list.sort(key=lambda x: x['created_at'], reverse=True)
        return shares_list
    
    def get_user_shares(self, username: str) -> List[dict]:
        """Получение раздач пользователя"""
        from utils.helpers import get_base_username
        
        base_name = get_base_username(username)
        return [
            self._format_share_info(sid, info)
            for sid, info in self._storage.shares.items()
            if info['username'] == base_name
        ]
    
    def update_owner_status(self, username: str, online: bool = True) -> int:
        """Обновление статуса владельца раздач"""
        from utils.helpers import get_base_username
        
        base_name = get_base_username(username)
        current_time = time.time()
        count = 0
        
        for share in self._storage.shares.values():
            if share['username'] == base_name:
                share['owner_online'] = online
                if online:
                    share['last_seen'] = current_time
                count += 1
        
        return count
    
    def update_share_activity(self, share_ids: List[str], username: str):
        """Обновление активности раздач"""
        from utils.helpers import get_base_username
        
        base_name = get_base_username(username)
        current_time = time.time()
        
        for share_id in share_ids:
            if share_id in self._storage.shares:
                share = self._storage.shares[share_id]
                if share['username'] == base_name:
                    share['last_seen'] = current_time
                    share['owner_online'] = True
    
    def increment_downloads(self, share_id: str):
        """Увеличение счетчика скачиваний"""
        if share_id in self._storage.shares:
            self._storage.shares[share_id]['downloads'] += 1
            self._logger.update_stat('total_downloads')
    
    def cleanup_inactive(self) -> int:
        """Очистка неактивных раздач"""
        current_time = time.time()
        to_delete = []
        
        for share_id, share in self._storage.shares.items():
            if current_time - share.get('last_seen', 0) > self._inactive_timeout:
                to_delete.append(share_id)
        
        for share_id in to_delete:
            share = self._storage.shares[share_id]
            self._logger.log('INFO', f'Удалена неактивная раздача: [{share_id}] {share["name"]}')
            del self._storage.shares[share_id]
        
        if to_delete:
            self._storage.save_shares()
        
        return len(to_delete)
    
    def _format_share_info(self, share_id: str, info: dict) -> dict:
        """Форматирование информации о раздаче"""
        from utils.helpers import format_timestamp
        
        share_data = {
            'share_id': share_id,
            'username': info['username'],
            'name': info['name'],
            'type': info['type'],
            'owner_online': self._auth.is_user_online(info['username']),
            'downloads': info['downloads'],
            'created_at': info['created_at']
        }
        
        if info['type'] == 'file':
            share_data['size'] = info['size']
        else:
            share_data['files_count'] = info.get('files_count', 0)
            share_data['total_size'] = info.get('total_size', 0)
        
        if 'last_seen' in info:
            share_data['last_active'] = format_timestamp(info['last_seen'])
        
        return share_data
    
    def _is_extension_allowed(self, filename: str) -> bool:
        """Проверка расширения файла"""
        if not self._blocked_extensions:
            return True
        ext = os.path.splitext(filename)[1].lower()
        return ext not in self._blocked_extensions
    
    def _log_share_creation(self, share_info: dict, username: str):
        """Логирование создания раздачи"""
        from utils.helpers import format_bytes
        
        log_msg = f'Новая раздача: [{share_info["share_id"]}] {share_info["name"]}'
        if share_info['type'] == 'file':
            log_msg += f' ({format_bytes(share_info["size"])})'
        else:
            log_msg += f' ({share_info["files_count"]} файлов)'
        log_msg += f' от {username}'
        self._logger.log('INFO', log_msg)