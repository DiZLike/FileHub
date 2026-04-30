import os
import sys
import threading
import datetime

class ConsoleManager:
    """Менеджер консольного вывода"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._progress_line_active = False
        self._last_menu_lines = 0
        self._is_windows = os.name == 'nt'
        self._progress_bars = {}
        self._progress_lines_count = 0
    
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
    
    def print_system_message(self, message: str, level: str = 'info'):
        """Вывод системного сообщения"""
        with self._lock:
            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
            
            active_bars = dict(self._progress_bars)
            
            if self._progress_lines_count > 0:
                for _ in range(self._progress_lines_count):
                    sys.stdout.write('\033[F')
                    sys.stdout.write('\033[K')
                self._progress_lines_count = 0
            
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
            
            print(f'{prefix} {message}')
            self._last_menu_lines = 0
            
            if active_bars:
                self._progress_bars = active_bars
                self._redraw_progress_bars_no_clear()
    
    def print_progress(self, current: int, total: int, prefix: str = '', suffix: str = ''):
        """Обновляемый прогресс-бар"""
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
    
    def update_multi_progress(self, transfer_id: str, current: int, total: int,
                              prefix: str = '', suffix: str = '', finished: bool = False):
        """Обновление прогресс-бара для трансфера"""
        with self._lock:
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
                self._progress_bars.pop(transfer_id, None)
            else:
                self._progress_bars[transfer_id] = progress_line
            
            self._redraw_progress_bars()
    
    def _redraw_progress_bars(self):
        """Перерисовка всех прогресс-баров"""
        if self._progress_lines_count > 0:
            for _ in range(self._progress_lines_count):
                sys.stdout.write('\033[F')
                sys.stdout.write('\033[K')
            sys.stdout.flush()
        
        if self._progress_line_active:
            sys.stdout.write('\n')
            sys.stdout.flush()
            self._progress_line_active = False
        
        active_bars = list(self._progress_bars.values())
        self._progress_lines_count = len(active_bars)
        
        for bar in active_bars:
            sys.stdout.write(bar + '\n')
        
        sys.stdout.flush()
    
    def _redraw_progress_bars_no_clear(self):
        """Перерисовка прогресс-баров без очистки"""
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
        """Завершение строки прогресса"""
        with self._lock:
            if self._progress_line_active:
                sys.stdout.write('\n')
                sys.stdout.flush()
                self._progress_line_active = False
    
    def print_menu(self, menu_items: list):
        """Вывод меню"""
        with self._lock:
            self._last_menu_lines = len(menu_items)
            for item in menu_items:
                print(item)
    
    def print_header(self, text: str):
        """Вывод заголовка"""
        with self._lock:
            width = len(text) + 4
            print('=' * width)
            print(f'| {text} |')
            print('=' * width)
    
    def print_separator(self, char: str = '=', length: int = 50):
        """Вывод разделителя"""
        with self._lock:
            print(char * length)
    
    def wait_for_key(self, message: str = 'Нажмите Enter для продолжения...'):
        """Ожидание нажатия клавиши"""
        with self._lock:
            self.clear_all_progress()
            print()
            print('-' * 40)
            try:
                input(message)
            except (KeyboardInterrupt, EOFError):
                pass


console = ConsoleManager()