"""
Сетевое подключение клиента
"""

import socket
import json
import threading
import time
from protocols import MessageActions, MAX_JSON_SIZE, JSON_BUFFER_SIZE
from console_ui import console


class ConnectionManager:
    """Менеджер сетевых подключений"""
    
    def __init__(self, config):
        """
        Инициализация менеджера подключений
        
        Аргументы:
            config: конфигурация клиента
        """
        conn_config = config.connection_config
        self.server_host = conn_config['server_host']
        self.server_port = conn_config['server_port']
        self.data_port = conn_config['data_port']
        self.connection_timeout = conn_config['connection_timeout']
        
        self.control_socket = None
        self.connected = False
        self.username = None
        self.password = None
        self.require_password = False
        self.last_response = None  # Последний ответ сервера
        
        # Для синхронизации доступа к сокету
        self._socket_lock = threading.Lock()
        self._pending_response = None
        self._response_event = threading.Event()
        self._listener_thread = None
        
        # Для безопасного завершения
        self._shutdown_event = threading.Event()
        
        # Колбэки
        self.on_upload_request = None
        self.on_disconnect = None
    
    def connect(self, username, password):
        """
        Подключение к серверу
        
        Аргументы:
            username: имя пользователя
            password: пароль
            
        Возвращает:
            True при успешном подключении
        """
        # Сначала отключаемся от предыдущего соединения если есть
        if self.connected:
            self.disconnect()
        
        self.username = username
        self.password = password
        self._shutdown_event.clear()
        
        try:
            # Основной сокет управления
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(self.connection_timeout)
            self.control_socket.connect((self.server_host, self.server_port))
            
            # Отправка логина
            login_data = {
                'action': MessageActions.LOGIN,
                'username': username,
                'password': password
            }
            
            self.send_json(self.control_socket, login_data)
            response = self.receive_json(self.control_socket, 10)
            
            # Сохраняем ответ для дальнейшего использования
            self.last_response = response
            
            if not response or response.get('status') != 'ok':
                error_msg = response.get('message', 'Неизвестная ошибка') if response else 'Нет ответа'
                console.print_system_message(f'Ошибка: {error_msg}', 'error')
                try:
                    self.control_socket.close()
                except:
                    pass
                self.control_socket = None
                return False
            
            self.require_password = response.get('require_password', False)
            console.print_system_message(f'{response["message"]}', 'success')
            
            self.connected = True
            
            # Запуск обработчика входящих сообщений
            self._listener_thread = threading.Thread(
                target=self._command_listener, 
                daemon=True,
                name="CommandListener"
            )
            self._listener_thread.start()
            
            return True
        
        except socket.timeout:
            console.print_system_message('Таймаут подключения к серверу', 'error')
            if self.control_socket:
                try:
                    self.control_socket.close()
                except:
                    pass
                self.control_socket = None
            return False
        except ConnectionRefusedError:
            console.print_system_message('Сервер недоступен (отказ в подключении)', 'error')
            if self.control_socket:
                try:
                    self.control_socket.close()
                except:
                    pass
                self.control_socket = None
            return False
        except Exception as e:
            console.print_system_message(f'Ошибка подключения: {e}', 'error')
            if self.control_socket:
                try:
                    self.control_socket.close()
                except:
                    pass
                self.control_socket = None
            return False
    
    def disconnect(self):
        """Отключение от сервера"""
        was_connected = self.connected
        self.connected = False
        self._shutdown_event.set()
        
        # Закрываем сокет
        if self.control_socket:
            try:
                try:
                    self.send_json(self.control_socket, {'action': MessageActions.LOGOUT})
                except:
                    pass
                try:
                    self.control_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.control_socket.close()
            except Exception:
                pass
            self.control_socket = None
        
        # Ожидаем завершения потока слушателя
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2)
        
        self._listener_thread = None
        self.last_response = None
        
        if was_connected:
            console.print_system_message('Отключено', 'info')
        
        if self.on_disconnect:
            self.on_disconnect()
    
    def send_json(self, sock, data):
        """
        Отправка JSON-сообщения
        
        Аргументы:
            sock: сокет
            data: данные для отправки
        """
        if not sock:
            return
        
        try:
            json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            sock.sendall(len(json_data).to_bytes(4, 'big') + json_data)
        except Exception:
            pass
    
    def receive_json(self, sock, timeout_sec):
        """
        Получение JSON-сообщения
        
        Аргументы:
            sock: сокет
            timeout_sec: таймаут в секундах
            
        Возвращает:
            распарсенный JSON или None
        """
        if not sock:
            return None
        
        try:
            sock.settimeout(timeout_sec)
            
            # Чтение длины
            raw_len = b''
            while len(raw_len) < 4:
                chunk = sock.recv(4 - len(raw_len))
                if not chunk:
                    return None
                raw_len += chunk
            
            msg_length = int.from_bytes(raw_len, 'big')
            
            if msg_length > MAX_JSON_SIZE:
                console.print_system_message(f'Получено сообщение слишком большого размера: {msg_length}', 'warning')
                return None
            
            # Чтение данных
            data = b''
            while len(data) < msg_length:
                chunk = sock.recv(min(JSON_BUFFER_SIZE, msg_length - len(data)))
                if not chunk:
                    break
                data += chunk
            
            if len(data) < msg_length:
                return None
            
            return json.loads(data.decode('utf-8'))
        except socket.timeout:
            return None
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            return None
        except json.JSONDecodeError as e:
            console.print_system_message(f'Ошибка декодирования JSON: {e}', 'warning')
            return None
        except Exception:
            return None
    
    def _command_listener(self):
        """Фоновый поток для приёма всех входящих сообщений"""
        console.print_system_message(f'Прослушивание запущено для {self.username}', 'info')
        
        while self.connected and self.control_socket and not self._shutdown_event.is_set():
            try:
                with self._socket_lock:
                    if not self.connected or not self.control_socket:
                        break
                    message = self.receive_json(self.control_socket, 0.5)
                
                if not message:
                    continue
                
                action = message.get('action')
                
                # Проверяем, ждет ли кто-то синхронный ответ
                if self._response_event.is_set():
                    # Это ответ на ожидаемую команду
                    self._pending_response = message
                    self._response_event.clear()
                elif action == MessageActions.UPLOAD_REQUEST:
                    # Асинхронный запрос на отправку - обрабатываем в колбэке
                    if self.on_upload_request:
                        # Запускаем в отдельном потоке через колбэк
                        self.on_upload_request(message)
                    else:
                        console.print_system_message(
                            f'[{self.username}] Получен запрос отправки, но обработчик не назначен',
                            'warning'
                        )
                elif action == MessageActions.PING:
                    # Игнорируем пинги в логе (они приходят как ответы на наши пинги)
                    pass
                else:
                    console.print_system_message(
                        f'[{self.username}] Получено асинхронное действие: {action}',
                        'info'
                    )
            
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                if self.connected:
                    console.print_system_message(
                        f'[{self.username}] Соединение разорвано: {e}',
                        'error'
                    )
                    self.connected = False
                break
            except Exception as e:
                if self.connected:
                    console.print_system_message(
                        f'[{self.username}] Ошибка прослушивания: {e}',
                        'error'
                    )
                break
        
        console.print_system_message(f'Прослушивание остановлено для {self.username}', 'info')
    
    def send_ping(self, share_ids):
        """
        Отправка пинга для поддержания активности
        
        Аргументы:
            share_ids: список ID раздач
        """
        if not self.connected or not self.control_socket:
            return
        
        try:
            with self._socket_lock:
                self.send_json(self.control_socket, {
                    'action': MessageActions.PING,
                    'share_ids': share_ids
                })
        except Exception:
            pass
    
    def send_command(self, command_data, timeout=10):
        """
        Отправка команды и получение ответа
        
        Аргументы:
            command_data: данные команды
            timeout: таймаут ожидания ответа
            
        Возвращает:
            ответ сервера или None
        """
        if not self.connected or not self.control_socket:
            console.print_system_message('Нет подключения к серверу', 'warning')
            return None
        
        try:
            # Сбрасываем предыдущие ожидания
            self._pending_response = None
            # Устанавливаем флаг ожидания ответа
            self._response_event.set()
            
            with self._socket_lock:
                self.send_json(self.control_socket, command_data)
            
            # Ждем ответ
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self._response_event.is_set() and self._pending_response is not None:
                    response = self._pending_response
                    self._pending_response = None
                    return response
                time.sleep(0.05)
            
            # Таймаут
            self._response_event.clear()
            self._pending_response = None
            console.print_system_message(
                f'Таймаут ожидания ответа на команду {command_data.get("action")}',
                'warning'
            )
            return None
            
        except Exception as e:
            console.print_system_message(f'Ошибка отправки команды: {e}', 'error')
            self._response_event.clear()
            self._pending_response = None
            return None
    
    def create_data_connection(self, transfer_id, role):
        """
        Создание подключения к каналу данных
        
        Аргументы:
            transfer_id: ID трансфера
            role: роль (отправитель/получатель)
            
        Возвращает:
            сокет данных или None
        """
        try:
            data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_socket.settimeout(10)
            data_socket.connect((self.server_host, self.data_port))
            
            # Отправка заголовка
            header = transfer_id.encode('utf-8').ljust(32) + role
            data_socket.sendall(header)
            
            console.print_system_message('Подключено к каналу данных', 'info')
            return data_socket
        
        except socket.timeout:
            console.print_system_message('Таймаут подключения к каналу данных', 'error')
            return None
        except ConnectionRefusedError:
            console.print_system_message('Сервер данных недоступен', 'error')
            return None
        except Exception as e:
            console.print_system_message(f'Ошибка подключения к каналу данных: {e}', 'error')
            return None
    
    def get_active_transfers_count(self):
        """
        Получение количества активных передач (для мониторинга)
        
        Возвращает:
            количество активных передач
        """
        # Эта информация доступна в UploadManager
        return 0  # Будет переопределено при необходимости