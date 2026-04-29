"""
Сетевое взаимодействие
"""

import json
import socket
import threading
import uuid
from protocols import TransferRoles

class NetworkManager:
    """Менеджер сетевого взаимодействия"""
    
    def __init__(self, config, logger):
        """
        Инициализация сетевого менеджера
        
        Аргументы:
            config: конфигурация сервера
            logger: система логирования
        """
        self.buffer_size = config.network_config['buffer_size']
        self.max_json_size = config.network_config['max_json_size']
        self.logger = logger
        
        self.pending_transfers = {}
        self.transfer_lock = threading.RLock()
    
    def receive_json(self, client_socket):
        """
        Получение JSON-сообщения
        
        Аргументы:
            client_socket: сокет клиента
            
        Возвращает:
            распарсенный JSON или None
        """
        try:
            # Чтение длины сообщения
            raw_len = b''
            while len(raw_len) < 4:
                chunk = client_socket.recv(4 - len(raw_len))
                if not chunk:
                    return None
                raw_len += chunk
            
            msg_length = int.from_bytes(raw_len, 'big')
            
            if msg_length > self.max_json_size:
                self.logger.log('WARNING', f'Слишком большой JSON: {msg_length} байт')
                return None
            
            # Чтение данных
            data = b''
            while len(data) < msg_length:
                chunk = client_socket.recv(min(self.buffer_size, msg_length - len(data)))
                if not chunk:
                    break
                data += chunk
            
            if len(data) < msg_length:
                return None
            
            return json.loads(data.decode('utf-8'))
        except socket.timeout:
            return None
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка получения JSON: {e}')
            return None
    
    def send_json(self, client_socket, data):
        """
        Отправка JSON-сообщения
        
        Аргументы:
            client_socket: сокет клиента
            data: данные для отправки
        """
        try:
            json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            if len(json_data) > self.max_json_size:
                self.logger.log('WARNING', f'Слишком большой JSON ответ: {len(json_data)} байт')
                return
            
            # Отправка длины и данных
            client_socket.sendall(len(json_data).to_bytes(4, 'big') + json_data)
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка отправки JSON: {e}')
    
    def create_transfer(self, share_info, requester):
        """
        Создание транфера данных
        
        Аргументы:
            share_info: информация о раздаче
            requester: запрашивающий пользователь
            
        Возвращает:
            ID трансфера
        """
        transfer_id = uuid.uuid4().hex
        
        with self.transfer_lock:
            self.pending_transfers[transfer_id] = {
                'share_info': share_info,
                'requester': requester,
                'created_at': __import__('time').time()
            }
        
        return transfer_id
    
    def handle_data_connection(self, data_socket, address):
        """
        Обработка подключения к каналу данных
        
        Аргументы:
            data_socket: сокет данных
            address: адрес подключения
        """
        try:
            # Чтение заголовка
            header = b''
            while len(header) < 33:
                chunk = data_socket.recv(33 - len(header))
                if not chunk:
                    data_socket.close()
                    return
                header += chunk
            
            if len(header) < 33:
                data_socket.close()
                return
            
            transfer_id = header[:32].decode('utf-8').strip()
            role = header[32:33]
            
            with self.transfer_lock:
                if transfer_id not in self.pending_transfers:
                    self.pending_transfers[transfer_id] = {}
                
                if role == TransferRoles.SENDER:
                    self.pending_transfers[transfer_id]['sender'] = data_socket
                elif role == TransferRoles.RECEIVER:
                    self.pending_transfers[transfer_id]['receiver'] = data_socket
                
                transfer = self.pending_transfers[transfer_id]
                
                # Если оба участника подключены, начинаем проксирование
                if 'sender' in transfer and 'receiver' in transfer:
                    sender = transfer['sender']
                    receiver = transfer['receiver']
                    del self.pending_transfers[transfer_id]
                    
                    threading.Thread(
                        target=self._proxy_transfer,
                        args=(sender, receiver, transfer_id),
                        daemon=True
                    ).start()
        
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка при приеме данных: {e}')
            try:
                data_socket.close()
            except Exception:
                pass
    
    def _proxy_transfer(self, sender_socket, receiver_socket, transfer_id):
        """
        Проксирование передачи данных
        
        Аргументы:
            sender_socket: сокет отправителя
            receiver_socket: сокет получателя
            transfer_id: ID трансфера
        """
        self.logger.log('DEBUG', f'Проксирование трансфера {transfer_id}')
        total_bytes = 0
        
        try:
            sender_socket.settimeout(60)
            receiver_socket.settimeout(60)
            
            while True:
                try:
                    data = sender_socket.recv(self.buffer_size)
                    if not data:
                        break
                    receiver_socket.sendall(data)
                    total_bytes += len(data)
                except socket.timeout:
                    break
                except Exception as e:
                    self.logger.log('ERROR', f'Ошибка при передаче данных: {e}')
                    break
        
        except Exception as e:
            self.logger.log('ERROR', f'Ошибка проксирования: {e}')
        finally:
            self.logger.update_stat('total_bytes_transferred', total_bytes)
            
            from utils import Utils
            self.logger.log('DEBUG', 
                f'Трансфер {transfer_id} завершен: {Utils.format_bytes(total_bytes)}')
            
            # Закрываем сокеты
            for sock in [sender_socket, receiver_socket]:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    sock.close()
                except:
                    pass
    
    def cleanup_transfers(self):
        """
        Очистка зависших трансферов
        
        Возвращает:
            количество удаленных трансферов
        """
        current_time = __import__('time').time()
        to_remove = []
        
        with self.transfer_lock:
            for transfer_id, transfer in self.pending_transfers.items():
                if current_time - transfer.get('created_at', 0) > 300:
                    to_remove.append(transfer_id)
            
            for transfer_id in to_remove:
                if transfer_id in self.pending_transfers:
                    del self.pending_transfers[transfer_id]
        
        return len(to_remove)