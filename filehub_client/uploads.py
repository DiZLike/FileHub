"""
Отправка файлов на сервер
"""

import os
import sys
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from protocols import ShareTypes
from utils import Utils
from console_ui import console


class UploadManager:
    """Менеджер отправки файлов"""
    
    # Максимальное количество одновременных передач
    MAX_CONCURRENT_UPLOADS = 3
    
    def __init__(self, connection, local_shares, config):
        """
        Инициализация менеджера отправки
        
        Аргументы:
            connection: менеджер подключений
            local_shares: словарь локальных раздач
            config: конфигурация клиента
        """
        self.connection = connection
        self.local_shares = local_shares  # Ссылка на словарь из ShareManager
        self.show_progress = config.interface_config['show_progress']
        self.encryption = None
        
        # Потокобезопасное хранение информации о шифровании
        self._encryption_info = {}  # transfer_id -> encryption_info
        self._encryption_info_lock = threading.Lock()
        
        # Пул потоков для ограничения одновременных передач
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_CONCURRENT_UPLOADS,
            thread_name_prefix="Upload"
        )
        
        # Отслеживание активных передач
        self._active_futures = {}  # transfer_id -> Future
        self._futures_lock = threading.Lock()
    
    def set_encryption(self, encryption):
        """
        Установка объекта шифрования
        
        Аргументы:
            encryption: объект ClientEncryption
        """
        self.encryption = encryption
    
    def handle_upload_request(self, request):
        """
        Обработка запроса на отправку файла
        (вызывается в отдельном потоке из client.py)
        
        Аргументы:
            request: данные запроса
        """
        requester = request.get('requester')
        filename = request.get('filename')
        transfer_id = request.get('transfer_id')
        share_id = request.get('share_id')
        share_type = request.get('type')
        short_id = transfer_id[:8] if transfer_id else 'unknown'
        
        console.print_system_message(
            f'Запрос от {requester}: {filename} [{short_id}]',
            'info'
        )
        
        # Сохраняем информацию о шифровании для этого трансфера
        encryption_info = request.get('encryption')
        if encryption_info and encryption_info.get('enabled'):
            with self._encryption_info_lock:
                self._encryption_info[transfer_id] = encryption_info
        
        # Проверяем наличие раздачи в локальном кэше
        local_shares_copy = dict(self.local_shares)
        
        if share_id not in local_shares_copy:
            console.print_system_message(
                f'[{short_id}] Раздача {share_id} не найдена локально',
                'error'
            )
            return
        
        share_info = local_shares_copy[share_id]
        local_path = share_info.get('local_path')
        
        if not local_path or not os.path.exists(local_path):
            console.print_system_message(
                f'[{short_id}] Путь не найден: {local_path}',
                'error'
            )
            return
        
        # Запускаем отправку через пул потоков
        try:
            if share_type == ShareTypes.FILE:
                future = self._executor.submit(
                    self.send_file, transfer_id, share_id, local_path
                )
            else:
                future = self._executor.submit(
                    self.send_folder, transfer_id, share_id, local_path, 
                    request.get('files', [])
                )
            
            # Сохраняем Future для отслеживания
            with self._futures_lock:
                self._active_futures[transfer_id] = future
            
            # Добавляем колбэк для очистки после завершения
            future.add_done_callback(
                lambda f, tid=transfer_id: self._on_transfer_complete(tid, f)
            )
            
        except Exception as e:
            console.print_system_message(
                f'[{short_id}] Ошибка запуска: {e}',
                'error'
            )
    
    def _on_transfer_complete(self, transfer_id, future):
        """
        Колбэк при завершении передачи
        
        Аргументы:
            transfer_id: ID трансфера
            future: объект Future
        """
        with self._futures_lock:
            if transfer_id in self._active_futures:
                del self._active_futures[transfer_id]
        
        # Очищаем информацию о шифровании
        with self._encryption_info_lock:
            if transfer_id in self._encryption_info:
                del self._encryption_info[transfer_id]
        
        # Проверяем на ошибки
        try:
            future.result(timeout=0)
        except Exception as e:
            short_id = transfer_id[:8]
            console.print_system_message(
                f'[{short_id}] Завершено с ошибкой: {e}',
                'warning'
            )
    
    def wait_for_all_transfers(self, timeout=None):
        """
        Ожидание завершения всех активных передач
        
        Аргументы:
            timeout: максимальное время ожидания в секундах
        """
        with self._futures_lock:
            futures = list(self._active_futures.values())
        
        if not futures:
            return
        
        console.print_system_message(
            f'Ожидание завершения {len(futures)} передач...',
            'info'
        )
        
        for future in futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                pass
    
    def get_active_transfers_count(self):
        """
        Получение количества активных передач
        
        Возвращает:
            количество активных передач
        """
        with self._futures_lock:
            return len(self._active_futures)
    
    def get_encryption_info(self, transfer_id):
        """
        Потокобезопасное получение информации о шифровании
        
        Аргументы:
            transfer_id: ID трансфера
            
        Возвращает:
            словарь с информацией о шифровании или {}
        """
        with self._encryption_info_lock:
            return self._encryption_info.get(transfer_id, {})
    
    def send_file(self, transfer_id, share_id, local_path):
        """
        Отправка одного файла с поддержкой шифрования
        
        Аргументы:
            transfer_id: ID трансфера
            share_id: ID раздачи
            local_path: локальный путь к файлу
        """
        short_id = transfer_id[:8]
        
        if not os.path.exists(local_path):
            console.print_system_message(
                f'[{short_id}] Файл не найден: {local_path}',
                'error'
            )
            return
        
        data_socket = self.connection.create_data_connection(transfer_id, b'S')
        if not data_socket:
            console.print_system_message(
                f'[{short_id}] Не удалось подключиться к каналу данных',
                'error'
            )
            return
        
        try:
            time.sleep(0.5)
            data_socket.settimeout(60)
            
            # Получаем параметры шифрования
            encryption_info = self.get_encryption_info(transfer_id)
            use_encryption = (
                encryption_info.get('enabled', False) and 
                self.encryption and 
                self.encryption.is_enabled()
            )
            session_key = encryption_info.get('session_key') if use_encryption else None
            
            file_size = os.path.getsize(local_path)
            filename = os.path.basename(local_path)
            
            console.print_system_message(
                f'[{short_id}] Отправка: {filename} ({Utils.format_size(file_size)})',
                'info'
            )
            
            sent = 0
            last_progress_update = 0
            
            with open(local_path, 'rb') as f:
                while sent < file_size:
                    chunk_size = min(65536, file_size - sent)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    data_to_send = chunk
                    
                    # Шифруем если нужно
                    if use_encryption and session_key:
                        encrypted_chunk = self.encryption.encrypt_file_data(chunk, session_key)
                        if encrypted_chunk is None:
                            console.print_system_message(
                                f'[{short_id}] Ошибка шифрования',
                                'error'
                            )
                            break
                        data_to_send = encrypted_chunk
                    
                    try:
                        data_socket.sendall(data_to_send)
                        sent += len(chunk)
                        
                        # Обновляем прогресс
                        if self.show_progress and (
                            sent - last_progress_update > 102400 or 
                            sent == file_size
                        ):
                            console.update_multi_progress(
                                short_id,
                                sent,
                                file_size,
                                prefix=f'[T{short_id}]',
                                suffix=f'{Utils.format_size(sent)}/{Utils.format_size(file_size)}'
                            )
                            last_progress_update = sent
                            
                    except socket.timeout:
                        console.print_system_message(
                            f'[{short_id}] Таймаут отправки',
                            'error'
                        )
                        break
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        console.print_system_message(
                            f'[{short_id}] Соединение разорвано',
                            'error'
                        )
                        break
            
            # Завершаем прогресс-бар
            console.update_multi_progress(
                short_id, sent, file_size,
                prefix=f'[T{short_id}]',
                suffix=f'{Utils.format_size(sent)}/{Utils.format_size(file_size)}',
                finished=True
            )
            
            # Финальный статус
            if sent == file_size:
                console.print_system_message(
                    f'[✓] {short_id}: {filename} отправлен ({Utils.format_size(sent)})',
                    'success'
                )
            else:
                console.print_system_message(
                    f'[⚠] {short_id}: {filename} частично ({Utils.format_size(sent)} из {Utils.format_size(file_size)})',
                    'warning'
                )
        
        except Exception as e:
            console.update_multi_progress(short_id, 0, 0, finished=True)
            console.print_system_message(
                f'[{short_id}] Ошибка: {e}',
                'error'
            )
        finally:
            try:
                data_socket.shutdown(socket.SHUT_WR)
            except:
                pass
            data_socket.close()
    
    def send_folder(self, transfer_id, share_id, local_path, files):
        """
        Отправка папки с поддержкой шифрования и параллельных отправок
        Минимальный вывод: только общий прогресс
        
        Аргументы:
            transfer_id: ID трансфера
            share_id: ID раздачи
            local_path: локальный путь к папке
            files: список файлов
        """
        short_id = transfer_id[:8]
        
        if not os.path.exists(local_path):
            console.print_system_message(
                f'[{short_id}] Папка не найдена: {local_path}',
                'error'
            )
            return
        
        data_socket = self.connection.create_data_connection(transfer_id, b'S')
        if not data_socket:
            console.print_system_message(
                f'[{short_id}] Не удалось подключиться к каналу данных',
                'error'
            )
            return
        
        try:
            time.sleep(0.5)
            data_socket.settimeout(60)
            
            # Получаем параметры шифрования
            encryption_info = self.get_encryption_info(transfer_id)
            use_encryption = (
                encryption_info.get('enabled', False) and 
                self.encryption and 
                self.encryption.is_enabled()
            )
            session_key = encryption_info.get('session_key') if use_encryption else None
            
            total_files = len(files)
            total_size = sum(f.get('size', 0) for f in files)
            
            # Одна строка с общей информацией
            console.print_system_message(
                f'[{short_id}] Отправка: {os.path.basename(local_path)} | '
                f'{total_files} файлов | {Utils.format_size(total_size)}',
                'info'
            )
            
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
                
                # Каждый поток открывает свой независимый дескриптор файла
                try:
                    with open(full_path, 'rb') as f:
                        while file_sent < file_size:
                            chunk_size = min(65536, file_size - file_sent)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            
                            data_to_send = chunk
                            
                            # Шифруем если нужно
                            if use_encryption and session_key:
                                encrypted_chunk = self.encryption.encrypt_file_data(
                                    chunk, session_key
                                )
                                if encrypted_chunk is None:
                                    break
                                data_to_send = encrypted_chunk
                            
                            try:
                                data_socket.sendall(data_to_send)
                                file_sent += len(chunk)
                                total_sent_bytes += len(chunk)
                                
                                # Обновляем общий прогресс
                                if self.show_progress and (
                                    total_sent_bytes - last_progress_update > 102400 or 
                                    total_sent_bytes == total_size
                                ):
                                    console.update_multi_progress(
                                        short_id,
                                        total_sent_bytes,
                                        total_size,
                                        prefix=f'[T{short_id}]',
                                        suffix=f'{Utils.format_size(total_sent_bytes)}/{Utils.format_size(total_size)}'
                                    )
                                    last_progress_update = total_sent_bytes
                                    
                            except socket.timeout:
                                break
                            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                                break
                    
                    if file_sent == file_size:
                        files_sent += 1
                        
                except Exception:
                    pass
            
            # Завершаем прогресс-бар
            console.update_multi_progress(
                short_id, total_sent_bytes, total_size,
                prefix=f'[T{short_id}]',
                suffix=f'{Utils.format_size(total_sent_bytes)}/{Utils.format_size(total_size)}',
                finished=True
            )
            
            # Финальный статус одной строкой
            if total_sent_bytes == total_size:
                console.print_system_message(
                    f'[✓] {short_id}: {files_sent}/{total_files} файлов, '
                    f'{Utils.format_size(total_sent_bytes)}',
                    'success'
                )
            else:
                console.print_system_message(
                    f'[⚠] {short_id}: {files_sent}/{total_files} файлов, '
                    f'{Utils.format_size(total_sent_bytes)} из {Utils.format_size(total_size)}',
                    'warning'
                )
        
        except Exception as e:
            console.update_multi_progress(short_id, 0, 0, finished=True)
            console.print_system_message(
                f'[{short_id}] Ошибка: {e}',
                'error'
            )
        finally:
            try:
                data_socket.shutdown(socket.SHUT_WR)
            except:
                pass
            data_socket.close()