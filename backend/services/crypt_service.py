import json
import hashlib
import os
from base64 import b64decode, b64encode
from Crypto.Cipher import AES
from typing import Union, Tuple, Any


def openssl_bytes_to_key(password: bytes, salt: bytes, key_len: int, iv_len: int) -> Tuple[bytes, bytes]:
    """
    Derives key and IV from password and salt, replicating OpenSSL's EVP_BytesToKey (MD5-based).

    Args:
        password (bytes): The password to derive the key from.
        salt (bytes): The salt used for derivation.
        key_len (int): Desired key length in bytes.
        iv_len (int): Desired IV length in bytes.

    Returns:
        Tuple[bytes, bytes]: A tuple containing the key and IV.
    """
    dtot = b""
    d = b""
    while len(dtot) < (key_len + iv_len):
        d = hashlib.md5(d + password + salt).digest()
        dtot += d
    return dtot[:key_len], dtot[key_len:key_len + iv_len]


def decrypt_data(ciphertext: str, password: str) -> Union[str, Any]:
    """
    Decrypts an AES-256-CBC encrypted string (OpenSSL-compatible with Salted__ header).

    Args:
        ciphertext (str): Base64-encoded encrypted data.
        password (str): Password used for encryption.

    Returns:
        Union[str, Any]: Decrypted string or JSON-decoded object.
    
    Raises:
        ValueError: If ciphertext format or padding is invalid.
    """
    raw = b64decode(ciphertext)

    if not raw.startswith(b"Salted__"):
        raise ValueError("Invalid ciphertext format. Missing 'Salted__' header.")

    salt = raw[8:16]
    encrypted = raw[16:]

    key, iv = openssl_bytes_to_key(password.encode(), salt, 32, 16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted)

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if pad_len < 1 or pad_len > AES.block_size:
        raise ValueError("Invalid PKCS7 padding")
    decrypted = decrypted[:-pad_len]

    text = decrypted.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def encrypt_data(data: Union[str, dict, list], password: str) -> str:
    """
    Encrypts data using AES-256-CBC (OpenSSL compatible with Salted__ header) and returns Base64 string.

    Args:
        data (Union[str, dict, list]): Data to encrypt (string or JSON-serializable object).
        password (str): Password for encryption.

    Returns:
        str: Base64-encoded encrypted string.
    """
    # Convert object to JSON string
    if not isinstance(data, str):
        data = json.dumps(data)

    data_bytes = data.encode("utf-8")

    # PKCS7 padding
    pad_len = AES.block_size - (len(data_bytes) % AES.block_size)
    data_bytes += bytes([pad_len]) * pad_len

    # Generate random 8-byte salt
    salt = os.urandom(8)

    # Derive key and IV
    key, iv = openssl_bytes_to_key(password.encode(), salt, 32, 16)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(data_bytes)

    # Prepend OpenSSL Salted__ header
    openssl_blob = b"Salted__" + salt + encrypted
    return b64encode(openssl_blob).decode("utf-8")
