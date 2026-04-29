"""
Протоколы обмена для клиента
"""

class MessageActions:
    """Действия в протоколе обмена"""
    LOGIN = 'login'              # Вход в систему
    LOGOUT = 'logout'            # Выход из системы
    SHARE_FILE = 'share_file'    # Поделиться файлом
    SHARE_FOLDER = 'share_folder' # Поделиться папкой
    LIST = 'list'                # Список всех раздач
    MY_SHARES = 'my_shares'      # Мои раздачи
    DOWNLOAD = 'download'        # Скачать раздачу
    REMOVE_SHARE = 'remove_share' # Удалить раздачу
    PING = 'ping'                # Пинг для поддержания активности
    STATS = 'stats'              # Статистика сервера
    UPLOAD_REQUEST = 'upload_request' # Запрос на отправку файла

class ShareTypes:
    """Типы раздач"""
    FILE = 'file'      # Файл
    FOLDER = 'folder'  # Папка

class StatusCodes:
    """Статусы ответов"""
    OK = 'ok'          # Успешно
    ERROR = 'error'    # Ошибка

# Максимальный размер JSON-сообщения (10 МБ)
MAX_JSON_SIZE = 10 * 1024 * 1024

# Размер буфера для передачи данных
BUFFER_SIZE = 65536

# Размер буфера для получения JSON
JSON_BUFFER_SIZE = 4096