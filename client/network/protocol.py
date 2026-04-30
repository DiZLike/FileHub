class MessageActions:
    """Действия в протоколе обмена"""
    HELLO = 'hello'
    LOGIN = 'login'
    LOGOUT = 'logout'
    SHARE_FILE = 'share_file'
    SHARE_FOLDER = 'share_folder'
    LIST = 'list'
    MY_SHARES = 'my_shares'
    DOWNLOAD = 'download'
    REMOVE_SHARE = 'remove_share'
    PING = 'ping'
    STATS = 'stats'
    UPLOAD_REQUEST = 'upload_request'

class ShareTypes:
    """Типы раздач"""
    FILE = 'file'
    FOLDER = 'folder'

class StatusCodes:
    """Статусы ответов"""
    OK = 'ok'
    ERROR = 'error'

MAX_JSON_SIZE = 10 * 1024 * 1024
BUFFER_SIZE = 65536
JSON_BUFFER_SIZE = 4096