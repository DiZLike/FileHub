import socket
import threading
import time
from datetime import datetime

from core.config import ServerConfig
from core.logger import ServerLogger
from core.security import SecurityManager
from services.storage import DataStorage
from services.auth import AuthManager
from services.shares import ShareManager
from network.server import NetworkManager
from network.encryption import EncryptionManager
from network.protocol import MessageActions, StatusCodes
from utils.helpers import format_bytes, get_base_username


class FileHubServer:
    """Главный класс сервера FileHub"""
    
    def __init__(self, config_path='filehub.conf'):
        self.config = ServerConfig(config_path)
        self.logger = ServerLogger(self.config.logging)
        self.security = SecurityManager(self.config.security)
        self.storage = DataStorage(self.config, self.logger)
        self.auth = AuthManager(self.storage, self.security, self.logger)
        self.shares = ShareManager(self.storage, self.config, self.auth, self.logger)
        self.network = NetworkManager(self.config, self.logger)
        self.encryption = EncryptionManager(self.config, self.logger)
        
        self.storage.validate_shares(self.config.shares.inactive_timeout)
        
        server_cfg = self.config.server
        self.host = server_cfg.host
        self.port = server_cfg.port
        self.data_port = server_cfg.data_port
        self.max_connections = server_cfg.max_connections
        self.connection_timeout = server_cfg.connection_timeout
        
        shares_cfg = self.config.shares
        self.cleanup_interval = shares_cfg.cleanup_interval
        self.save_interval = shares_cfg.save_interval
        
        self.running = True
        self.start_time = datetime.now()
        self.control_socket = None
        self.data_socket = None
        
        self.logger.log('INFO', 'Сервер FileHub инициализирован')
        tls_status = 'TLSv1.2+ (самоподписанный сертификат)' if self.encryption.enabled else 'отключено'
        self.logger.log('INFO', f'Шифрование: {tls_status}')
    
    def start(self):
        """Запуск сервера"""
        self.control_socket = self._create_server_socket(self.host, self.port)
        self.data_socket = self._create_server_socket(self.host, self.data_port)
        
        if not self.control_socket or not self.data_socket:
            self.logger.log('ERROR', 'Не удалось запустить сервер')
            return
        
        self._log_runtime_info()
        self._start_background_tasks()
        self._print_banner()
        
        try:
            while self.running:
                try:
                    client_socket, address = self.control_socket.accept()
                    self.logger.log('DEBUG', f'Входящее подключение от {address[0]}:{address[1]}')
                    
                    if not self.security.is_ip_allowed(address[0]):
                        self.logger.log('WARNING', f'Заблокировано подключение от {address[0]}')
                        self._close_socket(client_socket)
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
    
    def _handle_client(self, client_socket, address):
        """Обработка клиентского соединения"""
        username = None
        
        try:
            client_socket.settimeout(self.connection_timeout)
        except (OSError, socket.error) as e:
            self.logger.log('ERROR', f'Ошибка установки таймаута: {e}')
            self._close_socket(client_socket)
            return
        
        try:
            # Этап 1: Приветствие
            hello_data = self.network.receive_json(client_socket)
            if not hello_data or hello_data.get('action') != MessageActions.HELLO:
                self.logger.log('WARNING', f'Неверное приветствие от {address[0]}')
                self._close_socket(client_socket)
                return
            
            encryption_params = self.encryption.get_encryption_params()
            hello_response = {
                'status': StatusCodes.OK,
                'require_password': self.security.require_password,
                'server_version': '1.0'
            }
            if encryption_params:
                hello_response['encryption'] = encryption_params
            
            self.network.send_json(client_socket, hello_response)
            
            # Этап 2: TLS handshake если включён
            if self.encryption.enabled:
                self.logger.log('DEBUG', f'Ожидание TLS handshake от {address[0]}')
                ssl_socket = self.encryption.wrap_socket(client_socket, server_side=True)
                if ssl_socket is None:
                    self.logger.log('WARNING', f'TLS handshake не удался для {address[0]}')
                    self._close_socket(client_socket)
                    return
                client_socket = ssl_socket
                self.logger.log('DEBUG', f'TLS соединение установлено с {address[0]}')
            
            # Этап 3: Аутентификация
            login_data = self.network.receive_json(client_socket)
            if not login_data or login_data.get('action') != MessageActions.LOGIN:
                self.logger.log('WARNING', f'Неверные данные входа от {address[0]}')
                self._close_socket(client_socket)
                return
            
            username = login_data['username']
            password = login_data.get('password', '')
            
            self.logger.log('DEBUG', f'Попытка входа: {username} с {address[0]}')
            
            success, message = self.auth.authenticate(username, password)
            
            if not success:
                self.network.send_json(client_socket, {
                    'status': StatusCodes.ERROR,
                    'message': message,
                    'require_password': self.security.require_password
                })
                self._close_socket(client_socket)
                self.logger.log('WARNING', f'Ошибка аутентификации: {username} - {message}')
                return
            
            self.auth.add_active_user(username, client_socket, address)
            
            online_shares = self.shares.update_owner_status(username, online=True)
            self.logger.log('DEBUG', f'Обновлено {online_shares} раздач в онлайн для {username}')
            
            self.network.send_json(client_socket, {
                'status': StatusCodes.OK,
                'message': f'Добро пожаловать, {username}!',
                'require_password': self.security.require_password
            })
            
            tls_status = ' [TLS]' if self.encryption.enabled else ''
            self.logger.log('INFO', f'Подключен: {username} ({address[0]}:{address[1]}){tls_status}')
            
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
                self.auth.update_activity(username)
                
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
                    self.logger.log('ERROR', f'Ошибка обработки команды {action}: {e}')
                    try:
                        self.network.send_json(client_socket, {
                            'status': StatusCodes.ERROR,
                            'message': 'Внутренняя ошибка сервера'
                        })
                    except Exception:
                        pass
            
            self.logger.log('DEBUG', f'{username} обработал {command_count} команд')
        
        except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
            self.logger.log('DEBUG', f'Ошибка соединения клиента {username}: {e}')
        except socket.timeout:
            self.logger.log('INFO', f'Таймаут: {username}')
        except Exception as e:
            self.logger.log('ERROR', f'Критическая ошибка клиента {username}: {e}')
        finally:
            if username:
                try:
                    offline_shares = self.shares.update_owner_status(username, online=False)
                    self.logger.log('DEBUG', f'Обновлено {offline_shares} раздач в офлайн для {username}')
                    self.auth.remove_active_user(username)
                    self.logger.log('INFO', f'Отключен: {username}')
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка при отключении {username}: {e}')
            
            self._close_socket(client_socket)
    
    def _handle_share_file(self, client_socket, request, username):
        filename = request.get('name', 'неизвестно')
        filesize = request.get('size', 0)
        
        self.logger.log('DEBUG', f'Запрос раздачи файла: {username} -> {filename} ({format_bytes(filesize)})')
        
        share_id, message = self.shares.create_share(username, filename, 'file', size=filesize)
        
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
        folder_name = request.get('name', 'неизвестно')
        files = request.get('files', [])
        total_size = request.get('total_size', 0)
        
        self.logger.log('DEBUG', f'Запрос раздачи папки: {username} -> {folder_name} ({len(files)} файлов)')
        
        share_id, message = self.shares.create_share(
            username, folder_name, 'folder',
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
        shares_list = self.shares.get_all_shares()
        self.logger.log('DEBUG', f'Список раздач: возвращено {len(shares_list)}')
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK,
            'shares': shares_list,
            'total': len(shares_list)
        })
    
    def _handle_my_shares(self, client_socket, username):
        shares_list = self.shares.get_user_shares(username)
        self.logger.log('DEBUG', f'Мои раздачи для {username}: {len(shares_list)}')
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK,
            'shares': shares_list,
            'total': len(shares_list)
        })
    
    def _handle_download(self, client_socket, request, username):
        share_id = request.get('share_id')
        base_name = get_base_username(username)
        
        self.logger.log('DEBUG', f'Запрос скачивания: {username} -> {share_id}')
        
        share_info = self.shares.get_share_info(share_id)
        if not share_info:
            self.logger.log('WARNING', f'Раздача не найдена: {share_id}')
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': 'Раздача не найдена'
            })
            return
        
        owner = share_info['username']
        
        owner_socket = self.auth.get_user_socket(owner)
        if not owner_socket:
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': f'Владелец ({owner}) не в сети'
            })
            return
        
        if owner == base_name:
            self.network.send_json(client_socket, {
                'status': StatusCodes.ERROR,
                'message': 'Нельзя скачать свою раздачу'
            })
            return
        
        transfer_id = self.network.create_transfer(share_info, base_name)
        
        upload_request = {
            'action': MessageActions.UPLOAD_REQUEST,
            'share_id': share_id,
            'transfer_id': transfer_id,
            'filename': share_info['name'],
            'type': share_info['type'],
            'requester': base_name
        }
        
        if share_info['type'] == 'file':
            upload_request.update({'size': share_info['size'], 'files': []})
        else:
            upload_request.update({'size': share_info['total_size'], 'files': share_info['files']})
        
        encryption_params = self.encryption.get_encryption_params()
        if encryption_params:
            upload_request['encryption'] = encryption_params
        
        self.network.send_json(owner_socket, upload_request)
        
        download_response = {
            'status': StatusCodes.OK,
            'type': share_info['type'],
            'transfer_id': transfer_id,
            'filename': share_info['name'],
            'data_port': self.data_port
        }
        
        if share_info['type'] == 'file':
            download_response.update({'size': share_info['size'], 'files': []})
        else:
            download_response.update({'size': share_info['total_size'], 'files': share_info['files']})
        
        if encryption_params:
            download_response['encryption'] = encryption_params
        
        self.network.send_json(client_socket, download_response)
        self.shares.increment_downloads(share_id)
        
        tls_status = ' [TLS]' if encryption_params else ''
        self.logger.log('INFO', f'Трансфер {transfer_id}: {owner} -> {base_name} ({share_info["name"]}){tls_status}')
    
    def _handle_remove_share(self, client_socket, request, username):
        share_id = request.get('share_id')
        self.logger.log('DEBUG', f'Запрос удаления: {username} -> {share_id}')
        success, message = self.shares.remove_share(share_id, username)
        
        self.network.send_json(client_socket, {
            'status': StatusCodes.OK if success else StatusCodes.ERROR,
            'message': message
        })
    
    def _handle_ping(self, request, username):
        share_ids = request.get('share_ids', [])
        if share_ids:
            self.shares.update_share_activity(share_ids, username)
            self.logger.log('DEBUG', f'Пинг от {username}: обновлено {len(share_ids)} раздач')
    
    def _handle_stats(self, client_socket):
        uptime = str(datetime.now() - self.start_time).split('.')[0]
        stats = {
            'status': StatusCodes.OK,
            'server_uptime': uptime,
            'active_users': self.auth.get_online_count(),
            'total_shares': len(self.storage.shares),
            'total_connections': self.logger.stats['total_connections'],
            'total_downloads': self.logger.stats['total_downloads'],
            'total_bytes_transferred': format_bytes(self.logger.stats['total_bytes_transferred']),
            'registered_users': len(self.storage.users),
            'require_password': self.security.require_password,
            'encryption': self.encryption.get_stats()
        }
        self.network.send_json(client_socket, stats)
    
    def _accept_data_connections(self):
        """Приём подключений к каналу данных"""
        self.logger.log('DEBUG', 'Прослушивание канала данных запущено')
        while self.running:
            try:
                data_socket, address = self.data_socket.accept()
                self.logger.log('DEBUG', f'Подключение к данным от {address[0]}:{address[1]}')
                
                if self.encryption.enabled:
                    ssl_socket = self.encryption.wrap_socket(data_socket, server_side=True)
                    if ssl_socket is None:
                        self._close_socket(data_socket)
                        continue
                    data_socket = ssl_socket
                    self.logger.log('DEBUG', f'TLS канал данных установлен с {address[0]}')
                
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
            removed = self.shares.cleanup_inactive()
            if removed:
                self.logger.log('INFO', f'Очищено {removed} неактивных раздач')
    
    def _periodic_save(self):
        """Периодическое сохранение данных"""
        self.logger.log('DEBUG', f'Поток сохранения запущен (интервал: {self.save_interval}с)')
        while self.running:
            time.sleep(self.save_interval)
            self.storage.save_shares()
            self.storage.save_users()
    
    def _periodic_stats(self):
        """Периодический вывод статистики"""
        self.logger.log('DEBUG', 'Поток статистики запущен')
        while self.running:
            time.sleep(300)
            online = self.auth.get_online_count()
            self.logger.log('INFO', 
                f'Статистика: {online} онлайн, {len(self.storage.shares)} раздач, '
                f'{self.logger.stats["total_downloads"]} скачиваний, '
                f'{format_bytes(self.logger.stats["total_bytes_transferred"])} передано')
    
    def _cleanup_transfers(self):
        """Очистка зависших трансферов"""
        self.logger.log('DEBUG', 'Поток очистки трансферов запущен')
        while self.running:
            time.sleep(60)
            removed = self.network.cleanup_transfers()
            if removed:
                self.logger.log('DEBUG', f'Очищено {removed} зависших трансферов')
    
    def _start_background_tasks(self):
        """Запуск фоновых задач"""
        tasks = [
            self._accept_data_connections,
            self._cleanup_inactive_shares,
            self._periodic_save,
            self._periodic_stats,
            self._cleanup_transfers
        ]
        for task in tasks:
            threading.Thread(target=task, daemon=True).start()
    
    def _log_runtime_info(self):
        """Вывод информации о запуске"""
        self.logger.log('INFO', f'Сервер запущен: управление {self.host}:{self.port}, данные {self.host}:{self.data_port}')
        self.logger.log('INFO', f'Требуется пароль: {"да" if self.security.require_password else "нет"}')
        self.logger.log('INFO', f'Загружено пользователей: {len(self.storage.users)}')
        self.logger.log('INFO', f'Загружено раздач: {len(self.storage.shares)}')
        
        blocked_extensions = self.config.security.blocked_extensions
        if blocked_extensions:
            self.logger.log('INFO', f'Запрещённые расширения: {", ".join(blocked_extensions)}')
    
    def _print_banner(self):
        """Вывод баннера при запуске"""
        tls_status = 'TLSv1.2+ (самоподписанный сертификат)' if self.encryption.enabled else 'отключено'
        print(f"""
Сервер FileHub
------------------------------
Управление: {self.host}:{self.port}
Данные:     {self.host}:{self.data_port}
Раздач:     {len(self.storage.shares)}
Пользователей: {len(self.storage.users)}
Пароль:     {"да" if self.security.require_password else "нет"}
Шифрование: {tls_status}
------------------------------
""")
    
    def shutdown(self):
        """Завершение работы сервера"""
        self.logger.log('INFO', 'Завершение работы сервера...')
        self.running = False
        
        self.storage.save_shares()
        self.storage.save_users()
        
        if self.encryption.enabled:
            self.logger.log('INFO', 'TLS шифрование было активно')
        
        active_count = self.auth.get_online_count()
        if active_count > 0:
            self.logger.log('INFO', f'Закрытие {active_count} активных соединений')
        for user_info in list(self.auth.active_users.values()):
            self._close_socket(user_info.get('socket'))
        
        self._close_socket(self.control_socket)
        self._close_socket(self.data_socket)
        
        uptime = datetime.now() - self.start_time
        self.logger.log('INFO', f'Сервер остановлен. Время работы: {uptime}')
    
    @staticmethod
    def _create_server_socket(host, port):
        """Создание серверного сокета"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(10)
            return sock
        except Exception as e:
            print(f'Ошибка создания сокета {host}:{port}: {e}')
            return None
    
    @staticmethod
    def _close_socket(sock):
        """Безопасное закрытие сокета"""
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass


def main():
    """Точка входа"""
    server = FileHubServer('filehub.conf')
    try:
        server.start()
    except KeyboardInterrupt:
        print('\nСервер остановлен')


if __name__ == '__main__':
    main()