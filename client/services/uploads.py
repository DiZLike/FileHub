import os
import sys
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from network.protocol import ShareTypes
from utils.helpers import format_size

class UploadManager:
    """Менеджер отправки файлов"""
    
    MAX_CONCURRENT_UPLOADS = 3
    
    def __init__(self, connection, local_shares: dict, config):
        self.connection = connection
        self.local_shares = local_shares
        self.show_progress = config.interface.show_progress
        self.encryption = None
        
        self._encryption_info = {}
        self._encryption_info_lock = threading.Lock()
        
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_CONCURRENT_UPLOADS,
            thread_name_prefix="Upload"
        )
        
        self._active_futures = {}
        self._futures_lock = threading.Lock()
    
    def set_encryption(self, encryption):
        """Установка объекта шифрования"""
        self.encryption = encryption
    
    def handle_upload_request(self, request: dict):
        """Обработка запроса на отправку файла"""
        from ui.console import console
        
        requester = request.get('requester')
        filename = request.get('filename')
        transfer_id = request.get('transfer_id')
        share_id = request.get('share_id')
        share_type = request.get('type')
        short_id = transfer_id[:8] if transfer_id else 'unknown'
        
        #console.print_system_message(f'Запрос от {requester}: {filename} [{short_id}]', 'info')
        
        encryption_info = request.get('encryption')
        if encryption_info and encryption_info.get('enabled'):
            with self._encryption_info_lock:
                self._encryption_info[transfer_id] = encryption_info
        
        local_shares_copy = dict(self.local_shares)
        
        if share_id not in local_shares_copy:
            #console.print_system_message(f'[{short_id}] Раздача {share_id} не найдена локально', 'error')
            return
        
        share_info = local_shares_copy[share_id]
        local_path = share_info.get('local_path')
        
        if not local_path or not os.path.exists(local_path):
            #console.print_system_message(f'[{short_id}] Путь не найден: {local_path}', 'error')
            return
        
        try:
            if share_type == ShareTypes.FILE:
                future = self._executor.submit(
                    self._send_file, transfer_id, share_id, local_path
                )
            else:
                future = self._executor.submit(
                    self._send_folder, transfer_id, share_id, local_path,
                    request.get('files', [])
                )
            
            with self._futures_lock:
                self._active_futures[transfer_id] = future
            
            future.add_done_callback(
                lambda f, tid=transfer_id: self._on_transfer_complete(tid, f)
            )
            
        except Exception as e:
            #console.print_system_message(f'[{short_id}] Ошибка запуска: {e}', 'error')
            pass
    
    def _on_transfer_complete(self, transfer_id: str, future):
        """Колбэк при завершении передачи"""
        with self._futures_lock:
            self._active_futures.pop(transfer_id, None)
        
        with self._encryption_info_lock:
            self._encryption_info.pop(transfer_id, None)
        
        try:
            future.result(timeout=0)
        except Exception as e:
            short_id = transfer_id[:8]
            from ui.console import console
            #console.print_system_message(f'[{short_id}] Завершено с ошибкой: {e}', 'warning')
    
    def wait_for_all_transfers(self, timeout=None):
        """Ожидание завершения всех активных передач"""
        with self._futures_lock:
            futures = list(self._active_futures.values())
        
        if not futures:
            return
        
        for future in futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                pass
    
    def get_active_transfers_count(self) -> int:
        """Получение количества активных передач"""
        with self._futures_lock:
            return len(self._active_futures)
    
    def _send_file(self, transfer_id: str, share_id: str, local_path: str):
        """Отправка одного файла"""
        from ui.console import console
        
        short_id = transfer_id[:8]
        
        if not os.path.exists(local_path):
            #console.print_system_message(f'[{short_id}] Файл не найден: {local_path}', 'error')
            return
        
        data_socket = self.connection.create_data_connection(transfer_id, b'S')
        if not data_socket:
            #console.print_system_message(f'[{short_id}] Не удалось подключиться к каналу данных', 'error')
            return
        
        try:
            time.sleep(0.5)
            data_socket.settimeout(60)
            
            file_size = os.path.getsize(local_path)
            filename = os.path.basename(local_path)
            
            #console.print_system_message(f'[{short_id}] Отправка: {filename} ({format_size(file_size)})', 'info')
            
            sent = 0
            last_progress_update = 0
            
            with open(local_path, 'rb') as f:
                while sent < file_size:
                    chunk_size = min(65536, file_size - sent)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    try:
                        data_socket.sendall(chunk)
                        sent += len(chunk)
                        
                        if self.show_progress and (sent - last_progress_update > 102400 or sent == file_size):
                            console.update_multi_progress(
                                short_id, sent, file_size,
                                prefix=f'[T{short_id}]',
                                suffix=f'{format_size(sent)}/{format_size(file_size)}'
                            )
                            last_progress_update = sent
                            
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                        #console.print_system_message(f'[{short_id}] Соединение разорвано: {e}', 'warning')
                        break
                    except socket.timeout:
                        #console.print_system_message(f'[{short_id}] Таймаут отправки', 'warning')
                        break
            
            #console.update_multi_progress(
            #    short_id, sent, file_size,
            #    prefix=f'[T{short_id}]',
            #    suffix=f'{format_size(sent)}/{format_size(file_size)}',
            #    finished=True
            #)
            
            if sent == file_size:
                # Сигнализируем серверу что мы закончили отправку
                try:
                    data_socket.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                
                # Ждем подтверждения от сервера что данные доставлены
                try:
                    data_socket.settimeout(30)
                    ack = data_socket.recv(1024)
                    if ack == b'OK':
                        #console.print_system_message(
                        #    f'[✓] {short_id}: {filename} отправлен ({format_size(sent)})',
                        #    'success'
                        #)
                        pass
                    else:
                        #console.print_system_message(
                        #    f'[✓] {short_id}: {filename} отправлен ({format_size(sent)})',
                        #    'success'
                        #)
                        pass
                except socket.timeout:
                    #console.print_system_message(
                    #    f'[✓] {short_id}: {filename} отправлен ({format_size(sent)})',
                    #    'success'
                    #)
                    pass
                except Exception:
                    #console.print_system_message(
                    #    f'[✓] {short_id}: {filename} отправлен ({format_size(sent)})',
                    #    'success'
                    #)
                    pass
            else:
                #console.print_system_message(
                #    f'[⚠] {short_id}: {filename} частично ({format_size(sent)} из {format_size(file_size)})',
                #    'warning'
                #)
                pass
        
        except Exception as e:
            #console.update_multi_progress(short_id, 0, 0, finished=True)
            #console.print_system_message(f'[{short_id}] Ошибка: {e}', 'error')
            pass
        finally:
            try:
                data_socket.close()
            except Exception:
                pass

    def _send_folder(self, transfer_id: str, share_id: str, local_path: str, files: list):
        """Отправка папки"""
        from ui.console import console
        
        short_id = transfer_id[:8]
        
        if not os.path.exists(local_path):
            #console.print_system_message(f'[{short_id}] Папка не найдена: {local_path}', 'error')
            return
        
        data_socket = self.connection.create_data_connection(transfer_id, b'S')
        if not data_socket:
            #console.print_system_message(f'[{short_id}] Не удалось подключиться к каналу данных', 'error')
            return
        
        try:
            time.sleep(0.5)
            data_socket.settimeout(60)
            
            total_files = len(files)
            total_size = sum(f.get('size', 0) for f in files)
            
            #console.print_system_message(
            #    f'[{short_id}] Отправка: {os.path.basename(local_path)} | {total_files} файлов | {format_size(total_size)}',
            #    'info'
            #)
            
            total_sent_bytes = 0
            files_sent = 0
            last_progress_update = 0
            
            for i, file_info in enumerate(files, 1):
                file_path = file_info.get('path', '')
                full_path = os.path.join(local_path, file_path)
                
                if not os.path.exists(full_path):
                    continue
                
                file_size = file_info.get('size', 0)
                file_sent = 0
                
                try:
                    with open(full_path, 'rb') as f:
                        while file_sent < file_size:
                            chunk_size = min(65536, file_size - file_sent)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            
                            try:
                                data_socket.sendall(chunk)
                                file_sent += len(chunk)
                                total_sent_bytes += len(chunk)
                                
                                if self.show_progress and (total_sent_bytes - last_progress_update > 102400 or total_sent_bytes == total_size):
                                    #console.update_multi_progress(
                                    #    short_id, total_sent_bytes, total_size,
                                    #    prefix=f'[T{short_id}]',
                                    #    suffix=f'{format_size(total_sent_bytes)}/{format_size(total_size)}'
                                    #)
                                    last_progress_update = total_sent_bytes
                                    
                            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                                #console.print_system_message(f'[{short_id}] Соединение разорвано: {e}', 'warning')
                                raise  # Прерываем внешний цикл
                            except socket.timeout:
                                #console.print_system_message(f'[{short_id}] Таймаут отправки', 'warning')
                                raise  # Прерываем внешний цикл
                    
                    if file_sent == file_size:
                        files_sent += 1
                        
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout):
                    break
                except Exception:
                    pass
            
            #console.update_multi_progress(
            #    short_id, total_sent_bytes, total_size,
            #    prefix=f'[T{short_id}]',
            #    suffix=f'{format_size(total_sent_bytes)}/{format_size(total_size)}',
            #    finished=True
            #)
            
            if total_sent_bytes == total_size:
                # Сигнализируем серверу что мы закончили отправку
                try:
                    data_socket.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                
                # Ждем подтверждения от сервера
                try:
                    data_socket.settimeout(30)
                    ack = data_socket.recv(1024)
                except Exception:
                    pass
                
                #console.print_system_message(
                #    f'[✓] {short_id}: {files_sent}/{total_files} файлов, {format_size(total_sent_bytes)}',
                #    'success'
                #)
            else:
                #console.print_system_message(
                #    f'[⚠] {short_id}: {files_sent}/{total_files} файлов, {format_size(total_sent_bytes)} из {format_size(total_size)}',
                #    'warning'
                #)
                pass
        
        except Exception as e:
            #console.update_multi_progress(short_id, 0, 0, finished=True)
            #console.print_system_message(f'[{short_id}] Ошибка: {e}', 'error')
            pass
        finally:
            try:
                data_socket.close()
            except Exception:
                pass