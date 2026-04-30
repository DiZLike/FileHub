import json
import socket
import threading
import uuid
import time
from typing import Optional, Dict

class NetworkManager:
    """Менеджер сетевого взаимодействия"""
    
    HEADER_SIZE = 4
    TRANSFER_HEADER_SIZE = 33
    
    def __init__(self, config, logger):
        self._buffer_size = config.network.buffer_size
        self._max_json_size = config.network.max_json_size
        self._logger = logger
        
        self._pending_transfers: Dict[str, dict] = {}
        self._transfer_lock = threading.RLock()
    
    def receive_json(self, client_socket) -> Optional[dict]:
        """Получение JSON-сообщения"""
        try:
            raw_len = self._recv_exactly(client_socket, self.HEADER_SIZE)
            if not raw_len:
                return None
            
            msg_length = int.from_bytes(raw_len, 'big')
            if msg_length > self._max_json_size:
                self._logger.log('WARNING', f'Слишком большой JSON: {msg_length} байт')
                return None
            
            data = self._recv_exactly(client_socket, msg_length)
            if not data or len(data) < msg_length:
                return None
            
            return json.loads(data.decode('utf-8'))
        except (socket.timeout, json.JSONDecodeError):
            return None
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка получения JSON: {e}')
            return None
    
    def send_json(self, client_socket, data: dict):
        """Отправка JSON-сообщения"""
        try:
            json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            if len(json_data) > self._max_json_size:
                self._logger.log('WARNING', f'Слишком большой JSON ответ: {len(json_data)} байт')
                return
            
            client_socket.sendall(len(json_data).to_bytes(4, 'big') + json_data)
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка отправки JSON: {e}')
    
    def create_transfer(self, share_info: dict, requester: str) -> str:
        """Создание трансфера данных"""
        transfer_id = uuid.uuid4().hex
        
        with self._transfer_lock:
            self._pending_transfers[transfer_id] = {
                'share_info': share_info,
                'requester': requester,
                'created_at': time.time()
            }
        
        return transfer_id
    
    def handle_data_connection(self, data_socket, address):
        """Обработка подключения к каналу данных"""
        try:
            header = self._recv_exactly(data_socket, self.TRANSFER_HEADER_SIZE)
            if not header:
                data_socket.close()
                return
            
            transfer_id = header[:32].decode('utf-8').strip()
            role = header[32:33]
            
            with self._transfer_lock:
                self._pending_transfers.setdefault(transfer_id, {})
                key = 'sender' if role == b'S' else 'receiver'
                self._pending_transfers[transfer_id][key] = data_socket
                
                transfer = self._pending_transfers[transfer_id]
                if 'sender' in transfer and 'receiver' in transfer:
                    sender = transfer.pop('sender')
                    receiver = transfer.pop('receiver')
                    del self._pending_transfers[transfer_id]
                    
                    threading.Thread(
                        target=self._proxy_transfer,
                        args=(sender, receiver, transfer_id),
                        daemon=True
                    ).start()
        
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка при приёме данных: {e}')
            try:
                data_socket.close()
            except Exception:
                pass
    
    def _proxy_transfer(self, sender, receiver, transfer_id: str):
        """Проксирование передачи данных"""
        self._logger.log('DEBUG', f'Проксирование трансфера {transfer_id}')
        total_bytes = 0
        
        try:
            sender.settimeout(60)
            receiver.settimeout(60)
            
            # Этап 1: Передаем данные от отправителя к получателю
            while True:
                try:
                    data = sender.recv(self._buffer_size)
                    if not data:
                        self._logger.log('DEBUG', f'Трансфер {transfer_id}: отправитель закрыл соединение')
                        break
                    receiver.sendall(data)
                    total_bytes += len(data)
                except socket.timeout:
                    self._logger.log('DEBUG', f'Трансфер {transfer_id}: таймаут при чтении от отправителя')
                    break
                except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                    self._logger.log('DEBUG', f'Трансфер {transfer_id}: соединение с отправителем разорвано: {e}')
                    break
                except Exception as e:
                    self._logger.log('ERROR', f'Трансфер {transfer_id}: ошибка при передаче данных: {e}')
                    break
            
            self._logger.log('DEBUG', f'Трансфер {transfer_id}: передано {total_bytes} байт от отправителя')
            
            # Этап 2: Закрываем отправляющую сторону
            # Используем SHUT_WR чтобы отправитель знал что мы закончили читать
            try:
                sender.shutdown(socket.SHUT_RD)
            except Exception:
                pass
            
            # Этап 3: Уведомляем получателя что передача завершена
            # и ждем пока он прочитает все данные
            try:
                receiver.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            
            # Этап 4: Ждем подтверждения от получателя что он все прочитал
            try:
                receiver.settimeout(10)
                ack = receiver.recv(1024)
                if ack:
                    self._logger.log('DEBUG', f'Трансфер {transfer_id}: получатель подтвердил получение ({len(ack)} байт)')
            except socket.timeout:
                self._logger.log('DEBUG', f'Трансфер {transfer_id}: таймаут ожидания подтверждения от получателя')
            except Exception as e:
                self._logger.log('DEBUG', f'Трансфер {transfer_id}: ошибка ожидания подтверждения: {e}')
            
        except Exception as e:
            self._logger.log('ERROR', f'Трансфер {transfer_id}: ошибка проксирования: {e}')
        finally:
            from utils.helpers import format_bytes
            self._logger.log('DEBUG', f'Трансфер {transfer_id} завершен: {format_bytes(total_bytes)}')
            self._logger.update_stat('total_bytes_transferred', total_bytes)
            
            # Закрываем оба сокета
            for sock in (sender, receiver):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass
    
    def cleanup_transfers(self) -> int:
        """Очистка зависших трансферов"""
        current_time = time.time()
        
        with self._transfer_lock:
            expired = [
                tid for tid, transfer in self._pending_transfers.items()
                if current_time - transfer.get('created_at', 0) > 300
            ]
            
            for tid in expired:
                if tid in self._pending_transfers:
                    del self._pending_transfers[tid]
        
        return len(expired)
    
    def _recv_exactly(self, sock, size: int) -> Optional[bytes]:
        """Чтение точного количества байт"""
        data = b''
        while len(data) < size:
            chunk = sock.recv(min(self._buffer_size, size - len(data)))
            if not chunk:
                break
            data += chunk
        return data if len(data) >= size else None