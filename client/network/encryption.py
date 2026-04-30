import ssl

class ClientEncryption:
    """Менеджер TLS клиента"""
    
    def __init__(self):
        self.enabled = False
        self.algorithm = None
        self._ssl_context = None
    
    def enable(self, encryption_params: dict) -> bool:
        """Включение TLS с параметрами от сервера"""
        if encryption_params and encryption_params.get('enabled'):
            self.enabled = True
            self.algorithm = encryption_params.get('algorithm', 'TLSv1.2+')
            
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
            self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            
            return True
        return False
    
    def wrap_socket(self, sock):
        """Оборачивание сокета в TLS"""
        if not self.enabled or not self._ssl_context:
            return sock
        
        try:
            return self._ssl_context.wrap_socket(sock)
        except Exception as e:
            print(f'[ERROR] Ошибка TLS handshake: {e}')
            return None
    
    def is_enabled(self) -> bool:
        """Проверка, включён ли TLS"""
        return self.enabled