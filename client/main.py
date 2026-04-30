import threading
import sys
from core.config import ClientConfig
from core.auth import AuthManager
from network.connection import ConnectionManager
from network.encryption import ClientEncryption
from services.shares import ShareManager
from services.downloads import DownloadManager
from services.uploads import UploadManager


class FileHubClient:
    """Главный класс клиента FileHub"""
    
    def __init__(self, config_path='client.conf', service_mode=False):
        self.service_mode = service_mode
        
        self.config = ClientConfig(config_path)
        self.auth = AuthManager(self.config)
        self.connection = ConnectionManager(self.config)
        self.encryption = ClientEncryption()
        
        self.connection.set_encryption(self.encryption)
        
        self.shares = ShareManager(self.connection, self.config)
        self.downloads = DownloadManager(self.connection, self.config)
        self.uploads = UploadManager(self.connection, self.shares.local_shares, self.config)
        
        self.downloads.set_encryption(self.encryption)
        self.uploads.set_encryption(self.encryption)
        
        self._setup_callbacks()
        
        self._ping_thread = None
        self._service_running = False
        self._service_credentials = None
    
    def _setup_callbacks(self):
        """Настройка колбэков"""
        def async_upload_handler(request):
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
    
    def set_service_credentials(self, username: str, password: str):
        """Установка учетных данных для сервисного режима"""
        self._service_credentials = (username, password)
    
    def connect(self, username: str, password: str) -> bool:
        """Подключение к серверу"""
        if self.connection.connect(username, password):
            response = self.connection.last_response
            if response:
                encryption_params = response.get('encryption')
                if encryption_params:
                    self.encryption.enable(encryption_params)
                    print(f'[INFO] Шифрование включено: {encryption_params["algorithm"]}')
            
            self.shares.reload_shares_for_user()
            
            invalid_count = self.shares.cleanup_invalid_shares()
            if invalid_count > 0:
                print(f'Очищено {invalid_count} невалидных раздач')
            
            self.shares.sync_shares_with_server()
            
            self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self._ping_thread.start()
            return True
        return False
    
    def disconnect(self):
        """Отключение от сервера"""
        self.uploads.wait_for_all_transfers(timeout=5)
        self.connection.disconnect()
    
    def share(self, path: str):
        """Расшаривание файла или папки"""
        self.shares.share(path)
    
    def list_shares(self):
        """Список всех раздач"""
        self.shares.list_shares()
    
    def list_my_shares(self):
        """Список своих раздач"""
        self.shares.list_my_shares()
    
    def download(self, share_id: str):
        """Скачивание раздачи"""
        self.downloads.download(share_id)
    
    def remove_share(self, share_id: str):
        """Удаление раздачи"""
        self.shares.remove_share(share_id)
    
    def show_stats(self):
        """Показ статистики сервера"""
        from network.protocol import MessageActions
        
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
            
            encryption_stats = response.get('encryption', {})
            if encryption_stats.get('enabled'):
                print(f'Шифрование: включено ({encryption_stats.get("protocol", "TLSv1.2+")})')
            else:
                print('Шифрование: отключено')
            print('=' * 40)
    
    def run_service(self, username: str, password: str, auto_reconnect: bool = True):
        """Запуск в режиме сервиса (только раздача)"""
        import time
        import signal
        
        self._service_running = True
        
        def signal_handler(signum, frame):
            print(f'\n[СЕРВИС] Получен сигнал {signum}, завершение...')
            self._service_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print(f'[СЕРВИС] Запуск в режиме раздачи')
        print(f'[СЕРВИС] Пользователь: {username}')
        print(f'[СЕРВИС] Автопереподключение: {"включено" if auto_reconnect else "отключено"}')
        print(f'[СЕРВИС] Для остановки нажмите Ctrl+C')
        print()
        
        while self._service_running:
            try:
                print(f'[СЕРВИС] Подключение к серверу...')
                if self.connect(username, password):
                    print(f'[СЕРВИС] Подключено как {username}')
                    
                    my_shares_count = len(self.shares.my_shares)
                    if my_shares_count > 0:
                        print(f'[СЕРВИС] Активных раздач: {my_shares_count}')
                        for share_id in self.shares.my_shares:
                            share_data = self.shares.local_shares.get(share_id, {})
                            local_path = share_data.get('local_path', 'Неизвестно')
                            share_type = share_data.get('type', 'Неизвестно')
                            print(f'  - [{share_type}] {local_path}')
                    
                    while self._service_running and self.connection.connected:
                        time.sleep(5)
                        
                        active_count = self.uploads.get_active_transfers_count()
                        if active_count > 0:
                            print(f'[СЕРВИС] Активных передач: {active_count}')
                    
                    if self._service_running:
                        print(f'[СЕРВИС] Соединение потеряно')
                        if auto_reconnect:
                            print(f'[СЕРВИС] Попытка переподключения через 10 секунд...')
                            time.sleep(10)
                        else:
                            break
                else:
                    print(f'[СЕРВИС] Не удалось подключиться')
                    if auto_reconnect:
                        print(f'[СЕРВИС] Попытка переподключения через 30 секунд...')
                        time.sleep(30)
                    else:
                        break
                        
            except Exception as e:
                print(f'[СЕРВИС] Ошибка: {e}')
                if auto_reconnect:
                    print(f'[СЕРВИС] Переподключение через 30 секунд...')
                    time.sleep(30)
                else:
                    break
        
        print(f'[СЕРВИС] Остановка сервиса...')
        self.disconnect()
        print(f'[СЕРВИС] Сервис остановлен')
    
    def share_paths_in_service(self, paths: list):
        """Расшаривание списка путей в сервисном режиме"""
        if not self.connection.connected:
            print(f'[СЕРВИС] Нет подключения, невозможно расшарить')
            return
        
        for path in paths:
            print(f'[СЕРВИС] Расшаривание: {path}')
            self.share(path)
    
    def _ping_loop(self):
        """Цикл пинга для поддержания активности раздач"""
        import time
        while self.connection.connected:
            time.sleep(60)
            if self.shares.my_shares and self.connection.connected:
                self.connection.send_ping(self.shares.get_share_ids())
    
    def _on_disconnect(self):
        """Обработчик отключения"""
        self.uploads.wait_for_all_transfers(timeout=3)


