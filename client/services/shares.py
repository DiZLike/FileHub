import json
import os
import time
import threading
from pathlib import Path
from network.protocol import MessageActions, ShareTypes
from utils.helpers import format_size, get_file_list

class ShareManager:
    """Менеджер раздач клиента"""
    
    def __init__(self, connection, config):
        self.connection = connection
        self.local_shares = {}
        self.my_shares = set()
        self.show_progress = config.interface.show_progress
        
        shares_cfg = config.shares
        self.st_dir = shares_cfg.st_dir
        self.st_file_template = shares_cfg.st_file
        self.sync_shares_on_connect = shares_cfg.sync_shares_on_connect
        
        self._user_st_dir = None
        
        self.load_local_shares()
    
    def _get_user_st_dir(self) -> str:
        """Получение пути к директории раздач пользователя"""
        if self._user_st_dir is None:
            if self.connection and self.connection.username:
                self._user_st_dir = os.path.join(self.st_dir, self.connection.username)
            else:
                self._user_st_dir = self.st_dir
        return self._user_st_dir
    
    def _ensure_user_st_dir(self):
        """Создание директории для файлов раздач пользователя"""
        from ui.console import console
        
        user_dir = self._get_user_st_dir()
        try:
            os.makedirs(user_dir, exist_ok=True)
        except Exception as e:
            console.print_system_message(f'Ошибка создания директории {user_dir}: {e}', 'error')
    
    def get_share_file_path(self, share_id: str) -> str:
        """Получение пути к файлу раздачи"""
        user_dir = self._get_user_st_dir()
        filename = self.st_file_template.replace('{share_id}', share_id)
        return os.path.join(user_dir, filename)
    
    def load_local_shares(self):
        """Загрузка информации о локальных раздачах"""
        from ui.console import console
        
        self.local_shares.clear()
        self.my_shares.clear()
        
        if not self.connection or not self.connection.username:
            return
        
        user_dir = self._get_user_st_dir()
        self._ensure_user_st_dir()
        
        loaded_count = 0
        error_count = 0
        
        if os.path.exists(user_dir):
            try:
                for filename in os.listdir(user_dir):
                    filepath = os.path.join(user_dir, filename)
                    
                    if not os.path.isfile(filepath) or not filename.endswith('.json'):
                        continue
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            share_data = json.load(f)
                        
                        share_id = share_data.get('share_id')
                        if not share_id:
                            error_count += 1
                            continue
                        
                        self.local_shares[share_id] = share_data
                        self.my_shares.add(share_id)
                        loaded_count += 1
                        
                    except json.JSONDecodeError:
                        error_count += 1
                    except Exception:
                        error_count += 1
                
                if loaded_count > 0:
                    console.print_system_message(f'Загружено {loaded_count} локальных раздач', 'info')
                
            except Exception as e:
                console.print_system_message(f'Ошибка сканирования директории: {e}', 'error')
    
    def reload_shares_for_user(self):
        """Перезагрузка раздач после подключения"""
        self._user_st_dir = None
        self.load_local_shares()
    
    def add_local_share(self, share_id: str, local_path: str, share_type: str):
        """Добавление локальной раздачи"""
        share_data = {
            'share_id': share_id,
            'local_path': local_path,
            'type': share_type,
            'created_at': time.time()
        }
        
        self.local_shares[share_id] = share_data
        self.my_shares.add(share_id)
        self._save_share_file(share_id)
    
    def remove_local_share(self, share_id: str):
        """Удаление локальной раздачи"""
        self.my_shares.discard(share_id)
        self.local_shares.pop(share_id, None)
        self._delete_share_file(share_id)
    
    def _save_share_file(self, share_id: str):
        """Сохранение файла раздачи"""
        if share_id not in self.local_shares:
            return
        
        filepath = self.get_share_file_path(share_id)
        
        try:
            file_dir = os.path.dirname(filepath)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.local_shares[share_id], f, indent=2, ensure_ascii=False)
        except Exception as e:
            from ui.console import console
            console.print_system_message(f'Ошибка сохранения раздачи {share_id}: {e}', 'error')
    
    def _delete_share_file(self, share_id: str):
        """Удаление файла раздачи"""
        filepath = self.get_share_file_path(share_id)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
    
    def sync_shares_with_server(self) -> int:
        """Синхронизация локальных раздач с сервером"""
        from ui.console import console
        
        if not self.sync_shares_on_connect:
            return 0
        
        if not self.local_shares:
            return 0
        
        response = self.connection.send_command({'action': MessageActions.MY_SHARES})
        if not response or response.get('status') != 'ok':
            console.print_system_message('Не удалось получить список раздач с сервера', 'error')
            return 0
        
        server_shares = response.get('shares', [])
        server_share_names = {s['name']: s for s in server_shares}
        
        synced_count = 0
        skipped_count = 0
        error_count = 0
        
        local_shares_items = list(self.local_shares.items())
        shares_to_add = {}
        shares_to_remove = []
        
        for share_id, share_data in local_shares_items:
            local_path = share_data.get('local_path')
            share_type = share_data.get('type')
            
            if not local_path or not os.path.exists(local_path):
                skipped_count += 1
                continue
            
            share_name = os.path.basename(local_path)
            
            if share_name in server_share_names:
                skipped_count += 1
                continue
            
            console.print_system_message(f'Синхронизация: {share_name}...', 'info')
            
            if share_type == ShareTypes.FILE:
                file_path = Path(local_path)
                filesize = file_path.stat().st_size
                
                response = self.connection.send_command({
                    'action': MessageActions.SHARE_FILE,
                    'name': share_name,
                    'size': filesize
                })
            else:
                files_list, total_size = get_file_list(local_path)
                
                if not files_list:
                    skipped_count += 1
                    continue
                
                response = self.connection.send_command({
                    'action': MessageActions.SHARE_FOLDER,
                    'name': share_name,
                    'files': files_list,
                    'total_size': total_size
                })
            
            if response and response.get('status') == 'ok':
                new_share_id = response.get('share_id')
                shares_to_add[new_share_id] = {
                    'share_id': new_share_id,
                    'local_path': local_path,
                    'type': share_type,
                    'created_at': time.time()
                }
                shares_to_remove.append(share_id)
                synced_count += 1
            else:
                error_count += 1
        
        for share_id in shares_to_remove:
            self._delete_share_file(share_id)
            self.my_shares.discard(share_id)
            self.local_shares.pop(share_id, None)
        
        for new_share_id, share_data in shares_to_add.items():
            self.local_shares[new_share_id] = share_data
            self.my_shares.add(new_share_id)
            self._save_share_file(new_share_id)
        
        console.print_system_message(f'Синхронизация завершена: {synced_count} синхронизировано, {skipped_count} пропущено', 'info')
        return synced_count
    
    def share(self, path: str):
        """Расшаривание файла или папки"""
        from ui.console import console
        
        path_obj = Path(path)
        if not path_obj.exists():
            console.print_system_message(f'Путь не найден: {path}', 'error')
            return
        
        if path_obj.is_file():
            self._share_file(path_obj)
        elif path_obj.is_dir():
            self._share_folder(path_obj)
    
    def _share_file(self, file_path: Path):
        """Расшаривание файла"""
        from ui.console import console
        
        filename = file_path.name
        filesize = file_path.stat().st_size
        
        console.print_system_message(f'Создание раздачи: {filename} ({format_size(filesize)})', 'info')
        
        response = self.connection.send_command({
            'action': MessageActions.SHARE_FILE,
            'name': filename,
            'size': filesize
        })
        
        if response and response.get('status') == 'ok':
            share_id = response['share_id']
            self.add_local_share(share_id, str(file_path), ShareTypes.FILE)
            console.print_system_message(f'{response["message"]}', 'success')
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def _share_folder(self, folder_path: Path):
        """Расшаривание папки"""
        from ui.console import console
        
        folder_name = folder_path.name
        console.print_system_message(f'Анализ папки: {folder_name}...', 'info')
        
        files_list, total_size = get_file_list(folder_path)
        
        if not files_list:
            console.print_system_message('Папка пуста', 'warning')
            return
        
        console.print_system_message(f'Создание раздачи: {folder_name} ({len(files_list)} файлов)', 'info')
        
        response = self.connection.send_command({
            'action': MessageActions.SHARE_FOLDER,
            'name': folder_name,
            'files': files_list,
            'total_size': total_size
        })
        
        if response and response.get('status') == 'ok':
            share_id = response['share_id']
            self.add_local_share(share_id, str(folder_path), ShareTypes.FOLDER)
            console.print_system_message(f'Раздача создана! ID: {share_id}', 'success')
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def list_shares(self):
        """Получение списка всех раздач"""
        from ui.console import console
        
        response = self.connection.send_command({'action': MessageActions.LIST})
        
        if not response or response.get('status') != 'ok':
            console.print_system_message('Ошибка получения списка', 'error')
            return
        
        shares = response.get('shares', [])
        if not shares:
            console.print_system_message('Нет активных раздач', 'info')
            return
        
        print(f'\nДоступные раздачи (всего: {len(shares)}):')
        print('=' * 70)
        for share in shares:
            self._print_share_info(share)
    
    def list_my_shares(self):
        """Получение списка своих раздач"""
        from ui.console import console
        
        response = self.connection.send_command({'action': MessageActions.MY_SHARES})
        
        if not response or response.get('status') != 'ok':
            console.print_system_message('Ошибка получения списка', 'error')
            return
        
        shares = response.get('shares', [])
        if not shares:
            console.print_system_message('У вас нет активных раздач', 'info')
            return
        
        user_dir = self._get_user_st_dir()
        print(f'\nВаши раздачи (всего: {len(shares)}):')
        print(f'Директория хранения: {os.path.abspath(user_dir)}')
        print('=' * 70)
        for share in shares:
            share_id = share['share_id']
            if share_id in self.local_shares:
                share['_local_path'] = self.local_shares[share_id]['local_path']
                share['_share_file'] = self.get_share_file_path(share_id)
            else:
                share['_local_path'] = 'Не найден'
                share['_share_file'] = 'Отсутствует'
            
            self._print_share_info(share)
    
    def remove_share(self, share_id: str):
        """Удаление раздачи"""
        from ui.console import console
        
        response = self.connection.send_command({
            'action': MessageActions.REMOVE_SHARE,
            'share_id': share_id
        })
        
        if response and response.get('status') == 'ok':
            console.print_system_message(f'{response["message"]}', 'success')
            self.remove_local_share(share_id)
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def _print_share_info(self, share: dict):
        """Вывод информации о раздаче"""
        icon = 'd' if share['type'] == 'folder' else 'f'
        status = 'Онлайн' if share.get('owner_online') else 'Офлайн'
        
        print(f'[{icon}] {status} [{share["share_id"]}] {share["name"]}')
        print(f'   Владелец: {share["username"]} | Тип: {share["type"]}')
        
        if share['type'] == 'file':
            print(f'   Размер: {format_size(share.get("size", 0))}')
        else:
            print(f'   Файлов: {share.get("files_count", 0)} | Размер: {format_size(share.get("total_size", 0))}')
        
        print(f'   Скачиваний: {share.get("downloads", 0)} | Создана: {share.get("created_at", "?")}')
        print(f'   Активность: {share.get("last_active", "?")}')
        
        if '_local_path' in share:
            print(f'   Локальный путь: {share["_local_path"]}')
            print(f'   Файл раздачи: {share["_share_file"]}')
        
        print('-' * 70)
    
    def get_share_ids(self) -> list:
        """Получение списка ID раздач для пинга"""
        return list(self.my_shares)
    
    def get_share_local_path(self, share_id: str) -> str:
        """Получение локального пути для раздачи"""
        if share_id in self.local_shares:
            return self.local_shares[share_id].get('local_path')
        return None
    
    def validate_local_shares(self) -> list:
        """Валидация локальных раздач"""
        invalid_shares = []
        
        for share_id, data in self.local_shares.items():
            local_path = data.get('local_path')
            if not local_path or not os.path.exists(local_path):
                invalid_shares.append(share_id)
        
        return invalid_shares
    
    def cleanup_invalid_shares(self) -> int:
        """Очистка невалидных раздач"""
        invalid = self.validate_local_shares()
        for share_id in invalid:
            self.remove_local_share(share_id)
        return len(invalid)