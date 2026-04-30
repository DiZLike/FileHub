import os
import sys
import socket
from network.protocol import ShareTypes, MessageActions
from utils.helpers import format_size, ensure_dir, safe_remove

class DownloadManager:
    """Менеджер скачивания файлов"""
    
    def __init__(self, connection, config):
        self.connection = connection
        self.download_dir = config.downloads.download_dir
        self.max_retries = config.downloads.max_retries
        self.show_progress = config.interface.show_progress
        self.encryption = None
        
        ensure_dir(self.download_dir)
    
    def set_encryption(self, encryption):
        """Установка объекта шифрования"""
        self.encryption = encryption
    
    def download(self, share_id: str):
        """Скачивание раздачи"""
        from ui.console import console
        
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
        console.print_system_message(f'Файл: {filename}', 'info')
        console.print_system_message(f'Размер: {format_size(filesize)}', 'info')
        
        if encryption_info and encryption_info.get('enabled'):
            console.print_system_message('TLS: данные передаются по защищённому каналу', 'info')
        
        data_socket = self.connection.create_data_connection(transfer_id, b'R')
        if not data_socket:
            return
        
        try:
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
            # Сокет закрывается внутри методов _download_file / _download_folder
            pass
    
    def _download_file(self, response: dict, data_socket):
        """Скачивание одного файла"""
        from ui.console import console
        
        transfer_id = response.get('transfer_id', 'unknown')
        short_id = transfer_id[:8]
        filename = response['filename']
        filesize = response['size']
        
        save_path = os.path.join(self.download_dir, filename)
        console.print_system_message(f'Сохранение в: {save_path}', 'info')
        
        try:
            received = 0
            last_update = 0
            
            data_socket.settimeout(60)
            
            console.print_system_message(f'[{short_id}] Скачивание: {filename} ({format_size(filesize)})', 'info')
            
            with open(save_path, 'wb') as f:
                while received < filesize:
                    chunk_size = min(65536, filesize - received)
                    chunk = self._recv_exactly(data_socket, chunk_size)
                    if not chunk:
                        break
                    
                    f.write(chunk)
                    received += len(chunk)
                    
                    if self.show_progress and (received - last_update > 102400 or received == filesize):
                        console.update_multi_progress(
                            short_id, received, filesize,
                            prefix=f'[D{short_id}]',
                            suffix=f'{format_size(received)}/{format_size(filesize)}'
                        )
                        last_update = received
            
            console.update_multi_progress(
                short_id, received, filesize,
                prefix=f'[D{short_id}]',
                suffix=f'{format_size(received)}/{format_size(filesize)}',
                finished=True
            )
            
            if received == filesize:
                # Отправляем подтверждение
                try:
                    data_socket.sendall(b'OK')
                except Exception:
                    pass
                console.print_system_message(
                    f'[✓] {short_id}: {filename} скачан ({format_size(received)})',
                    'success'
                )
            else:
                console.print_system_message(
                    f'[⚠] {short_id}: {filename} частично ({format_size(received)} из {format_size(filesize)})',
                    'error'
                )
                safe_remove(save_path)
        
        except Exception as e:
            console.update_multi_progress(short_id, 0, 0, finished=True)
            console.print_system_message(f'[{short_id}] Ошибка сохранения файла: {e}', 'error')
            safe_remove(save_path)
        finally:
            try:
                data_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                data_socket.close()
            except Exception:
                pass

    def _download_folder(self, response: dict, data_socket):
        """Скачивание папки"""
        from ui.console import console
        
        transfer_id = response.get('transfer_id', 'unknown')
        short_id = transfer_id[:8]
        folder_name = response['filename']
        files = response['files']
        total_size = response['size']
        
        folder_path = os.path.join(self.download_dir, folder_name)
        ensure_dir(folder_path)
        
        console.print_system_message(
            f'[{short_id}] Скачивание: {folder_name} ({len(files)} файлов, {format_size(total_size)})',
            'info'
        )
        
        data_socket.settimeout(60)
        
        total_received = 0
        all_ok = True
        
        try:
            for i, file_info in enumerate(files, 1):
                full_path = os.path.join(folder_path, file_info['path'])
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                file_size = file_info['size']
                received = 0
                
                with open(full_path, 'wb') as f:
                    while received < file_size:
                        chunk_size = min(65536, file_size - received)
                        chunk = self._recv_exactly(data_socket, chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        total_received += len(chunk)
                
                if received == file_size:
                    console.update_multi_progress(
                        short_id, total_received, total_size,
                        prefix=f'[D{short_id}]',
                        suffix=f'[{i}/{len(files)}] {format_size(total_received)}/{format_size(total_size)}'
                    )
                else:
                    all_ok = False
            
            console.update_multi_progress(
                short_id, total_received, total_size,
                prefix=f'[D{short_id}]',
                suffix=f'{format_size(total_received)}/{format_size(total_size)}',
                finished=True
            )
            
            if all_ok:
                # Отправляем подтверждение
                try:
                    data_socket.sendall(b'OK')
                except Exception:
                    pass
                console.print_system_message(
                    f'[✓] {short_id}: {folder_name} скачана ({len(files)} файлов, {format_size(total_received)})',
                    'success'
                )
            else:
                console.print_system_message(
                    f'[⚠] {short_id}: {folder_name} скачана с ошибками ({format_size(total_received)} из {format_size(total_size)})',
                    'warning'
                )
        
        except Exception as e:
            console.update_multi_progress(short_id, 0, 0, finished=True)
            console.print_system_message(f'[{short_id}] Ошибка: {e}', 'error')
        finally:
            try:
                data_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                data_socket.close()
            except Exception:
                pass
    
    def _recv_exactly(self, sock, size: int) -> bytes:
        """Чтение точного количества байт"""
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