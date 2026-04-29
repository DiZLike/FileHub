"""
Управление раздачами файлов
"""

import time
from datetime import datetime
from utils import Utils
from protocols import ShareTypes

class ShareManager:
    """Менеджер раздач"""
    
    def __init__(self, storage, config, auth, logger):
        """
        Инициализация менеджера раздач
        
        Аргументы:
            storage: хранилище данных
            config: конфигурация
            auth: менеджер аутентификации
            logger: система логирования
        """
        self.storage = storage
        self.auth = auth
        self.logger = logger
        
        self.max_file_size = config.shares_config['max_file_size']
        self.max_files_in_folder = config.shares_config['max_files_in_folder']
        self.max_shares_per_user = config.security_config['max_shares_per_user']
        self.inactive_timeout = config.shares_config['inactive_timeout']
        
        self.blocked_extensions = config.security_config['blocked_extensions']
    
    def create_share(self, username, name, share_type, **kwargs):
        """
        Создание новой раздачи
        
        Аргументы:
            username: имя пользователя
            name: имя раздачи
            share_type: тип раздачи (файл/папка)
            **kwargs: дополнительные параметры (размер, файлы и т.д.)
            
        Возвращает:
            (ID раздачи, сообщение) или (None, сообщение об ошибке)
        """
        base_name = Utils.get_base_username(username)
        
        # Проверка лимитов
        user_shares = self._get_user_shares_count(base_name)
        if user_shares >= self.max_shares_per_user:
            return None, f'Лимит раздач ({self.max_shares_per_user})'
        
        # Проверка расширения для файлов
        if share_type == ShareTypes.FILE:
            if not self._is_extension_allowed(name):
                return None, 'Расширение файла запрещено'
            
            size = kwargs.get('size', 0)
            if self.max_file_size > 0 and size > self.max_file_size:
                return None, f'Файл слишком большой. Максимум: {Utils.format_bytes(self.max_file_size)}'
        
        # Проверка количества файлов в папке
        if share_type == ShareTypes.FOLDER:
            files = kwargs.get('files', [])
            if len(files) > self.max_files_in_folder:
                return None, f'Слишком много файлов. Максимум: {self.max_files_in_folder}'
        
        # Создание раздачи
        share_id = Utils.generate_unique_id(base_name, name)
        
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
        
        if share_type == ShareTypes.FILE:
            share_info['size'] = kwargs.get('size', 0)
        else:
            share_info.update({
                'files': kwargs.get('files', []),
                'total_size': kwargs.get('total_size', 0),
                'files_count': kwargs.get('files_count', 0)
            })
        
        self.storage.shares[share_id] = share_info
        self.logger.update_stat('total_shares')
        
        # Обновление счетчика пользователя
        if base_name in self.storage.users:
            self.storage.users[base_name]['shares_count'] = \
                self.storage.users[base_name].get('shares_count', 0) + 1
        
        self.storage.save_shares()
        
        log_msg = f'Новая раздача: [{share_id}] {name}'
        if share_type == ShareTypes.FILE:
            log_msg += f' ({Utils.format_bytes(share_info["size"])})'
        else:
            log_msg += f' ({share_info["files_count"]} файлов)'
        log_msg += f' от {base_name}'
        self.logger.log('INFO', log_msg)
        
        return share_id, 'Раздача создана'
    
    def remove_share(self, share_id, username):
        """
        Удаление раздачи
        
        Аргументы:
            share_id: ID раздачи
            username: имя пользователя
            
        Возвращает:
            (успех, сообщение)
        """
        base_name = Utils.get_base_username(username)
        
        if share_id not in self.storage.shares:
            return False, 'Раздача не найдена'
        
        if self.storage.shares[share_id]['username'] != base_name:
            return False, 'Это не ваша раздача'
        
        share_name = self.storage.shares[share_id]['name']
        del self.storage.shares[share_id]
        self.storage.save_shares()
        
        self.logger.log('INFO', f'Удалена раздача: {share_name} ({base_name})')
        return True, f'Раздача {share_name} удалена'
    
    def get_share_info(self, share_id):
        """
        Получение информации о раздаче
        
        Аргументы:
            share_id: ID раздачи
            
        Возвращает:
            информация о раздаче или None
        """
        return self.storage.shares.get(share_id)
    
    def get_all_shares(self):
        """
        Получение всех раздач
        
        Возвращает:
            список раздач
        """
        shares_list = [
            self._format_share_info(sid, info) 
            for sid, info in self.storage.shares.items()
        ]
        shares_list.sort(key=lambda x: x['created_at'], reverse=True)
        return shares_list
    
    def get_user_shares(self, username):
        """
        Получение раздач пользователя
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            список раздач пользователя
        """
        base_name = Utils.get_base_username(username)
        shares_list = [
            self._format_share_info(sid, info)
            for sid, info in self.storage.shares.items()
            if info['username'] == base_name
        ]
        return shares_list
    
    def update_owner_status(self, username, online=True):
        """
        Обновление статуса владельца раздач
        
        Аргументы:
            username: имя пользователя
            online: статус онлайн
        """
        base_name = Utils.get_base_username(username)
        current_time = time.time()
        
        for share in self.storage.shares.values():
            if share['username'] == base_name:
                share['owner_online'] = online
                if online:
                    share['last_seen'] = current_time
    
    def update_share_activity(self, share_ids, username):
        """
        Обновление активности раздач
        
        Аргументы:
            share_ids: список ID раздач
            username: имя пользователя
        """
        base_name = Utils.get_base_username(username)
        current_time = time.time()
        
        for share_id in share_ids:
            if share_id in self.storage.shares:
                share = self.storage.shares[share_id]
                if share['username'] == base_name:
                    share['last_seen'] = current_time
                    share['owner_online'] = True
    
    def increment_downloads(self, share_id):
        """
        Увеличение счетчика скачиваний
        
        Аргументы:
            share_id: ID раздачи
        """
        if share_id in self.storage.shares:
            self.storage.shares[share_id]['downloads'] += 1
            self.logger.update_stat('total_downloads')
    
    def cleanup_inactive_shares(self):
        """
        Очистка неактивных раздач
        
        Возвращает:
            количество удалённых раздач
        """
        current_time = time.time()
        to_delete = []
        
        for share_id, share in self.storage.shares.items():
            if current_time - share.get('last_seen', 0) > self.inactive_timeout:
                to_delete.append(share_id)
        
        for share_id in to_delete:
            share = self.storage.shares[share_id]
            self.logger.log('INFO', f'Удалена неактивная раздача: [{share_id}] {share["name"]}')
            del self.storage.shares[share_id]
        
        if to_delete:
            self.storage.save_shares()
        
        return len(to_delete)
    
    def _format_share_info(self, share_id, info):
        """
        Форматирование информации о раздаче
        
        Аргументы:
            share_id: ID раздачи
            info: информация о раздаче
            
        Возвращает:
            отформатированные данные
        """
        share_data = {
            'share_id': share_id,
            'username': info['username'],
            'name': info['name'],
            'type': info['type'],
            'owner_online': self.auth.is_user_online(info['username']),
            'downloads': info['downloads'],
            'created_at': info['created_at']
        }
        
        if info['type'] == ShareTypes.FILE:
            share_data['size'] = info['size']
        else:
            share_data['files_count'] = info.get('files_count', 0)
            share_data['total_size'] = info.get('total_size', 0)
        
        if 'last_seen' in info:
            share_data['last_active'] = Utils.format_timestamp(info['last_seen'])
        
        return share_data
    
    def _get_user_shares_count(self, username):
        """
        Получение количества раздач пользователя
        
        Аргументы:
            username: имя пользователя
            
        Возвращает:
            количество раздач
        """
        return sum(1 for s in self.storage.shares.values() if s['username'] == username)
    
    def _is_extension_allowed(self, filename):
        """
        Проверка расширения файла
        
        Аргументы:
            filename: имя файла
            
        Возвращает:
            True если расширение разрешено
        """
        if not self.blocked_extensions:
            return True
        import os
        ext = os.path.splitext(filename)[1].lower()
        return ext not in self.blocked_extensions