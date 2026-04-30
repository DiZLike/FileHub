import socket
import json
import threading
import time
from network.protocol import MessageActions, MAX_JSON_SIZE, JSON_BUFFER_SIZE
from ui.console import console

class ConnectionManager:
    """Менеджер сетевых подключений"""
    
    def __init__(self, config):
        conn_config = config.connection
        self.server_host = conn_config.server_host
        self.server_port = conn_config.server_port
        self.data_port = conn_config.data_port
        self.connection_timeout = conn_config.connection_timeout
        
        self.control_socket = None
        self.connected = False
        self.username = None
        self.password = None
        self.require_password = False
        self.last_response = None
        
        self._socket_lock = threading.Lock()
        self._pending_response = None
        self._response_event = threading.Event()
        self._listener_thread = None
        self._shutdown_event = threading.Event()
        
        self._encryption = None
        
        self.on_upload_request = None
        self.on_disconnect = None
    
    def set_encryption(self, encryption):
        """Установка объекта шифрования"""
        self._encryption = encryption
    
    def connect(self, username: str, password: str) -> bool:
        """Подключение к серверу"""
        if self.connected:
            self.disconnect()
        
        self.username = username
        self.password = password
        self._shutdown_event.clear()
        
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(self.connection_timeout)
            self.control_socket.connect((self.server_host, self.server_port))
            
            # Этап 1: Отправляем HELLO
            hello_data = {
                'action': MessageActions.HELLO,
                'client_version': '1.0'
            }
            
            self._send_json(self.control_socket, hello_data)
            hello_response = self._receive_json(self.control_socket, 10)
            
            if not hello_response or hello_response.get('status') != 'ok':
                error_msg = hello_response.get('message', 'Сервер не ответил на приветствие') if hello_response else 'Нет ответа'
                console.print_system_message(f'Ошибка: {error_msg}', 'error')
                self._close_socket(self.control_socket)
                self.control_socket = None
                return False
            
            # Этап 2: TLS handshake если требуется
            encryption_params = hello_response.get('encryption')
            if encryption_params and encryption_params.get('enabled'):
                if not self._encryption:
                    self._encryption = ClientEncryption()
                
                self._encryption.enable(encryption_params)
                
                ssl_socket = self._encryption.wrap_socket(self.control_socket)
                if ssl_socket is None:
                    console.print_system_message('Ошибка установки TLS соединения', 'error')
                    self._close_socket(self.control_socket)
                    self.control_socket = None
                    return False
                
                self.control_socket = ssl_socket
                console.print_system_message(f'TLS соединение установлено ({encryption_params["algorithm"]})', 'info')
            
            # Этап 3: Аутентификация
            login_data = {
                'action': MessageActions.LOGIN,
                'username': username,
                'password': password
            }
            
            self._send_json(self.control_socket, login_data)
            response = self._receive_json(self.control_socket, 10)
            
            self.last_response = response
            
            if not response or response.get('status') != 'ok':
                error_msg = response.get('message', 'Неизвестная ошибка') if response else 'Нет ответа'
                console.print_system_message(f'Ошибка: {error_msg}', 'error')
                self._close_socket(self.control_socket)
                self.control_socket = None
                return False
            
            self.require_password = response.get('require_password', False)
            console.print_system_message(f'{response["message"]}', 'success')
            
            self.connected = True
            
            self._listener_thread = threading.Thread(
                target=self._command_listener,
                daemon=True,
                name="CommandListener"
            )
            self._listener_thread.start()
            
            return True
        
        except socket.timeout:
            console.print_system_message('Таймаут подключения к серверу', 'error')
            self._close_socket(self.control_socket)
            self.control_socket = None
            return False
        except ConnectionRefusedError:
            console.print_system_message('Сервер недоступен (отказ в подключении)', 'error')
            self._close_socket(self.control_socket)
            self.control_socket = None
            return False
        except Exception as e:
            console.print_system_message(f'Ошибка подключения: {e}', 'error')
            self._close_socket(self.control_socket)
            self.control_socket = None
            return False
    
    def disconnect(self):
        """Отключение от сервера"""
        was_connected = self.connected
        self.connected = False
        self._shutdown_event.set()
        
        if self.control_socket:
            try:
                self._send_json(self.control_socket, {'action': MessageActions.LOGOUT})
            except Exception:
                pass
            self._close_socket(self.control_socket)
            self.control_socket = None
        
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2)
        
        self._listener_thread = None
        self.last_response = None
        
        if was_connected:
            console.print_system_message('Отключено', 'info')
        
        if self.on_disconnect:
            self.on_disconnect()
    
    def send_command(self, command_data: dict, timeout: int = 10) -> dict:
        """Отправка команды и получение ответа"""
        if not self.connected or not self.control_socket:
            console.print_system_message('Нет подключения к серверу', 'warning')
            return None
        
        try:
            self._pending_response = None
            self._response_event.set()
            
            with self._socket_lock:
                self._send_json(self.control_socket, command_data)
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self._response_event.is_set() and self._pending_response is not None:
                    response = self._pending_response
                    self._pending_response = None
                    return response
                time.sleep(0.05)
            
            self._response_event.clear()
            self._pending_response = None
            console.print_system_message(f'Таймаут ожидания ответа на команду {command_data.get("action")}', 'warning')
            return None
            
        except Exception as e:
            console.print_system_message(f'Ошибка отправки команды: {e}', 'error')
            self._response_event.clear()
            self._pending_response = None
            return None
    
    def send_ping(self, share_ids: list):
        """Отправка пинга для поддержания активности"""
        if not self.connected or not self.control_socket:
            return
        
        try:
            with self._socket_lock:
                self._send_json(self.control_socket, {
                    'action': MessageActions.PING,
                    'share_ids': share_ids
                })
        except Exception:
            pass
    
    def create_data_connection(self, transfer_id: str, role: bytes):
        """Создание подключения к каналу данных"""
        try:
            data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_socket.settimeout(10)
            data_socket.connect((self.server_host, self.data_port))
            
            if self._encryption and self._encryption.is_enabled():
                ssl_socket = self._encryption.wrap_socket(data_socket)
                if ssl_socket is None:
                    console.print_system_message('Ошибка TLS для канала данных', 'error')
                    data_socket.close()
                    return None
                data_socket = ssl_socket
                console.print_system_message('TLS канал данных установлен', 'info')
            
            header = transfer_id.encode('utf-8').ljust(32) + role
            data_socket.sendall(header)
            
            #console.print_system_message('Подключено к каналу данных', 'info')
            return data_socket
        
        except Exception as e:
            console.print_system_message(f'Ошибка подключения к каналу данных: {e}', 'error')
            return None
    
    def _command_listener(self):
        """Фоновый поток для приёма входящих сообщений"""
        console.print_system_message(f'Прослушивание запущено для {self.username}', 'info')
        
        while self.connected and self.control_socket and not self._shutdown_event.is_set():
            try:
                with self._socket_lock:
                    if not self.connected or not self.control_socket:
                        break
                    message = self._receive_json(self.control_socket, 0.5)
                
                if not message:
                    continue
                
                action = message.get('action')
                
                if self._response_event.is_set():
                    self._pending_response = message
                    self._response_event.clear()
                elif action == MessageActions.UPLOAD_REQUEST:
                    if self.on_upload_request:
                        self.on_upload_request(message)
                    else:
                        console.print_system_message(
                            f'[{self.username}] Получен запрос отправки, но обработчик не назначен',
                            'warning'
                        )
            
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                if self.connected:
                    console.print_system_message(f'[{self.username}] Соединение разорвано: {e}', 'error')
                    self.connected = False
                break
            except Exception as e:
                if self.connected:
                    console.print_system_message(f'[{self.username}] Ошибка прослушивания: {e}', 'error')
                break
        
        console.print_system_message(f'Прослушивание остановлено для {self.username}', 'info')
    
    def _send_json(self, sock, data: dict):
        """Отправка JSON-сообщения"""
        if not sock:
            return
        
        try:
            json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            sock.sendall(len(json_data).to_bytes(4, 'big') + json_data)
        except Exception:
            pass
    
    def _receive_json(self, sock, timeout_sec: int) -> dict:
        """Получение JSON-сообщения"""
        if not sock:
            return None
        
        try:
            sock.settimeout(timeout_sec)
            
            raw_len = self._recv_exactly(sock, 4)
            if not raw_len:
                return None
            
            msg_length = int.from_bytes(raw_len, 'big')
            if msg_length > MAX_JSON_SIZE:
                console.print_system_message(f'Получено сообщение слишком большого размера: {msg_length}', 'warning')
                return None
            
            data = self._recv_exactly(sock, msg_length)
            if not data or len(data) < msg_length:
                return None
            
            return json.loads(data.decode('utf-8'))
        except (socket.timeout, json.JSONDecodeError):
            return None
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            return None
        except Exception:
            return None
    
    def _recv_exactly(self, sock, size: int) -> bytes:
        """Чтение точного количества байт"""
        data = b''
        while len(data) < size:
            chunk = sock.recv(min(JSON_BUFFER_SIZE, size - len(data)))
            if not chunk:
                break
            data += chunk
        return data if len(data) >= size else None
    
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


from network.encryption import ClientEncryption