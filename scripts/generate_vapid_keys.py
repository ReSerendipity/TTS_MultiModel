#!/usr/bin/env python3
"""VAPID 密钥对生成工具（Phase 3 — PWA 推送通知）。

生成 EC P-256 密钥对，用于 Web Push API 的 VAPID (Voluntary Application
Server Identification) 协议。将公钥填入 config.yaml 的 pwa.vapid_public_key
字段，私钥填入 pwa.vapid_private_key 字段。

用法:
    python scripts/generate_vapid_keys.py

输出:
    - VAPID 公钥（Base64URL，无 padding）— 浏览器 PushManager.subscribe() 使用
    - VAPID 私钥（PEM 格式）— 后端 pywebpush 签名 JWT 使用

技术细节:
    - 曲线: SECP256R1 (NIST P-256 / prime256v1)
    - 公钥编码: X962 UncompressedPoint (65 字节: 0x04 + X[32] + Y[32])
    - 公钥输出: Base64URL encode 后去除 '=' padding
    - 私钥编码: PKCS#8 PEM (无密码加密)
    - VAPID subject: 建议填 mailto: 或 https:// URL

Refs:
    - RFC 8292: VAPID Identification
    - RFC 8291: Message Encryption for WebPush
    - https://developers.google.com/web/fundamentals/push-notifications/web-push-protocol
"""

from __future__ import annotations

import base64
import sys

# 确保能导入 cryptography（已在 requirements.txt 中）
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    print("ERROR: cryptography library not found. Run: pip install cryptography", file=sys.stderr)
    sys.exit(1)


def generate_vapid_keypair() -> tuple[str, str]:
    """生成 VAPID EC P-256 密钥对。

    Returns:
        (public_key_b64url, private_key_pem) 二元组：
        - public_key_b64url: Base64URL 编码的未压缩公钥点（65 字节），无 '=' padding
        - private_key_pem: PKCS#8 PEM 格式私钥字符串
    """
    private_key = ec.generate_private_key(ec.SECP256R1())

    # 公钥：X962 未压缩点格式（65 字节）
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key_b64url = base64.urlsafe_b64encode(public_key_bytes).decode("ascii").rstrip("=")

    # 私钥：PKCS#8 PEM 格式（无加密）
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return public_key_b64url, private_pem.decode("ascii")


def main() -> None:
    """命令行入口：生成密钥对并输出到 stdout。"""
    print("=" * 70)
    print("VAPID Key Pair Generator for TTS MultiModel PWA Push Notifications")
    print("=" * 70)
    print()

    public_key, private_key_pem = generate_vapid_keypair()

    print("1. VAPID Public Key (Base64URL, no padding)")
    print("   -> Fill into config.yaml: pwa.vapid_public_key")
    print()
    print(f"   {public_key}")
    print()

    print("2. VAPID Private Key (PEM format)")
    print("   -> Fill into config.yaml: pwa.vapid_private_key")
    print("   (Use a YAML multiline string | or >)")
    print()
    for line in private_key_pem.strip().splitlines():
        print(f"   {line}")
    print()

    print("3. VAPID Subject (recommended)")
    print("   -> Fill into config.yaml: pwa.vapid_subject")
    print("   Example: mailto:admin@example.com")
    print()

    print("=" * 70)
    print("config.yaml snippet:")
    print("=" * 70)
    print("pwa:")
    print(f'  vapid_public_key: "{public_key}"')
    print("  vapid_private_key: |")
    for line in private_key_pem.strip().splitlines():
        print(f"    {line}")
    print('  vapid_subject: "mailto:admin@example.com"')
    print()

    # 安全提示
    print("[WARNING] SECURITY: Keep the private key secret! Do not commit to public repos.")
    print("   The private key allows sending push messages to all subscribers.")


if __name__ == "__main__":
    main()
