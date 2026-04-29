"""
Управление раздачами файлов
"""

import json
import os
import time
import threading
from pathlib import Path
from protocols import MessageActions, ShareTypes
from utils import Utils
from console_ui import console

class ShareManager:
    """Менеджер раздач клиента"""
    
    def __init__(self, connection, config):
        """
        Инициализация менеджера раздач
        
        Аргументы:
            connection: менеджер подключений
            config: конфигурация клиента
        """
        self.connection = connection
        self.local_shares = {}  # Кэш в памяти: share_id -> данные раздачи
        self.my_shares = set()  # Множество ID раздач для быстрой проверки
        self.show_progress = config.interface_config['show_progress']
        
        # Конфигурация для отдельных файлов раздач
        shares_cfg = config.shares_config
        self.st_dir = shares_cfg['st_dir']
        self.st_file_template = shares_cfg['st_file']
        self.sync_shares_on_connect = shares_cfg['sync_shares_on_connect']
        
        # Путь к подпапке пользователя будет установлен после подключения
        self._user_st_dir = None
        
        # Загружаем существующие раздачи
        self.load_local_shares()
    
    def _get_user_st_dir(self):
        """
        Получение пути к директории раздач пользователя
        
        Возвращает:
            путь к директории раздач пользователя
        """
        if self._user_st_dir is None:
            if self.connection and self.connection.username:
                self._user_st_dir = os.path.join(self.st_dir, self.connection.username)
            else:
                self._user_st_dir = self.st_dir
        return self._user_st_dir
    
    def _ensure_user_st_dir(self):
        """Создание директории для файлов раздач пользователя"""
        user_dir = self._get_user_st_dir()
        try:
            os.makedirs(user_dir, exist_ok=True)
            console.print_system_message(f'Директория раздач: {os.path.abspath(user_dir)}', 'info')
        except Exception as e:
            console.print_system_message(f'Ошибка создания директории {user_dir}: {e}', 'error')
    
    def get_share_file_path(self, share_id):
        """
        Получение пути к файлу раздачи в подпапке пользователя
        
        Аргументы:
            share_id: ID раздачи
            
        Возвращает:
            путь к файлу
        """
        user_dir = self._get_user_st_dir()
        filename = self.st_file_template.replace('{share_id}', share_id)
        return os.path.join(user_dir, filename)
    
    def get_old_share_file_path(self, share_id):
        """
        Получение старого пути к файлу раздачи (в корне my_shares)
        
        Аргументы:
            share_id: ID раздачи
            
        Возвращает:
            старый путь к файлу
        """
        filename = self.st_file_template.replace('{share_id}', share_id)
        return os.path.join(self.st_dir, filename)
    
    def load_local_shares(self):
        """Загрузка информации о локальных раздачах из подпапки пользователя"""
        self.local_shares.clear()
        self.my_shares.clear()
        
        # Если пользователь ещё не подключён, откладываем загрузку
        if not self.connection or not self.connection.username:
            console.print_system_message('Ожидание подключения для загрузки раздач...', 'info')
            return
        
        user_dir = self._get_user_st_dir()
        
        # Создаем директорию если её нет
        self._ensure_user_st_dir()
        
        # Сначала пробуем загрузить из подпапки пользователя
        loaded_count = 0
        error_count = 0
        
        if os.path.exists(user_dir):
            try:
                for filename in os.listdir(user_dir):
                    filepath = os.path.join(user_dir, filename)
                    
                    # Пропускаем не-файлы
                    if not os.path.isfile(filepath):
                        continue
                    
                    # Пропускаем не-JSON файлы
                    if not filename.endswith('.json'):
                        continue
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            share_data = json.load(f)
                        
                        share_id = share_data.get('share_id')
                        if not share_id:
                            console.print_system_message(f'Предупреждение: файл {filename}: отсутствует share_id, пропущен', 'warning')
                            error_count += 1
                            continue
                        
                        self.local_shares[share_id] = share_data
                        self.my_shares.add(share_id)
                        loaded_count += 1
                        
                    except json.JSONDecodeError:
                        console.print_system_message(f'Предупреждение: файл {filename}: невалидный JSON, пропущен', 'warning')
                        error_count += 1
                    except Exception as e:
                        console.print_system_message(f'Предупреждение: ошибка чтения {filename}: {e}', 'warning')
                        error_count += 1
                
                if loaded_count > 0:
                    console.print_system_message(f'Загружено {loaded_count} локальных раздач из {user_dir}', 'info')
                if error_count > 0:
                    console.print_system_message(f'Пропущено {error_count} файлов с ошибками', 'warning')
                
            except Exception as e:
                console.print_system_message(f'Ошибка сканирования директории {user_dir}: {e}', 'error')
        
        # Затем мигрируем старые файлы из корневой папки my_shares
        if user_dir != self.st_dir:
            migrated = self._migrate_old_shares()
            if migrated > 0:
                console.print_system_message(f'Мигрировано {migrated} старых раздач в {user_dir}', 'info')
    
    def reload_shares_for_user(self):
        """
        Перезагрузка раздач после установки имени пользователя
        Должен вызываться после успешного подключения
        """
        # Сбрасываем кэш пути
        self._user_st_dir = None
        # Перезагружаем раздачи
        self.load_local_shares()

    def _migrate_old_shares(self):
        """
        Миграция старых файлов раздач из корневой папки в подпапку пользователя
        
        Возвращает:
            количество мигрированных файлов
        """
        if not os.path.exists(self.st_dir):
            return 0
        
        user_dir = self._get_user_st_dir()
        if user_dir == self.st_dir:
            return 0
        
        migrated_count = 0
        
        try:
            for filename in os.listdir(self.st_dir):
                old_filepath = os.path.join(self.st_dir, filename)
                
                # Пропускаем подпапки (это уже директории пользователей)
                if os.path.isdir(old_filepath):
                    continue
                
                # Проверяем, что это JSON файл раздачи
                if not filename.endswith('.json'):
                    continue
                
                # Проверяем, что это действительно файл раздачи (содержит share_id)
                try:
                    with open(old_filepath, 'r', encoding='utf-8') as f:
                        share_data = json.load(f)
                    
                    share_id = share_data.get('share_id')
                    if not share_id:
                        continue
                    
                    # Определяем новый путь
                    new_filepath = os.path.join(user_dir, filename)
                    
                    # Перемещаем только если такого файла еще нет в новой директории
                    if not os.path.exists(new_filepath):
                        import shutil
                        shutil.move(old_filepath, new_filepath)
                        
                        # Добавляем в кэш если еще не добавлена
                        if share_id not in self.local_shares:
                            self.local_shares[share_id] = share_data
                            self.my_shares.add(share_id)
                        
                        migrated_count += 1
                    else:
                        # Файл уже существует в новой директории, удаляем старый
                        os.remove(old_filepath)
                        
                except json.JSONDecodeError:
                    # Не JSON файл, пропускаем
                    continue
                except Exception as e:
                    console.print_system_message(f'Предупреждение: ошибка миграции {filename}: {e}', 'warning')
                    continue
            
        except Exception as e:
            console.print_system_message(f'Ошибка миграции старых раздач: {e}', 'error')
        
        return migrated_count
    
    def save_share_file(self, share_id):
        """
        Сохранение отдельного файла раздачи в подпапке пользователя
        
        Аргументы:
            share_id: ID раздачи
        """
        if share_id not in self.local_shares:
            return
        
        filepath = self.get_share_file_path(share_id)
        
        try:
            # Убеждаемся, что директория существует
            file_dir = os.path.dirname(filepath)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.local_shares[share_id], f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print_system_message(f'Ошибка сохранения раздачи {share_id}: {e}', 'error')
    
    def delete_share_file(self, share_id):
        """
        Удаление файла раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        # Пробуем удалить из новой подпапки пользователя
        filepath = self.get_share_file_path(share_id)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                # Пытаемся удалить пустую родительскую директорию
                parent_dir = os.path.dirname(filepath)
                if parent_dir and parent_dir != self._get_user_st_dir() and parent_dir != self.st_dir:
                    try:
                        if not os.listdir(parent_dir):
                            os.rmdir(parent_dir)
                    except:
                        pass
        except Exception as e:
            console.print_system_message(f'Ошибка удаления файла раздачи {share_id}: {e}', 'error')
        
        # Также пробуем удалить старый файл если он есть
        old_filepath = self.get_old_share_file_path(share_id)
        if old_filepath != filepath and os.path.exists(old_filepath):
            try:
                os.remove(old_filepath)
            except Exception as e:
                console.print_system_message(f'Ошибка удаления старого файла раздачи {share_id}: {e}', 'error')
    
    def add_local_share(self, share_id, local_path, share_type):
        """
        Добавление локальной раздачи
        
        Аргументы:
            share_id: ID раздачи
            local_path: локальный путь
            share_type: тип раздачи
        """
        share_data = {
            'share_id': share_id,
            'local_path': local_path,
            'type': share_type,
            'created_at': time.time()
        }
        
        self.local_shares[share_id] = share_data
        self.my_shares.add(share_id)
        
        # Сохраняем в отдельный файл в подпапке пользователя
        self.save_share_file(share_id)
    
    def remove_local_share(self, share_id):
        """
        Удаление локальной раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        self.my_shares.discard(share_id)
        if share_id in self.local_shares:
            del self.local_shares[share_id]
        
        # Удаляем файл раздачи
        self.delete_share_file(share_id)
    
    def sync_shares_with_server(self):
        """
        Синхронизация локальных раздач с сервером
        
        Возвращает:
            количество синхронизированных раздач
        """
        if not self.sync_shares_on_connect:
            console.print_system_message('Синхронизация раздач отключена в настройках', 'info')
            return 0
        
        if not self.local_shares:
            console.print_system_message('Нет локальных раздач для синхронизации', 'info')
            return 0
        
        # Получаем список раздач на сервере
        response = self.connection.send_command({'action': MessageActions.MY_SHARES})
        if not response or response.get('status') != 'ok':
            console.print_system_message('Не удалось получить список раздач с сервера для синхронизации', 'error')
            return 0
        
        server_shares = response.get('shares', [])
        server_share_names = {s['name']: s for s in server_shares}
        
        synced_count = 0
        skipped_count = 0
        error_count = 0
        
        console.print_system_message(f'Синхронизация раздач: локально {len(self.local_shares)}, на сервере {len(server_shares)}', 'info')
        
        # Создаем копию списка элементов для безопасной итерации
        local_shares_items = list(self.local_shares.items())
        
        # Собираем изменения, которые нужно применить после итерации
        shares_to_add = {}
        shares_to_remove = []
        
        for share_id, share_data in local_shares_items:
            local_path = share_data.get('local_path')
            share_type = share_data.get('type')
            
            if not local_path:
                console.print_system_message(f'  Пропущена раздача {share_id}: отсутствует локальный путь', 'warning')
                skipped_count += 1
                continue
            
            if not os.path.exists(local_path):
                console.print_system_message(f'  Пропущена раздача {share_id}: путь не найден ({local_path})', 'warning')
                skipped_count += 1
                continue
            
            # Проверяем, есть ли такая раздача на сервере
            share_name = os.path.basename(local_path)
            
            if share_name in server_share_names:
                console.print_system_message(f'  Раздача "{share_name}" уже существует на сервере (ID: {server_share_names[share_name]["share_id"]})', 'info')
                skipped_count += 1
                continue
            
            # Создаем раздачу на сервере
            console.print_system_message(f'  Синхронизация: {share_name} ({share_type})...', 'info')
            
            if share_type == ShareTypes.FILE:
                file_path = Path(local_path)
                filesize = file_path.stat().st_size
                
                response = self.connection.send_command({
                    'action': MessageActions.SHARE_FILE,
                    'name': share_name,
                    'size': filesize
                })
            else:
                files_list, total_size = Utils.get_file_list(local_path)
                
                if not files_list:
                    console.print_system_message(f'    Папка пуста, пропущена', 'warning')
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
                console.print_system_message(f'    Успешно синхронизирована, новый ID: {new_share_id}', 'success')
                
                # Сохраняем изменения для применения после итерации
                shares_to_add[new_share_id] = {
                    'share_id': new_share_id,
                    'local_path': local_path,
                    'type': share_type,
                    'created_at': time.time()
                }
                shares_to_remove.append(share_id)
                
                synced_count += 1
            else:
                error_msg = response.get('message', 'Неизвестная ошибка') if response else 'Нет ответа'
                console.print_system_message(f'    Ошибка синхронизации: {error_msg}', 'error')
                error_count += 1
        
        # Применяем изменения после завершения итерации
        for share_id in shares_to_remove:
            # Удаляем старый файл раздачи
            self.delete_share_file(share_id)
            # Удаляем из множеств
            self.my_shares.discard(share_id)
            if share_id in self.local_shares:
                del self.local_shares[share_id]
        
        for new_share_id, share_data in shares_to_add.items():
            self.local_shares[new_share_id] = share_data
            self.my_shares.add(new_share_id)
            # Сохраняем новый файл раздачи
            self.save_share_file(new_share_id)
        
        console.print_system_message(f'Синхронизация завершена: синхронизировано {synced_count}, пропущено {skipped_count}, ошибок {error_count}', 'info')
        return synced_count
    
    def share(self, path):
        """
        Расшаривание файла или папки
        
        Аргументы:
            path: путь к файлу или папке
        """
        path_obj = Path(path)
        if not path_obj.exists():
            console.print_system_message(f'Путь не найден: {path}', 'error')
            return
        
        if path_obj.is_file():
            self._share_file(path_obj)
        elif path_obj.is_dir():
            self._share_folder(path_obj)
    
    def _share_file(self, file_path):
        """
        Расшаривание файла
        
        Аргументы:
            file_path: путь к файлу
        """
        filename = file_path.name
        filesize = file_path.stat().st_size
        
        console.print_system_message(f'Создание раздачи: {filename} ({Utils.format_size(filesize)})', 'info')
        
        response = self.connection.send_command({
            'action': MessageActions.SHARE_FILE,
            'name': filename,
            'size': filesize
        })
        
        if response and response.get('status') == 'ok':
            share_id = response['share_id']
            self.add_local_share(share_id, str(file_path), ShareTypes.FILE)
            console.print_system_message(f'{response["message"]}', 'success')
            console.print_system_message(f'Файл раздачи: {self.get_share_file_path(share_id)}', 'info')
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def _share_folder(self, folder_path):
        """
        Расшаривание папки
        
        Аргументы:
            folder_path: путь к папке
        """
        folder_name = folder_path.name
        console.print_system_message(f'Анализ папки: {folder_name}...', 'info')
        
        files_list, total_size = Utils.get_file_list(folder_path)
        
        if not files_list:
            console.print_system_message('Папка пуста', 'warning')
            return
        
        console.print_system_message(f'Создание раздачи: {folder_name} ({len(files_list)} файлов, {Utils.format_size(total_size)})', 'info')
        
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
            console.print_system_message(f'Файл раздачи: {self.get_share_file_path(share_id)}', 'info')
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def list_shares(self):
        """Получение списка всех раздач"""
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
            # Проверяем, есть ли локальный файл для этой раздачи
            share_id = share['share_id']
            if share_id in self.local_shares:
                share['_local_path'] = self.local_shares[share_id]['local_path']
                share['_share_file'] = self.get_share_file_path(share_id)
            else:
                share['_local_path'] = 'Не найден'
                share['_share_file'] = 'Отсутствует'
            
            self._print_share_info(share)
    
    def remove_share(self, share_id):
        """
        Удаление раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        response = self.connection.send_command({
            'action': MessageActions.REMOVE_SHARE,
            'share_id': share_id
        })
        
        if response and response.get('status') == 'ok':
            console.print_system_message(f'{response["message"]}', 'success')
            # Показываем путь к удаляемому файлу
            share_file = self.get_share_file_path(share_id)
            console.print_system_message(f'Удален файл раздачи: {share_file}', 'info')
            self.remove_local_share(share_id)
        else:
            error_msg = response.get('message', 'Ошибка') if response else 'Нет ответа'
            console.print_system_message(f'{error_msg}', 'error')
    
    def _print_share_info(self, share):
        """
        Вывод информации о раздаче
        
        Аргументы:
            share: данные раздачи
        """
        icon = 'd' if share['type'] == 'folder' else 'f'
        status = 'Онлайн' if share.get('owner_online') else 'Офлайн'
        
        print(f'[{icon}] {status} [{share["share_id"]}] {share["name"]}')
        print(f'   Владелец: {share["username"]} | Тип: {share["type"]}')
        
        if share['type'] == 'file':
            print(f'   Размер: {Utils.format_size(share.get("size", 0))}')
        else:
            print(f'   Файлов: {share.get("files_count", 0)} | Размер: {Utils.format_size(share.get("total_size", 0))}')
        
        print(f'   Скачиваний: {share.get("downloads", 0)} | Создана: {share.get("created_at", "?")}')
        print(f'   Активность: {share.get("last_active", "?")}')
        
        # Дополнительная информация для своих раздач
        if '_local_path' in share:
            print(f'   Локальный путь: {share["_local_path"]}')
            print(f'   Файл раздачи: {share["_share_file"]}')
        
        print('-' * 70)
    
    def get_share_ids(self):
        """
        Получение списка ID раздач для пинга
        
        Возвращает:
            список ID раздач
        """
        return list(self.my_shares)
    
    def get_share_local_path(self, share_id):
        """
        Получение локального пути для раздачи
        
        Аргументы:
            share_id: ID раздачи
            
        Возвращает:
            локальный путь или None
        """
        if share_id in self.local_shares:
            return self.local_shares[share_id].get('local_path')
        return None
    
    def validate_local_shares(self):
        """
        Валидация локальных раздач (проверка существования путей)
        
        Возвращает:
            список невалидных ID раздач
        """
        invalid_shares = []
        
        for share_id, data in self.local_shares.items():
            local_path = data.get('local_path')
            if not local_path:
                invalid_shares.append(share_id)
                console.print_system_message(f'Предупреждение: раздача {share_id}: отсутствует локальный путь', 'warning')
            elif not os.path.exists(local_path):
                invalid_shares.append(share_id)
                console.print_system_message(f'Предупреждение: раздача {share_id}: путь не найден ({local_path})', 'warning')
        
        return invalid_shares
    
    def cleanup_invalid_shares(self):
        """
        Очистка невалидных раздач
        
        Возвращает:
            количество удалённых раздач
        """
        invalid = self.validate_local_shares()
        for share_id in invalid:
            console.print_system_message(f'Удаление невалидной раздачи: {share_id}', 'info')
            # Удаляем файл раздачи
            share_file = self.get_share_file_path(share_id)
            if os.path.exists(share_file):
                console.print_system_message(f'   Удален файл: {share_file}', 'info')
            self.remove_local_share(share_id)
        return len(invalid)