"""
Пользовательский интерфейс клиента
"""

import getpass
import threading
import time
from protocols import MessageActions
from console_ui import console

class UserInterface:
    """Консольный интерфейс клиента с четким разделением зон вывода"""
    
    def __init__(self, client):
        """
        Инициализация интерфейса
        
        Аргументы:
            client: экземпляр клиента
        """
        self.client = client
        self._running = True
        self._notification_queue = []
        self._notification_lock = threading.Lock()
        
        # Подписываемся на системные сообщения
        self._setup_notification_handler()
    
    def _setup_notification_handler(self):
        """Настройка обработчика системных уведомлений"""
        original_upload_handler = self.client.uploads.handle_upload_request
        
        def wrapped_upload_handler(request):
            """Оборачиваем обработчик для перехвата сообщений"""
            requester = request.get('requester')
            filename = request.get('filename')
            self.add_notification(f'Запрос отправки: {filename} от {requester}')
            original_upload_handler(request)
        
        self.client.uploads.handle_upload_request = wrapped_upload_handler
    
    def start(self):
        """Запуск интерфейса"""
        console.clear_screen()
        self._print_banner()
        
        # Ввод учетных данных
        username, password = self._get_credentials()
        if not username:
            return
        
        # Подключение с отображением прогресса
        console.print_system_message('Подключение к серверу...', 'info')
        
        if not self.client.connect(username, password):
            console.print_system_message('Не удалось подключиться', 'error')
            return
        
        console.print_system_message(f'Подключено как {username}', 'success')
        
        # Сохранение пароля
        if self.client.auth.remember_password and password:
            self.client.auth.save_password_hash(username, password)
            console.print_system_message('Пароль сохранен', 'info')
        
        # Запуск обработчика уведомлений
        notification_thread = threading.Thread(target=self._notification_worker, daemon=True)
        notification_thread.start()
        
        # Главный цикл
        try:
            self._main_loop()
        except KeyboardInterrupt:
            console.print_system_message('Завершение работы...', 'warning')
        finally:
            self._running = False
            self.client.disconnect()
            console.print_system_message('Отключено', 'info')
    
    def _print_banner(self):
        """Вывод баннера"""
        print('=' * 50)
        print('FileHub Client v1.0')
        print('=' * 50)
        print()
    
    def _get_credentials(self):
        """
        Получение учетных данных
        
        Возвращает:
            (имя пользователя, пароль)
        """
        console.print_separator('-')
        username = input('Имя пользователя: ').strip()
        if not username:
            console.print_system_message('Имя пользователя не может быть пустым', 'error')
            return None, None
        
        # Проверка сохраненного пароля
        saved = self.client.auth.check_saved_password(username)
        
        if saved:
            console.print_system_message('Найден сохранённый пароль', 'info')
            password = getpass.getpass('Пароль (Enter для сохранённого): ')
        else:
            password = getpass.getpass('Пароль (Enter если не требуется): ')
        
        return username, password
    
    def _main_loop(self):
        """Главный цикл с улучшенным меню"""
        while self.client.connection.connected and self._running:
            console.clear_screen()
            
            # Отображаем статус подключения
            status_text = f'Подключен: {self.client.connection.username} | Сервер: {self.client.connection.server_host}'
            console.print_separator('=', len(status_text))
            print(status_text)
            console.print_separator('=', len(status_text))
            print()

            # Показываем активные передачи
            self._show_active_transfers()
            
            # Меню
            menu_items = [
                '1. Поделиться файлом/папкой',
                '2. Список всех раздач',
                '3. Мои раздачи',
                '4. Скачать раздачу',
                '5. Удалить раздачу',
                '6. Статистика сервера',
                '7. Выход',
                '',
                '-' * 40,
                'Подсказка: Ctrl+C для экстренного выхода'
            ]
            
            console.print_menu(menu_items)
            print()
            
            # Зона уведомлений
            self._show_notifications()
            
            try:
                choice = input('> Выберите действие: ').strip()
            except (KeyboardInterrupt, EOFError):
                break
            
            if not self.client.connection.connected:
                console.print_system_message('Соединение потеряно', 'error')
                break
            
            self._process_choice(choice)
    
    def _process_choice(self, choice):
        """
        Обработка выбора с разделением экранов
        
        Аргументы:
            choice: выбранный пункт меню
        """
        if choice == '1':
            console.clear_screen()
            console.print_header('Создание раздачи')
            path = input('\nПуть к файлу или папке: ').strip()
            if path:
                print()
                self.client.share(path)
            self._wait_for_exit()
        
        elif choice == '2':
            console.clear_screen()
            console.print_header('Все раздачи')
            self.client.list_shares()
            self._wait_for_exit()
        
        elif choice == '3':
            console.clear_screen()
            console.print_header('Мои раздачи')
            self.client.list_my_shares()
            self._wait_for_exit()
        
        elif choice == '4':
            console.clear_screen()
            console.print_header('Скачивание раздачи')
            share_id = input('\nID раздачи: ').strip()
            if share_id:
                print()
                self.client.download(share_id)
            self._wait_for_exit()
        
        elif choice == '5':
            console.clear_screen()
            console.print_header('Удаление раздачи')
            share_id = input('\nID раздачи: ').strip()
            if share_id:
                print()
                self.client.remove_share(share_id)
            self._wait_for_exit()
        
        elif choice == '6':
            console.clear_screen()
            console.print_header('Статистика сервера')
            self.client.show_stats()
            self._wait_for_exit()
        
        elif choice == '7':
            self.client.connection.connected = False
        
        else:
            console.print_system_message('Неверный выбор. Попробуйте снова.', 'warning')
            time.sleep(1)
    
    def _wait_for_exit(self):
        """
        Ожидание с возможностью выхода по 'q' или '0'
        """
        console.clear_all_progress()
        print()
        print('-' * 40)
        print('Нажмите Enter для возврата в меню, или введите "q" / "0" для выхода')
        
        try:
            user_input = input('> ').strip().lower()
            # Если пользователь ввел q или 0, просто возвращаемся (ничего не делаем)
            if user_input in ('q', '0'):
                pass  # Просто возвращаемся в главное меню
            # Enter или любой другой символ - тоже возвращаемся
        except (KeyboardInterrupt, EOFError):
            pass
    
    def add_notification(self, message, level='info'):
        """
        Добавление уведомления в очередь
        
        Аргументы:
            message: текст уведомления
            level: уровень (info, success, error, warning)
        """
        with self._notification_lock:
            self._notification_queue.append({
                'message': message,
                'level': level,
                'time': time.time()
            })
            # Ограничиваем очередь
            if len(self._notification_queue) > 10:
                self._notification_queue.pop(0)
    
    def _show_notifications(self):
        """Отображение последних уведомлений"""
        with self._notification_lock:
            if self._notification_queue:
                print('Последние события:')
                for notif in self._notification_queue[-3:]:  # Последние 3
                    icon = {
                        'info': '(*)',
                        'success': '(+)',
                        'error': '(-)',
                        'warning': '(!)'
                    }.get(notif['level'], '(*)')
                    print(f'  {icon} {notif["message"]}')
                print()
    
    def _notification_worker(self):
        """Фоновый обработчик уведомлений"""
        while self._running:
            time.sleep(0.5)
            # Автоматическая очистка старых уведомлений
            with self._notification_lock:
                current_time = time.time()
                self._notification_queue = [
                    n for n in self._notification_queue 
                    if current_time - n['time'] < 30  # Удаляем старше 30 секунд
                ]
    
    def _show_active_transfers(self):
        """Компактное отображение активных передач"""
        active_count = self.client.uploads.get_active_transfers_count()
        if active_count > 0:
            print(f'\n[Активные передачи: {active_count}]')