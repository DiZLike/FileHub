"""
Главный модуль сервера FileHub
"""

import socket
import threading
import time
from datetime import datetime

from config import Config
from logger import Logger
from storage import DataStorage
from security import SecurityManager
from auth import AuthManager
from shares import ShareManager
from networking import NetworkManager
from encryption import EncryptionManager
from protocols import MessageActions, ShareTypes, StatusCodes
from utils import Utils

class FileHubServer:
    """Главный класс сервера FileHub"""
    
    def __init__(self, config_path='filehub.conf'):
        """
        Инициализация сервера
        
        Аргументы:
            config_path: путь к файлу конфигурации
        """
        # Инициализация компонентов
        self.config = Config(config_path)
        self.logger = Logger(self.config)
        self.security = SecurityManager(self.config)
        self.storage = DataStorage(self.config, self.logger)
        self.auth = AuthManager(self.storage, self.security, self.logger)
        self.shares = ShareManager(self.storage, self.config, self.auth, self.logger)
        self.network = NetworkManager(self.config, self.logger)
        self.encryption = EncryptionManager(self.config, self.logger)
        
        # Валидация загруженных раздач
        self.storage.validate_shares(self.config.shares_config['inactive_timeout'])
        
        # Параметры сервера
        server_config = self.config.server_config
        self.host = server_config['host']
        self.port = server_config['port']
        self.data_port = server_config['data_port']
        self.max_connections = server_config['max_connections']
        self.connection_timeout = server_config['connection_timeout']
        
        # Параметры фоновых задач
        shares_config = self.config.shares_config
        self.cleanup_interval = shares_config['cleanup_interval']
        self.save_interval = shares_config['save_interval']
        
        # Состояние сервера
        self.running = True
        self.start_time = datetime.now()
        self.control_socket = None
        self.data_socket = None
        
        self.logger.log('INFO', 'Сервер FileHub инициализирован')
        self.logger.log('INFO', f'Конфигурация загружена из {config_path}')
        self.logger.log('INFO', f'Шифрование: {"включено" if self.encryption.enabled else "выключено"}')
    
    def start(self):
        """Запуск сервера"""
        # Создание сокетов
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.control_socket.bind((self.host, self.port))
            self.control_socket.listen(self.max_connections)
            
            self.data_socket.bind((self.host, self.data_port))
            self.data_socket.listen(self.max_connections)
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка запуска сервера: {e}')
            return
        
        self.logger.log('INFO', 
            f'Сервер запущен: управление {self.host}:{self.port}, данные {self.host}:{self.data_port}')
        self.logger.log('INFO', f'Требуется пароль: {"да" if self.security.require_password else "нет"}')
        self.logger.log('INFO', f'Максимум подключений: {self.max_connections}')
        self.logger.log('INFO', f'Таймаут соединения: {self.connection_timeout}с')
        self.logger.log('INFO', f'Загружено пользователей: {len(self.storage.users)}')
        self.logger.log('INFO', f'Загружено раздач: {len(self.storage.shares)}')
        self.logger.log('INFO', f'Максимум раздач на пользователя: {self.config.security_config["max_shares_per_user"]}')
        self.logger.log('INFO', f'Интервал очистки: {self.cleanup_interval}с')
        self.logger.log('INFO', f'Интервал сохранения: {self.save_interval}с')
        self.logger.log('INFO', f'Таймаут неактивности: {self.config.shares_config["inactive_timeout"]}с')
        self.logger.log('INFO', f'Размер буфера: {self.config.network_config["buffer_size"]} байт')
        self.logger.log('INFO', f'Максимальный размер JSON: {self.config.network_config["max_json_size"]} байт')
        
        if self.config.security_config['blocked_extensions']:
            blocked = ', '.join(self.config.security_config['blocked_extensions'])
            self.logger.log('INFO', f'Запрещённые расширения: {blocked}')
        
        # Запуск обработчиков
        threading.Thread(target=self._accept_data_connections, daemon=True).start()
        threading.Thread(target=self._cleanup_inactive_shares, daemon=True).start()
        threading.Thread(target=self._periodic_save, daemon=True).start()
        threading.Thread(target=self._periodic_stats, daemon=True).start()
        threading.Thread(target=self._cleanup_transfers, daemon=True).start()
        threading.Thread(target=self._cleanup_encryption_keys, daemon=True).start()
        
        self._print_startup_info()
        
        # Главный цикл
        try:
            while self.running:
                try:
                    client_socket, address = self.control_socket.accept()
                    
                    self.logger.log('DEBUG', f'Входящее подключение от {address[0]}:{address[1]}')
                    
                    if not self.security.is_ip_allowed(address[0]):
                        self.logger.log('WARNING', f'Заблокировано подключение от {address[0]}')
                        client_socket.close()
                        continue
                    
                    self.logger.update_stat('total_connections')
                    
                    threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    ).start()
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.log('ERROR', f'Ошибка приёма подключения: {e}')
        
        except KeyboardInterrupt:
            self.logger.log('INFO', 'Получен сигнал завершения')
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Завершение работы сервера"""
        self.logger.log('INFO', 'Завершение работы сервера...')
        self.running = False
        
        # Сохранение данных
        self.logger.log('INFO', f'Сохранение {len(self.storage.shares)} раздач и {len(self.storage.users)} пользователей')
        self.storage.save_shares()
        self.storage.save_users()
        
        # Очистка ключей шифрования
        if self.encryption.enabled:
            key_count = len(self.encryption.session_keys)
            self.logger.log('INFO', f'Очистка {key_count} сессионных ключей шифрования')
            self.encryption.session_keys.clear()
        
        # Закрытие активных соединений
        active_count = len(self.auth.active_users)
        if active_count > 0:
            self.logger.log('INFO', f'Закрытие {active_count} активных соединений')
        for user_info in list(self.auth.active_users.values()):
            try:
                user_info['socket'].close()
            except Exception:
                pass
        
        # Очистка ожидающих трансферов
        pending = len(self.network.pending_transfers)
        if pending > 0:
            self.logger.log('DEBUG', f'Очистка {pending} ожидающих трансферов')
        for transfer in list(self.network.pending_transfers.values()):
            for sock in transfer.values():
                if hasattr(sock, 'close'):
                    try:
                        sock.close()
                    except Exception:
                        pass
        
        # Закрытие серверных сокетов
        if self.control_socket:
            try:
                self.control_socket.close()
            except Exception:
                pass
        
        if self.data_socket:
            try:
                self.data_socket.close()
            except Exception:
                pass
        
        uptime = datetime.now() - self.start_time
        self.logger.log('INFO', f'Сервер остановлен. Время работы: {uptime}')
        self.logger.log('INFO', f'Итоговая статистика - Подключений: {self.logger.stats["total_connections"]}, '
                      f'Раздач: {self.logger.stats["total_shares"]}, '
                      f'Скачиваний: {self.logger.stats["total_downloads"]}, '
                      f'Передано данных: {Utils.format_bytes(self.logger.stats["total_bytes_transferred"])}')
    
    def _handle_client(self, client_socket, address):
        """
        Обработка клиентского соединения
        
        Аргументы:
            client_socket: сокет клиента
            address: адрес клиента
        """
        username = None
        
        # Проверяем, что сокет еще открыт
        try:
            client_socket.settimeout(self.connection_timeout)
        except (OSError, socket.error) as e:
            self.logger.log('ERROR', f'Ошибка установки таймаута для {address[0]}:{address[1]}: {e}')
            try:
                client_socket.close()
            except:
                pass
            return
        
        try:
            # Аутентификация
            login_data = self.network.receive_json(client_socket)
            if not login_data or login_data.get('action') != MessageActions.LOGIN:
                self.logger.log('WARNING', f'Неверные данные входа от {address[0]}:{address[1]}')
                try:
                    client_socket.close()
                except:
                    pass
                return
            
            username = login_data['username']
            password = login_data.get('password', '')
            
            self.logger.log('DEBUG', f'Попытка входа: {username} с {address[0]}')
            
            success, message = self.auth.authenticate_user(username, password)
            
            if not success:
                self.network.send_json(client_socket, {
                    'status': StatusCodes.ERROR,
                    'message': message,
                    'require_password': self.security.require_password
                })
                try:
                    client_socket.close()
                except:
                    pass
                self.logger.log('WARNING', f'Ошибка аутентификации: {username} с {address[0]} - {message}')
                return
            
            # Управление активными пользователями
            self.auth.add_active_user(username, client_socket, address)
            
            # Обновление статуса раздач
            online_shares = self.shares.update_owner_status(username, online=True)
            self.logger.log('DEBUG', f'Обновлено {online_shares} раздач в онлайн для {username}')
            
            # Формирование ответа с информацией о шифровании
            response_data = {
                'status': StatusCodes.OK,
                'message': f'Добро пожаловать, {username}!',
                'require_password': self.security.require_password
            }
            
            # Добавляем информацию о шифровании
            encryption_params = self.encryption.get_encryption_params()
            if encryption_params:
                response_data['encryption'] = encryption_params
            
            self.network.send_json(client_socket, response_data)
            
            self.logger.log('INFO', f'Подключен: {username} ({address[0]}:{address[1]})'
                        f'{" [шифрование]" if encryption_params else ""}')
            
            # Главный цикл обработки команд
            command_count = 0
            while self.running:
                try:
                    request = self.network.receive_json(client_socket)
                except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                    self.logger.log('DEBUG', f'Соединение с {username} потеряно: {e}')
                    break
                except socket.timeout:
                    continue
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка приёма данных от {username}: {e}')
                    break
                
                if not request:
                    break
                
                command_count += 1
                self.auth.update_user_activity(username)
                
                action = request.get('action')
                self.logger.log('DEBUG', f'Команда от {username}: {action}')
                
                try:
                    if action == MessageActions.SHARE_FILE:
                        self._handle_share_file(client_socket, request, username)
                    elif action == MessageActions.SHARE_FOLDER:
                        self._handle_share_folder(client_socket, request, username)
                    elif action == MessageActions.LIST:
                        self._handle_list_shares(client_socket)
                    elif action == MessageActions.MY_SHARES:
                        self._handle_my_shares(client_socket, username)
                    elif action == MessageActions.DOWNLOAD:
                        self._handle_download(client_socket, request, username)
                    elif action == MessageActions.REMOVE_SHARE:
                        self._handle_remove_share(client_socket, request, username)
                    elif action == MessageActions.PING:
                        self._handle_ping(request, username)
                        self.network.send_json(client_socket, {'status': StatusCodes.OK})
                    elif action == MessageActions.STATS:
                        self._handle_stats(client_socket)
                    elif action == MessageActions.LOGOUT:
                        break
                    else:
                        self.logger.log('WARNING', f'Неизвестное действие от {username}: {action}')
                        self.network.send_json(client_socket, {
                            'status': StatusCodes.ERROR,
                            'message': f'Неизвестное действие: {action}'
                        })
                except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                    self.logger.log('DEBUG', f'Ошибка отправки ответа {username}: {e}')
                    break
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка обработки команды {action} от {username}: {e}')
                    try:
                        self.network.send_json(client_socket, {
                            'status': StatusCodes.ERROR,
                            'message': 'Внутренняя ошибка сервера'
                        })
                    except:
                        pass
            
            self.logger.log('DEBUG', f'{username} обработал {command_count} команд')
        
        except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
            self.logger.log('DEBUG', f'Ошибка соединения клиента {username}: {e}')
        except socket.timeout:
            self.logger.log('INFO', f'Таймаут: {username}')
        except Exception as e:
            self.logger.log('ERROR', f'Критическая ошибка клиента {username}: {e}')
        finally:
            # Очистка при отключении
            if username:
                try:
                    # Обновление статуса раздач при отключении
                    offline_shares = self.shares.update_owner_status(username, online=False)
                    self.logger.log('DEBUG', f'Обновлено {offline_shares} раздач в офлайн для {username}')
                    self.auth.remove_active_user(username)
                    self.logger.log('INFO', f'Отключен: {username}')
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка при отключении {username}: {e}')
            
            # Закрываем сокет в любом случае
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
    
    def _handle_share_file(self, client_socket, request, username):
        """
        Обработка создания раздачи файла
        
        Аргументы:
            client_socket: сокет клиента
            request: данные запроса
            username: имя пользователя
        """
        filename = request.get('name', 'неизвестно')
        filesize = request.get('size', 0)
        
        self.logger.log('DEBUG', f'Запрос раздачи файла: {username} -> {filename} ({Utils.format_bytes(filesize)})')
        
        share_id, message = self.shares.create_share(
            username, filename, ShareTypes.FILE, size=filesize
        )
        
        if share_id:
            self.network.send_json(client_socket, {
                'status': StatusCodes.OK,
                'message': message,
                'share_id': share_id
            })
        else:
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': message
            })
    
    def _handle_share_folder(self, client_socket, request, username):
        """
        Обработка создания раздачи папки
        
        Аргументы:
            client_socket: сокет клиента
            request: данные запроса
            username: имя пользователя
        """
        folder_name = request.get('name', 'неизвестно')
        files = request.get('files', [])
        total_size = request.get('total_size', 0)
        
        self.logger.log('DEBUG', f'Запрос раздачи папки: {username} -> {folder_name} ({len(files)} файлов, {Utils.format_bytes(total_size)})')
        
        share_id, message = self.shares.create_share(
            username, folder_name, ShareTypes.FOLDER,
            files=files, total_size=total_size, files_count=len(files)
        )
        
        if share_id:
            self.network.send_json(client_socket, {
                'status': StatusCodes.OK,
                'message': message,
                'share_id': share_id
            })
        else:
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': message
            })
    
    def _handle_list_shares(self, client_socket):
        """
        Обработка запроса списка всех раздач
        
        Аргументы:
            client_socket: сокет клиента
        """
        shares_list = self.shares.get_all_shares()
        self.logger.log('DEBUG', f'Список раздач: возвращено {len(shares_list)} раздач')
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK,
            'shares': shares_list,
            'total': len(shares_list)
        })
    
    def _handle_my_shares(self, client_socket, username):
        """
        Обработка запроса списка своих раздач
        
        Аргументы:
            client_socket: сокет клиента
            username: имя пользователя
        """
        shares_list = self.shares.get_user_shares(username)
        self.logger.log('DEBUG', f'Мои раздачи для {username}: {len(shares_list)} раздач')
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK,
            'shares': shares_list,
            'total': len(shares_list)
        })
    
    def _handle_download(self, client_socket, request, username):
        """
        Обработка запроса на скачивание с поддержкой шифрования
        
        Аргументы:
            client_socket: сокет клиента
            request: данные запроса
            username: имя пользователя
        """
        share_id = request.get('share_id')
        base_name = Utils.get_base_username(username)
        
        self.logger.log('DEBUG', f'Запрос скачивания: {username} -> раздача {share_id}')
        
        share_info = self.shares.get_share_info(share_id)
        if not share_info:
            self.logger.log('WARNING', f'Раздача не найдена: {share_id}')
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': 'Раздача не найдена'
            })
            return
        
        owner = share_info['username']
        
        # Проверка, что владелец онлайн
        owner_socket = self.auth.get_user_socket(owner)
        if not owner_socket:
            self.logger.log('INFO', f'Скачивание не удалось: владелец {owner} офлайн')
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': f'Владелец ({owner}) не в сети'
            })
            return
        
        # Нельзя скачать свою раздачу
        if owner == base_name:
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': 'Нельзя скачать свою раздачу'
            })
            return
        
        # Создание трансфера
        transfer_id = self.network.create_transfer(share_info, base_name)
        
        # Генерация сессионного ключа если включено шифрование
        session_key = None
        if self.encryption.enabled:
            session_key = self.encryption.generate_session_key(transfer_id)
        
        # Отправка запроса владельцу
        upload_request = {
            'action': MessageActions.UPLOAD_REQUEST,
            'share_id': share_id,
            'transfer_id': transfer_id,
            'filename': share_info['name'],
            'type': share_info['type'],
            'requester': base_name
        }
        
        if share_info['type'] == ShareTypes.FILE:
            upload_request.update({
                'size': share_info['size'],
                'files': []
            })
        else:
            upload_request.update({
                'size': share_info['total_size'],
                'files': share_info['files']
            })
        
        # Добавляем информацию о шифровании для отправителя
        if session_key:
            upload_request['encryption'] = {
                'enabled': True,
                'session_key': session_key
            }
        
        self.network.send_json(owner_socket, upload_request)
        
        # Ответ запрашивающему
        download_response = {
            'status': StatusCodes.OK,
            'type': share_info['type'],
            'transfer_id': transfer_id,
            'filename': share_info['name'],
            'data_port': self.data_port
        }
        
        if share_info['type'] == ShareTypes.FILE:
            download_response.update({
                'size': share_info['size'],
                'files': []
            })
        else:
            download_response.update({
                'size': share_info['total_size'],
                'files': share_info['files']
            })
        
        # Добавляем информацию о шифровании для получателя
        if session_key:
            download_response['encryption'] = {
                'enabled': True,
                'session_key': session_key
            }
        
        self.network.send_json(client_socket, download_response)
        self.shares.increment_downloads(share_id)
        
        # Планируем удаление ключа после завершения передачи
        if session_key:
            threading.Thread(
                target=self._delayed_key_cleanup,
                args=(transfer_id,),
                daemon=True
            ).start()
        
        self.logger.log('INFO', 
            f'Трансфер {transfer_id}: {owner} -> {base_name} ({share_info["name"]})'
            f'{" [шифрование]" if session_key else ""}')
    
    def _delayed_key_cleanup(self, transfer_id):
        """
        Отложенное удаление сессионного ключа
        
        Аргументы:
            transfer_id: ID трансфера
        """
        time.sleep(300)  # Ждем 5 минут
        self.encryption.remove_session_key(transfer_id)
    
    def _handle_remove_share(self, client_socket, request, username):
        """
        Обработка запроса на удаление раздачи
        
        Аргументы:
            client_socket: сокет клиента
            request: данные запроса
            username: имя пользователя
        """
        share_id = request.get('share_id')
        self.logger.log('DEBUG', f'Запрос удаления раздачи: {username} -> {share_id}')
        success, message = self.shares.remove_share(share_id, username)
        
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK if success else StatusCodes.ERROR,
            'message': message
        })
    
    def _handle_ping(self, request, username):
        """
        Обработка пинга для поддержания активности
        
        Аргументы:
            request: данные запроса
            username: имя пользователя
        """
        share_ids = request.get('share_ids', [])
        if share_ids:
            self.shares.update_share_activity(share_ids, username)
            self.logger.log('DEBUG', f'Пинг от {username}: обновлено {len(share_ids)} раздач')
    
    def _handle_stats(self, client_socket):
        """
        Обработка запроса статистики
        
        Аргументы:
            client_socket: сокет клиента
        """
        uptime = str(datetime.now() - self.start_time).split('.')[0]
        stats = {
            'status': StatusCodes.OK,
            'server_uptime': uptime,
            'active_users': len(self.auth.active_users),
            'total_shares': len(self.storage.shares),
            'total_connections': self.logger.stats['total_connections'],
            'total_downloads': self.logger.stats['total_downloads'],
            'total_bytes_transferred': Utils.format_bytes(
                self.logger.stats['total_bytes_transferred']
            ),
            'registered_users': len(self.storage.users),
            'require_password': self.security.require_password,
            'encryption': self.encryption.get_stats()
        }
        self.logger.log('DEBUG', f'Запрошена статистика: {stats["active_users"]} пользователей онлайн, {stats["total_shares"]} раздач')
        self.network.send_json(client_socket, stats)
    
    def _accept_data_connections(self):
        """Прием подключений к каналу данных"""
        self.logger.log('DEBUG', 'Прослушивание канала данных запущено')
        while self.running:
            try:
                data_socket, address = self.data_socket.accept()
                self.logger.log('DEBUG', f'Подключение к данным от {address[0]}:{address[1]}')
                threading.Thread(
                    target=self.network.handle_data_connection,
                    args=(data_socket, address),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.log('ERROR', f'Ошибка приёма подключения к данным: {e}')
    
    def _cleanup_inactive_shares(self):
        """Очистка неактивных раздач"""
        self.logger.log('DEBUG', 'Поток очистки раздач запущен')
        while self.running:
            time.sleep(self.cleanup_interval)
            removed = self.shares.cleanup_inactive_shares()
            if removed:
                self.logger.log('INFO', f'Очищено {removed} неактивных раздач')
            else:
                self.logger.log('DEBUG', 'Неактивных раздач для очистки нет')
    
    def _periodic_save(self):
        """Периодическое сохранение данных"""
        self.logger.log('DEBUG', f'Поток периодического сохранения запущен (интервал: {self.save_interval}с)')
        while self.running:
            time.sleep(self.save_interval)
            self.logger.log('DEBUG', f'Сохранение данных: {len(self.storage.shares)} раздач, {len(self.storage.users)} пользователей')
            self.storage.save_shares()
            self.storage.save_users()
    
    def _periodic_stats(self):
        """Периодический вывод статистики"""
        self.logger.log('DEBUG', 'Поток периодической статистики запущен')
        while self.running:
            time.sleep(300)
            online = len(self.auth.active_users)
            encryption_keys = len(self.encryption.session_keys) if self.encryption.enabled else 0
            self.logger.log('INFO', 
                f'Статистика: {online} онлайн, {len(self.storage.shares)} раздач, '
                f'{self.logger.stats["total_downloads"]} скачиваний, '
                f'{Utils.format_bytes(self.logger.stats["total_bytes_transferred"])} передано, '
                f'ключей шифрования: {encryption_keys}')
    
    def _cleanup_transfers(self):
        """Очистка зависших трансферов"""
        self.logger.log('DEBUG', 'Поток очистки трансферов запущен')
        while self.running:
            time.sleep(60)
            removed = self.network.cleanup_transfers()
            if removed:
                self.logger.log('DEBUG', f'Очищено {removed} зависших трансферов')
    
    def _cleanup_encryption_keys(self):
        """Очистка просроченных ключей шифрования"""
        if self.encryption.enabled:
            self.logger.log('DEBUG', 'Поток очистки ключей шифрования запущен')
            while self.running:
                time.sleep(60)
                removed = self.encryption.cleanup_expired_keys()
                if removed > 0:
                    self.logger.log('DEBUG', f'Очищено {removed} ключей шифрования')
    
    def _print_startup_info(self):
        """Вывод информации при запуске"""
        print(f"""
Сервер FileHub
------------------------------
Управление: {self.host}:{self.port}
Данные:     {self.host}:{self.data_port}
Раздач:     {len(self.storage.shares)}
Пользователей: {len(self.storage.users)}
Пароль:     {"да" if self.security.require_password else "нет"}
Шифрование: {"включено" if self.encryption.enabled else "выключено"}
------------------------------
""")


def main():
    """Точка входа"""
    server = FileHubServer('filehub.conf')
    try:
        server.start()
    except KeyboardInterrupt:
        print('\nСервер остановлен')


if __name__ == '__main__':
    main()