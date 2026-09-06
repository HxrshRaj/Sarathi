"""Print a fresh Fernet key for ENCRYPTION_KEY.  `python -m app.scripts.gen_key`"""

from app.security.crypto import generate_key

if __name__ == "__main__":
    print(generate_key())