def main():
    """Точка входа"""
    import argparse
    
    parser = argparse.ArgumentParser(description='FileHub Client')
    parser.add_argument('--service', action='store_true', help='Запуск в режиме сервиса (только раздача)')
    parser.add_argument('--username', '-u', type=str, help='Имя пользователя')
    parser.add_argument('--password', '-p', type=str, help='Пароль')
    parser.add_argument('--share', '-s', type=str, nargs='+', help='Пути для раздачи (только в сервисном режиме)')
    parser.add_argument('--config', '-c', type=str, default='client.conf', help='Путь к файлу конфигурации')
    parser.add_argument('--no-reconnect', action='store_true', help='Отключить автоматическое переподключение')
    
    args = parser.parse_args()
    
    if args.service:
        client = FileHubClient(args.config, service_mode=True)
        
        username = args.username
        password = args.password
        
        if not username:
            print('[СЕРВИС] Ошибка: не указано имя пользователя (--username)')
            sys.exit(1)
        
        if not password:
            saved_password = client.auth.get_saved_password(username)
            if saved_password:
                password = saved_password
                print(f'[СЕРВИС] Использован сохраненный пароль для {username}')
            else:
                print('[СЕРВИС] Ошибка: не указан пароль (--password) и нет сохраненного')
                sys.exit(1)
        
        if args.share:
            if client.connect(username, password):
                client.share_paths_in_service(args.share)
                client.disconnect()
                import time
                time.sleep(2)
        
        client.run_service(username, password, auto_reconnect=not args.no_reconnect)
    else:
        from ui.interface import UserInterface
        
        client = FileHubClient(args.config)
        ui = UserInterface(client)
        ui.start()


if __name__ == '__main__':
    main()