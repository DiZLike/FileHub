"""
Протоколы обмена и константы
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

class TransferRoles:
    """Роли в передаче данных"""
    SENDER = b'S'      # Отправитель
    RECEIVER = b'R'    # Получатель

class StatusCodes:
    """Статусы ответов"""
    OK = 'ok'          # Успешно
    ERROR = 'error'    # Ошибка

class ShareTypes:
    """Типы раздач"""
    FILE = 'file'      # Файл
    FOLDER = 'folder'  # Папка

DEFAULT_CONFIG = """# Конфигурация FileHub
[server]
# Адрес для приёма подключений
host = 0.0.0.0
# Порт для управляющих команд
port = 5000
# Порт для передачи данных
data_port = 5001
# Максимум одновременных подключений
max_connections = 10
# Таймаут неактивного соединения (секунд)
connection_timeout = 300

[shares]
# Файл хранения раздач
storage_file = shares_data.json
# Файл хранения пользователей
users_file = users_data.json
# Интервал очистки неактивных раздач (часов)
cleanup_interval_hours = 1
# Время неактивности до удаления раздачи (дней)
inactive_days = 3
# Интервал автосохранения (минут)
save_interval_minutes = 5
# Максимальный размер файла (МБ, 0 - без ограничений)
max_file_size_mb = 0
# Максимум файлов в папке-раздаче
max_files_in_folder = 1000

[network]
# Размер буфера передачи (байт)
buffer_size = 8192
# Максимальный размер JSON (байт)
max_json_size = 1048576

[logging]
# Включить логирование
enabled = true
# Путь к файлу логов
log_file = hub.log
# Уровень логирования: DEBUG, INFO, WARNING, ERROR
log_level = INFO
# Логировать передачи файлов
log_transfers = true
# Максимальный размер лога (МБ)
max_log_size_mb = 10

[security]
# Только локальные подключения
local_only = false
# Разрешённые IP (через запятую)
allowed_ips = 
# Заблокированные IP (через запятую)
blocked_ips = 
# Максимум раздач на пользователя
max_shares_per_user = 50
# Запрещённые расширения (через запятую, например: .exe,.bat)
blocked_extensions = 
# Минимальная длина пароля
password_min_length = 4
# Требовать пароль
require_password = true
"""