"""
Управление консольным выводом с очисткой и форматированием
"""

import os
import sys
import threading
import datetime


class ConsoleManager:
    """Менеджер консольного вывода с поддержкой очистки и разделения зон"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._progress_line_active = False
        self._last_menu_lines = 0
        self._is_windows = os.name == 'nt'
        # Для мульти-прогресса
        self._progress_bars = {}  # transfer_id -> строка прогресса
        self._progress_lines_count = 0  # сколько строк занимают прогресс-бары
        
    def clear_screen(self):
        """Очистка всего экрана"""
        with self._lock:
            if self._is_windows:
                os.system('cls')
            else:
                os.system('clear')
            self._progress_lines_count = 0
            self._progress_bars.clear()
            self._progress_line_active = False
    
    def clear_line(self):
        """Очистка текущей строки"""
        with self._lock:
            sys.stdout.write('\r' + ' ' * 120 + '\r')
            sys.stdout.flush()
    
    def clear_last_lines(self, count):
        """
        Очистка последних N строк
        
        Аргументы:
            count: количество строк для очистки
        """
        with self._lock:
            for _ in range(count):
                sys.stdout.write('\033[F')  # Вверх на строку
                sys.stdout.write('\033[K')  # Очистка строки
            sys.stdout.flush()
    
    def print_system_message(self, message, level='info'):
        """
        Вывод системного сообщения в отдельной зоне
        
        Аргументы:
            message: текст сообщения
            level: уровень (info, success, error, warning)
        """
        with self._lock:
            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
            
            # Сохраняем прогресс-бары
            active_bars = dict(self._progress_bars)
            
            # Очищаем строки прогресса
            if self._progress_lines_count > 0:
                for _ in range(self._progress_lines_count):
                    sys.stdout.write('\033[F')
                    sys.stdout.write('\033[K')
                self._progress_lines_count = 0
            
            # Завершаем прогресс-бар если активен
            if self._progress_line_active:
                sys.stdout.write('\n')
                sys.stdout.flush()
                self._progress_line_active = False
            
            prefix = {
                'info': f'[{timestamp}] INFO',
                'success': f'[{timestamp}] OK',
                'error': f'[{timestamp}] ERROR',
                'warning': f'[{timestamp}] WARN'
            }.get(level, f'[{timestamp}] INFO')
            
            # Выводим сообщение
            print(f'{prefix} {message}')
            self._last_menu_lines = 0
            
            # Восстанавливаем прогресс-бары
            if active_bars:
                self._progress_bars = active_bars
                self._redraw_progress_bars_no_clear()
    
    def print_progress(self, current, total, prefix='', suffix=''):
        """
        Обновляемый прогресс-бар (в одной строке) — для обратной совместимости
        Перенаправляет на update_multi_progress
        
        Аргументы:
            current: текущее значение
            total: общее значение
            prefix: текст перед прогрессом
            suffix: текст после прогресса
        """
        with self._lock:
            percent = (current / total * 100) if total > 0 else 0
            bar_length = 30
            filled = int(bar_length * current / total) if total > 0 else 0
            
            bar = '#' * filled + '-' * (bar_length - filled)
            
            output = f'\r{prefix} [{bar}] {percent:.1f}% {suffix}'
            output = output.ljust(100)
            
            sys.stdout.write(output)
            sys.stdout.flush()
            self._progress_line_active = True
    
    def update_multi_progress(self, transfer_id, current, total, prefix='', suffix='', finished=False):
        """
        Обновление прогресс-бара с фиксированной позицией для каждого трансфера
        
        Аргументы:
            transfer_id: уникальный ID трансфера (короткий)
            current: текущее значение
            total: общее значение
            prefix: текст перед прогрессом
            suffix: текст после прогресса
            finished: True если передача завершена (удаляет строку)
        """
        with self._lock:
            # Форматируем прогресс-бар
            if total > 0:
                percent = (current / total * 100)
                bar_length = 20
                filled = int(bar_length * current / total)
                bar = '█' * filled + '░' * (bar_length - filled)
                progress_line = f'{prefix} [{bar}] {percent:.1f}% {suffix}'
            else:
                progress_line = f'{prefix} [░░░░░░░░░░░░░░░░░░░░] 0.0% {suffix}'
            
            progress_line = progress_line.ljust(100)
            
            if finished:
                # Удаляем завершенный прогресс
                if transfer_id in self._progress_bars:
                    del self._progress_bars[transfer_id]
            else:
                # Обновляем или добавляем
                self._progress_bars[transfer_id] = progress_line
            
            # Перерисовываем все прогресс-бары
            self._redraw_progress_bars()
    
    def _redraw_progress_bars(self):
        """Перерисовка всех активных прогресс-баров с очисткой предыдущих"""
        # Очищаем предыдущие строки прогресса
        if self._progress_lines_count > 0:
            for _ in range(self._progress_lines_count):
                sys.stdout.write('\033[F')  # Вверх
                sys.stdout.write('\033[K')  # Очистить строку
            sys.stdout.flush()
        
        # Завершаем одиночный прогресс если есть
        if self._progress_line_active:
            sys.stdout.write('\n')
            sys.stdout.flush()
            self._progress_line_active = False
        
        # Выводим все активные прогресс-бары
        active_bars = list(self._progress_bars.values())
        self._progress_lines_count = len(active_bars)
        
        for bar in active_bars:
            sys.stdout.write(bar + '\n')
        
        sys.stdout.flush()
    
    def _redraw_progress_bars_no_clear(self):
        """Перерисовка прогресс-баров без очистки (когда они уже очищены)"""
        if self._progress_line_active:
            sys.stdout.write('\n')
            sys.stdout.flush()
            self._progress_line_active = False
        
        active_bars = list(self._progress_bars.values())
        self._progress_lines_count = len(active_bars)
        
        for bar in active_bars:
            sys.stdout.write(bar + '\n')
        
        sys.stdout.flush()
    
    def clear_all_progress(self):
        """Очистка всех прогресс-баров"""
        with self._lock:
            if self._progress_lines_count > 0:
                for _ in range(self._progress_lines_count):
                    sys.stdout.write('\033[F')
                    sys.stdout.write('\033[K')
                self._progress_lines_count = 0
                self._progress_bars.clear()
                sys.stdout.flush()
    
    def finish_progress(self):
        """Завершение строки прогресса (для обратной совместимости)"""
        with self._lock:
            if self._progress_line_active:
                sys.stdout.write('\n')
                sys.stdout.flush()
                self._progress_line_active = False
    
    def print_menu(self, menu_items):
        """
        Вывод меню с запоминанием количества строк
        
        Аргументы:
            menu_items: список строк меню
        """
        with self._lock:
            self._last_menu_lines = len(menu_items)
            for item in menu_items:
                print(item)
    
    def print_header(self, text):
        """Вывод заголовка"""
        with self._lock:
            width = len(text) + 4
            print('=' * width)
            print(f'| {text} |')
            print('=' * width)
    
    def print_separator(self, char='=', length=50):
        """Вывод разделителя"""
        with self._lock:
            print(char * length)
    
    def wait_for_key(self, message='Нажмите Enter для продолжения...'):
        """
        Ожидание нажатия клавиши
        
        Аргументы:
            message: сообщение перед ожиданием
        """
        with self._lock:
            # Очищаем прогресс-бары перед ожиданием
            self.clear_all_progress()
            print()
            print('-' * 40)
            try:
                input(message)
            except (KeyboardInterrupt, EOFError):
                pass


# Глобальный экземпляр
console = ConsoleManager()