"""
Главный модуль клиента FileHub
"""

import threading
import sys
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
    
    def __init__(self, config_path='client.conf', service_mode=False):
        """
        Инициализация клиента
        
        Аргументы:
            config_path: путь к файлу конфигурации
            service_mode: режим сервиса (только раздача, без UI)
        """
        self.service_mode = service_mode
        
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
        
        # Для сервисного режима
        self._service_running = False
        self._service_credentials = None
    
    def set_service_credentials(self, username, password):
        """
        Установка учетных данных для сервисного режима
        
        Аргументы:
            username: имя пользователя
            password: пароль
        """
        self._service_credentials = (username, password)
    
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
            
            # Перезагружаем раздачи для этого пользователя
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
        self.uploads.wait_for_all_transfers(timeout=5)
        self.connection.disconnect()
    
    def share(self, path):
        """Расшаривание файла или папки"""
        self.shares.share(path)
    
    def list_shares(self):
        """Список всех раздач"""
        self.shares.list_shares()
    
    def list_my_shares(self):
        """Список своих раздач"""
        self.shares.list_my_shares()
    
    def download(self, share_id):
        """Скачивание раздачи"""
        self.downloads.download(share_id)
    
    def remove_share(self, share_id):
        """Удаление раздачи"""
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
            
            encryption_stats = response.get('encryption', {})
            if encryption_stats.get('enabled'):
                print(f'Шифрование: включено ({encryption_stats.get("active_session_keys", 0)} активных ключей)')
            else:
                print('Шифрование: выключено')
            
            print('=' * 40)
    
    def run_service(self, username, password, auto_reconnect=True):
        """
        Запуск в режиме сервиса (только раздача)
        
        Аргументы:
            username: имя пользователя
            password: пароль
            auto_reconnect: автоматическое переподключение при обрыве
        """
        import time
        import signal
        
        self._service_running = True
        
        # Обработчик сигналов для graceful shutdown
        def signal_handler(signum, frame):
            print(f'\n[СЕРВИС] Получен сигнал {signum}, завершение...')
            self._service_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print(f'[СЕРВИС] Запуск в режиме раздачи')
        print(f'[СЕРВИС] Пользователь: {username}')
        print(f'[СЕРВИС] Автопереподключение: {"включено" if auto_reconnect else "выключено"}')
        print(f'[СЕРВИС] Для остановки нажмите Ctrl+C')
        print()
        
        while self._service_running:
            try:
                # Подключаемся
                print(f'[СЕРВИС] Подключение к серверу...')
                if self.connect(username, password):
                    print(f'[СЕРВИС] Подключено как {username}')
                    
                    # Показываем информацию о раздачах
                    my_shares_count = len(self.shares.my_shares)
                    if my_shares_count > 0:
                        print(f'[СЕРВИС] Активных раздач: {my_shares_count}')
                        for share_id in self.shares.my_shares:
                            share_data = self.shares.local_shares.get(share_id, {})
                            local_path = share_data.get('local_path', 'Неизвестно')
                            share_type = share_data.get('type', 'Неизвестно')
                            print(f'  - [{share_type}] {local_path}')
                    else:
                        print(f'[СЕРВИС] Нет активных раздач')
                    
                    # Основной цикл сервиса
                    while self._service_running and self.connection.connected:
                        time.sleep(5)
                        
                        # Проверяем активные передачи
                        active_count = self.uploads.get_active_transfers_count()
                        if active_count > 0:
                            print(f'[СЕРВИС] Активных передач: {active_count}')
                    
                    # Если вышли из цикла и сервис еще работает - значит потеряли связь
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
        
        # Завершение
        print(f'[СЕРВИС] Остановка сервиса...')
        self.disconnect()
        print(f'[СЕРВИС] Сервис остановлен')
    
    def share_paths_in_service(self, paths):
        """
        Расшаривание списка путей в сервисном режиме
        
        Аргументы:
            paths: список путей для раздачи
        """
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
    parser.add_argument('--service', action='store_true', 
                       help='Запуск в режиме сервиса (только раздача)')
    parser.add_argument('--username', '-u', type=str,
                       help='Имя пользователя')
    parser.add_argument('--password', '-p', type=str,
                       help='Пароль')
    parser.add_argument('--share', '-s', type=str, nargs='+',
                       help='Пути для раздачи (только в сервисном режиме)')
    parser.add_argument('--config', '-c', type=str, default='client.conf',
                       help='Путь к файлу конфигурации')
    parser.add_argument('--no-reconnect', action='store_true',
                       help='Отключить автоматическое переподключение')
    
    args = parser.parse_args()
    
    if args.service:
        # Сервисный режим
        client = FileHubClient(args.config, service_mode=True)
        
        # Получаем учетные данные
        username = args.username
        password = args.password
        
        if not username:
            print('[СЕРВИС] Ошибка: не указано имя пользователя (--username)')
            sys.exit(1)
        
        if not password:
            # Пробуем получить сохраненный пароль
            saved_password = client.auth.get_saved_password(username)
            if saved_password:
                password = saved_password
                print(f'[СЕРВИС] Использован сохраненный пароль для {username}')
            else:
                print('[СЕРВИС] Ошибка: не указан пароль (--password) и нет сохраненного')
                sys.exit(1)
        
        # Если указаны пути для раздачи, расшариваем их перед запуском
        if args.share:
            # Подключаемся временно для расшаривания
            if client.connect(username, password):
                client.share_paths_in_service(args.share)
                client.disconnect()
                # Небольшая пауза перед переподключением в сервисном режиме
                import time
                time.sleep(2)
        
        # Запускаем сервис
        client.run_service(username, password, auto_reconnect=not args.no_reconnect)
    else:
        # Интерактивный режим
        from ui import UserInterface
        
        client = FileHubClient(args.config)
        ui = UserInterface(client)
        ui.start()


if __name__ == '__main__':
    main()