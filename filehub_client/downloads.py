"""
Скачивание файлов с сервера
"""

import os
import sys
import socket
import struct
from protocols import ShareTypes, MessageActions
from utils import Utils
from console_ui import console

class DownloadManager:
    """Менеджер скачивания файлов"""
    
    def __init__(self, connection, config):
        """
        Инициализация менеджера скачиваний
        
        Аргументы:
            connection: менеджер подключений
            config: конфигурация клиента
        """
        self.connection = connection
        self.download_dir = config.downloads_config['download_dir']
        self.max_retries = config.downloads_config['max_retries']
        self.show_progress = config.interface_config['show_progress']
        self.encryption = None
        
        Utils.ensure_dir(self.download_dir)
    
    def set_encryption(self, encryption):
        """
        Установка объекта шифрования
        
        Аргументы:
            encryption: объект ClientEncryption
        """
        self.encryption = encryption
    
    def download(self, share_id):
        """
        Скачивание раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        console.print_system_message(f'Запрос скачивания раздачи {share_id}...', 'info')
        
        response = self.connection.send_command({
            'action': MessageActions.DOWNLOAD,
            'share_id': share_id
        }, timeout=30)
        
        if not response or response.get('status') != 'ok':
            error_msg = response.get('message', 'Неизвестная ошибка') if response else 'Нет ответа'
            console.print_system_message(f'Ошибка: {error_msg}', 'error')
            return
        
        transfer_id = response['transfer_id']
        share_type = response['type']
        filename = response['filename']
        filesize = response.get('size', 0)
        encryption_info = response.get('encryption')
        
        console.print_system_message(f'ID трансфера: {transfer_id}', 'info')
        console.print_system_message(f'Тип: {share_type}', 'info')
        console.print_system_message(f'Файл: {filename}', 'info')
        console.print_system_message(f'Размер: {Utils.format_size(filesize)}', 'info')
        
        if encryption_info and encryption_info.get('enabled'):
            console.print_system_message('Шифрование: данные будут расшифрованы при получении', 'info')
        
        data_socket = self.connection.create_data_connection(transfer_id, b'R')
        if not data_socket:
            return
        
        try:
            console.print_system_message('Ожидание отправителя...', 'info')
            import time
            time.sleep(1)
            
            data_socket.settimeout(30)
            
            if share_type == ShareTypes.FILE:
                self._download_file(response, data_socket)
            else:
                self._download_folder(response, data_socket)
        
        except Exception as e:
            console.print_system_message(f'Ошибка скачивания: {e}', 'error')
        finally:
            data_socket.close()
    
    def _read_exactly(self, sock, size):
        """
        Чтение точного количества байт из сокета
        
        Аргументы:
            sock: сокет
            size: количество байт для чтения
            
        Возвращает:
            прочитанные данные или None
        """
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                return None
        return data
    
    def _download_file(self, response, data_socket):
        """
        Скачивание одного файла с поддержкой расшифровки
        
        Аргументы:
            response: ответ сервера
            data_socket: сокет данных
        """
        filename = response['filename']
        filesize = response['size']
        encryption_info = response.get('encryption')
        
        use_encryption = encryption_info and encryption_info.get('enabled') and self.encryption and self.encryption.is_enabled()
        session_key = encryption_info.get('session_key') if use_encryption else None
        
        save_path = os.path.join(self.download_dir, filename)
        console.print_system_message(f'Сохранение в: {save_path}', 'info')
        
        try:
            received = 0
            last_update = 0
            
            with open(save_path, 'wb') as f:
                while received < filesize:
                    if use_encryption and session_key:
                        # Читаем заголовок (4 байта - длина оригинальных данных)
                        header = self._read_exactly(data_socket, 4)
                        if not header:
                            console.print_system_message('Соединение закрыто при чтении заголовка', 'warning')
                            break
                        
                        original_chunk_size = struct.unpack('!I', header)[0]
                        
                        # Размер зашифрованного пакета: 12 nonce + данные + 16 тег GCM
                        encrypted_size = 12 + original_chunk_size + 16
                        
                        # Читаем зашифрованные данные
                        encrypted_chunk = self._read_exactly(data_socket, encrypted_size)
                        if not encrypted_chunk:
                            console.print_system_message('Соединение закрыто при чтении данных', 'warning')
                            break
                        
                        # Расшифровываем
                        full_packet = header + encrypted_chunk
                        decrypted_chunk = self.encryption.decrypt_file_data(full_packet, session_key)
                        if decrypted_chunk is None:
                            console.print_system_message('Ошибка расшифровки данных', 'error')
                            break
                        
                        f.write(decrypted_chunk)
                        received += len(decrypted_chunk)
                    else:
                        # Без шифрования читаем напрямую
                        chunk_size = min(65536, filesize - received)
                        chunk = self._read_exactly(data_socket, chunk_size)
                        if not chunk:
                            console.print_system_message(
                                f'Соединение закрыто после {Utils.format_size(received)}', 
                                'warning'
                            )
                            break
                        
                        f.write(chunk)
                        received += len(chunk)
                    
                    # Обновляем прогресс
                    if self.show_progress and (received - last_update > 102400 or received == filesize):
                        console.print_progress(
                            received, 
                            filesize,
                            prefix='Загрузка',
                            suffix=Utils.format_size(received)
                        )
                        last_update = received
            
            console.finish_progress()
            
            if received == filesize:
                console.print_system_message(f'Файл успешно сохранён: {save_path}', 'success')
            else:
                console.print_system_message(
                    f'Получено только {Utils.format_size(received)} из {Utils.format_size(filesize)}', 
                    'error'
                )
                Utils.safe_remove(save_path)
        
        except Exception as e:
            console.finish_progress()
            console.print_system_message(f'Ошибка сохранения файла: {e}', 'error')
            Utils.safe_remove(save_path)
    
    def _download_folder(self, response, data_socket):
        """
        Скачивание папки с поддержкой расшифровки
        
        Аргументы:
            response: ответ сервера
            data_socket: сокет данных
        """
        folder_name = response['filename']
        files = response['files']
        total_size = response['size']
        encryption_info = response.get('encryption')
        
        use_encryption = encryption_info and encryption_info.get('enabled') and self.encryption and self.encryption.is_enabled()
        session_key = encryption_info.get('session_key') if use_encryption else None
        
        folder_path = os.path.join(self.download_dir, folder_name)
        Utils.ensure_dir(folder_path)
        
        console.print_system_message(
            f'Скачивание: {folder_name} ({len(files)} файлов, {Utils.format_size(total_size)})',
            'info'
        )
        
        # Список для хранения последних 3 строк вывода
        last_file_lines = []
        
        def update_file_progress(line):
            """Обновление прогресса с ограничением в 3 строки"""
            nonlocal last_file_lines
            # Очищаем предыдущие строки
            for _ in range(len(last_file_lines)):
                console.clear_line()
                sys.stdout.write('\033[F')
            sys.stdout.write('\033[K')
            
            last_file_lines.append(line)
            if len(last_file_lines) > 3:
                last_file_lines.pop(0)
            
            for l in last_file_lines:
                print(l)
            sys.stdout.flush()
        
        try:
            for i, file_info in enumerate(files, 1):
                full_path = os.path.join(folder_path, file_info['path'])
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                file_size = file_info['size']
                
                # Показываем только в последних 3 строках
                update_file_progress(f'  [{i}/{len(files)}] {file_info["path"]} ({Utils.format_size(file_size)})')
                
                received = 0
                
                with open(full_path, 'wb') as f:
                    while received < file_size:
                        if use_encryption and session_key:
                            # Читаем заголовок
                            header = self._read_exactly(data_socket, 4)
                            if not header:
                                break
                            
                            original_chunk_size = struct.unpack('!I', header)[0]
                            encrypted_size = 12 + original_chunk_size + 16
                            
                            # Читаем зашифрованные данные
                            encrypted_chunk = self._read_exactly(data_socket, encrypted_size)
                            if not encrypted_chunk:
                                break
                            
                            # Расшифровываем
                            full_packet = header + encrypted_chunk
                            decrypted_chunk = self.encryption.decrypt_file_data(full_packet, session_key)
                            if decrypted_chunk is None:
                                update_file_progress(f'    Ошибка расшифровки')
                                break
                            
                            f.write(decrypted_chunk)
                            received += len(decrypted_chunk)
                        else:
                            chunk_size = min(65536, file_size - received)
                            chunk = self._read_exactly(data_socket, chunk_size)
                            if not chunk:
                                break
                            
                            f.write(chunk)
                            received += len(chunk)
                
                if received == file_size:
                    update_file_progress(f'  [{i}/{len(files)}] OK: {file_info["path"]}')
                else:
                    update_file_progress(
                        f'  [{i}/{len(files)}] Частично: {file_info["path"]} ({Utils.format_size(received)}/{Utils.format_size(file_size)})'
                    )
            
            # Очищаем последние строки прогресса
            for _ in range(len(last_file_lines)):
                sys.stdout.write('\033[F')
                sys.stdout.write('\033[K')
            
            console.print_system_message(f'Сохранено: {folder_path}', 'success')
        
        except Exception as e:
            console.print_system_message(f'Ошибка: {e}', 'error')