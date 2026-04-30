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

class TransferRoles:
    """Роли в передаче данных"""
    SENDER = b'S'
    RECEIVER = b'R'

class StatusCodes:
    """Статусы ответов"""
    OK = 'ok'
    ERROR = 'error'

class ShareTypes:
    """Типы раздач"""
    FILE = 'file'
    FOLDER = 'folder'