"""
Главный модуль клиента FileHub
"""

import threading
from config import ClientConfig
from auth import AuthManager
from connection import ConnectionManager
from shares import ShareManager
from downloads import DownloadManager
from uploads import UploadManager
from protocols import MessageActions
from encryption import ClientEncryption


class FileHubClient:
    """Главный класс клиента FileHub"""
    
    def __init__(self, config_path='client.conf'):
        """
        Инициализация клиента
        
        Аргументы:
            config_path: путь к файлу конфигурации
        """
        # Инициализация компонентов
        self.config = ClientConfig(config_path)
        self.auth = AuthManager(self.config)
        self.connection = ConnectionManager(self.config)
        self.encryption = ClientEncryption()
        
        # Создаем менеджеры с передачей encryption
        self.shares = ShareManager(self.connection, self.config)
        self.downloads = DownloadManager(self.connection, self.config)
        self.uploads = UploadManager(self.connection, self.shares.local_shares, self.config)
        
        # Передаем encryption в менеджеры
        self.downloads.set_encryption(self.encryption)
        self.uploads.set_encryption(self.encryption)
        
        # Настройка колбэков
        # ВАЖНО: Оборачиваем обработчик upload request в отдельный поток
        def async_upload_handler(request):
            """Асинхронная обработка запроса на отправку файла"""
            transfer_id = request.get('transfer_id', 'unknown')
            thread = threading.Thread(
                target=self.uploads.handle_upload_request,
                args=(request,),
                daemon=True,
                name=f"Upload-{transfer_id}"
            )
            thread.start()
        
        self.connection.on_upload_request = async_upload_handler
        self.connection.on_disconnect = self._on_disconnect
        
        # Запуск пинг-потока
        self._ping_thread = None
    
    def connect(self, username, password):
        """
        Подключение к серверу
        
        Аргументы:
            username: имя пользователя
            password: пароль
            
        Возвращает:
            True при успешном подключении
        """
        if self.connection.connect(username, password):
            # Проверяем, требует ли сервер шифрование
            response = self.connection.last_response
            if response:
                encryption_params = response.get('encryption')
                if encryption_params:
                    self.encryption.enable(encryption_params)
                    print(f'[INFO] Шифрование включено: {encryption_params["algorithm"]}')
            
            # username уже установлен в connection
            # Перезагружаем раздачи для этого пользователя (ВАЖНО!)
            self.shares.reload_shares_for_user()
            
            # Валидация локальных раздач при подключении
            invalid_count = self.shares.cleanup_invalid_shares()
            if invalid_count > 0:
                print(f'Очищено {invalid_count} невалидных раздач')
            
            # Синхронизация раздач с сервером
            synced = self.shares.sync_shares_with_server()
            
            # Запуск пинга для поддержания активности
            self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self._ping_thread.start()
            return True
        return False
    
    def disconnect(self):
        """Отключение от сервера"""
        # Дожидаемся завершения активных передач
        self.uploads.wait_for_all_transfers(timeout=5)
        self.connection.disconnect()
    
    def share(self, path):
        """
        Расшаривание файла или папки
        
        Аргументы:
            path: путь к файлу или папке
        """
        self.shares.share(path)
    
    def list_shares(self):
        """Список всех раздач"""
        self.shares.list_shares()
    
    def list_my_shares(self):
        """Список своих раздач"""
        self.shares.list_my_shares()
    
    def download(self, share_id):
        """
        Скачивание раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        self.downloads.download(share_id)
    
    def remove_share(self, share_id):
        """
        Удаление раздачи
        
        Аргументы:
            share_id: ID раздачи
        """
        self.shares.remove_share(share_id)
    
    def show_stats(self):
        """Показ статистики сервера"""
        response = self.connection.send_command({'action': MessageActions.STATS})
        
        if response and response.get('status') == 'ok':
            print('\nСтатистика сервера:')
            print('=' * 40)
            print(f'Время работы: {response["server_uptime"]}')
            print(f'Пользователей онлайн: {response["active_users"]}')
            print(f'Зарегистрировано: {response.get("registered_users", "Н/Д")}')
            print(f'Активных раздач: {response["total_shares"]}')
            print(f'Всего подключений: {response["total_connections"]}')
            print(f'Всего скачиваний: {response["total_downloads"]}')
            print(f'Передано данных: {response["total_bytes_transferred"]}')
            print(f'Требуется пароль: {"да" if response.get("require_password", False) else "нет"}')
            
            # Информация о шифровании
            encryption_stats = response.get('encryption', {})
            if encryption_stats.get('enabled'):
                print(f'Шифрование: включено ({encryption_stats.get("active_session_keys", 0)} активных ключей)')
            else:
                print('Шифрование: выключено')
            
            print('=' * 40)
    
    def _ping_loop(self):
        """Цикл пинга для поддержания активности раздач"""
        import time
        while self.connection.connected:
            time.sleep(60)
            if self.shares.my_shares and self.connection.connected:
                self.connection.send_ping(self.shares.get_share_ids())
    
    def _on_disconnect(self):
        """Обработчик отключения"""
        # Ожидаем завершения активных передач при отключении
        self.uploads.wait_for_all_transfers(timeout=3)


def main():
    """Точка входа"""
    from ui import UserInterface
    
    client = FileHubClient('client.conf')
    ui = UserInterface(client)
    ui.start()


if __name__ == '__main__':
    main()