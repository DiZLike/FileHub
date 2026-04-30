import ssl
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress

class EncryptionManager:
    """Менеджер TLS сервера"""
    
    def __init__(self, config, logger):
        self._config = config
        self._logger = logger
        self.enabled = config.security.tls_enabled
        self._ssl_context: Optional[ssl.SSLContext] = None
        
        if self.enabled:
            self._initialize()
    
    def _initialize(self):
        """Инициализация SSL контекста"""
        cert_dir = self._config.get('security', 'tls_cert_dir', 'certs')
        cert_file = os.path.join(cert_dir, 'server.crt')
        key_file = os.path.join(cert_dir, 'server.key')
        
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            self._generate_certificate(cert_file, key_file)
        
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            self._logger.log('ERROR', 'Не удалось создать TLS сертификаты')
            self.enabled = False
            return
        
        self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ssl_context.load_cert_chain(cert_file, key_file)
        self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
        self._ssl_context.options |= ssl.OP_NO_COMPRESSION
        
        self._logger.log('INFO', 'TLS контекст сервера инициализирован')
    
    def _generate_certificate(self, cert_file: str, key_file: str):
        """Генерация самоподписанного сертификата"""
        self._logger.log('INFO', 'Генерация самоподписанного TLS сертификата...')
        Path(os.path.dirname(cert_file)).mkdir(parents=True, exist_ok=True)
        
        private_key = rsa.generate_private_key(65537, 2048, default_backend())
        
        with open(key_file, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        host = self._config.get('server', 'host', '0.0.0.0')
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FileHub"),
            x509.NameAttribute(NameOID.COMMON_NAME, host),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName(host),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )
        
        with open(cert_file, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        self._logger.log('INFO', f'Сертификат создан: {cert_file}')
    
    def get_encryption_params(self) -> Optional[dict]:
        """Получение параметров шифрования для клиентов"""
        return {
            'enabled': True,
            'algorithm': 'TLSv1.2+',
            'key_exchange': 'tls_handshake'
        } if self.enabled else None
    
    def wrap_socket(self, socket, server_side=True):
        """Оборачивание сокета в TLS"""
        if not self.enabled or not self._ssl_context:
            return socket
        
        try:
            return self._ssl_context.wrap_socket(socket, server_side=server_side)
        except Exception as e:
            self._logger.log('ERROR', f'Ошибка TLS handshake: {e}')
            return None
    
    def get_stats(self) -> dict:
        """Получение статистики шифрования"""
        return {
            'enabled': self.enabled,
            'protocol': 'TLSv1.2+' if self.enabled else 'none',
            'certificates': 'self-signed' if self.enabled else 'none'
        }