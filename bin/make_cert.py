import os
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta, timezone

def generate_self_signed_cert(cert_path="cert.pem", key_path="key.pem"):
    print(f"正在生成自签名证书...")

    # 检查文件是否已存在
    if os.path.exists(cert_path) or os.path.exists(key_path):
        print(f"⚠️ 证书文件已存在: {cert_path} / {key_path}")
        overwrite = input("是否覆盖？(y/N): ").strip().lower()
        if overwrite != 'y':
            print("已取消生成")
            return

    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    except Exception as e:
        print(f"❌ 生成私钥失败: {e}")
        return

    # 使用时区感知的时间，修复警告
    now = datetime.now(timezone.utc)

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"localhost")])
    try:
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            now
        ).not_valid_after(
            now + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(u"localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
            ]),
            critical=False,
        ).sign(key, hashes.SHA256())
    except Exception as e:
        print(f"❌ 生成证书失败: {e}")
        return

    try:
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        print(f"✅ 证书已生成: {cert_path}, {key_path}")
    except (FileNotFoundError, PermissionError) as e:
        print(f"❌ 写入证书文件失败: {e}")
    except Exception as e:
        print(f"❌ 写入证书文件时发生未知错误: {e}")

if __name__ == "__main__":
    generate_self_signed_cert()