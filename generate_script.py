# scripts/generate_keys.py
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_rsa_keys():
    # private key 생성 (2048비트)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # private key 저장 (Django 서버만 보관)
    with open("private_key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # public key 저장 (FastAPI에 배포)
    with open("public_key.pem", "wb") as f:
        f.write(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    print("✅ private_key.pem → Django 서버 보관")
    print("✅ public_key.pem  → FastAPI 서버에 배포")

if __name__ == "__main__":
    generate_rsa_keys()