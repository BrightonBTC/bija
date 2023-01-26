from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

salt = b"\x00\xe9\xb9\x7f\xf3+\x8c\x97\x97T\x9a\xbc(m\xef\x1e\xda\n\x11lH'\x00"


def encrypt_key(password, to_encrypt):
    to_encrypt = to_encrypt.encode()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    _key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

    f = Fernet(_key)
    encrypted_string = f.encrypt(to_encrypt)
    return encrypted_string.decode()


def decrypt_key(password, to_decrypt):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    _key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

    f = Fernet(_key)
    try:
        pw = f.decrypt(to_decrypt)
        return pw.decode()
    except InvalidToken:
        return False
