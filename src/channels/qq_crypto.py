"""
QQ 开放平台 Webhook 签名处理模块。

提供 Ed25519 签名验证和回调地址验证（op=13）的签名功能。
"""

from __future__ import annotations

import binascii
from typing import Mapping

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey


def expand_secret_to_seed(bot_secret: str) -> bytes:
    """
    将机器人密钥扩展为 32 字节种子。

    QQ 开放平台要求使用 Ed25519 签名，但需要 32 字节种子。
    此函数通过循环拼接密钥直到达到 32 字节。

    Args:
        bot_secret: QQ 机器人密钥

    Returns:
        32 字节种子
    """
    encoded = bot_secret.encode("utf-8")
    seed = encoded
    while len(seed) < 32:
        seed = seed + seed
    return seed[:32]


def signing_key_from_secret(bot_secret: str) -> SigningKey:
    """
    从机器人密钥生成 Ed25519 签名密钥。

    Args:
        bot_secret: QQ 机器人密钥

    Returns:
        NaCl SigningKey 对象
    """
    return SigningKey(expand_secret_to_seed(bot_secret))


def sign_validation_response(bot_secret: str, event_ts: str, plain_token: str) -> str:
    """
    生成回调地址验证的响应签名（op=13）。

    Args:
        bot_secret: QQ 机器人密钥
        event_ts: 事件时间戳
        plain_token: 平台提供的随机字符串

    Returns:
        十六进制编码的签名
    """
    sk = signing_key_from_secret(bot_secret)
    message = event_ts.encode("utf-8") + plain_token.encode("utf-8")
    return sk.sign(message).signature.hex()


def verify_webhook_signature(
    bot_secret: str,
    headers: Mapping[str, str],
    raw_body: bytes,
) -> bool:
    """
    验证 Webhook 请求的 Ed25519 签名。

    Args:
        bot_secret: QQ 机器人密钥
        headers: HTTP 请求头（应包含 x-signature-ed25519 和 x-signature-timestamp）
        raw_body: 原始请求体字节

    Returns:
        签名是否有效
    """
    # 提取签名和时间戳（支持大小写不敏感）
    sig_hex = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519", "")
    timestamp = headers.get("x-signature-timestamp") or headers.get("X-Signature-Timestamp", "")

    if not sig_hex or not timestamp:
        return False

    # 解码签名
    try:
        signature = binascii.unhexlify(sig_hex.strip())
    except binascii.Error:
        return False

    if len(signature) != 64:
        return False

    # 构建验证消息：timestamp + body
    message = timestamp.encode("utf-8") + raw_body
    verify_key = signing_key_from_secret(bot_secret).verify_key

    try:
        verify_key.verify(message, signature)
        return True
    except BadSignatureError:
        return False


def normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """
    标准化 HTTP 请求头为小写。

    Args:
        headers: 原始请求头

    Returns:
        小写键名的请求头字典
    """
    return {str(k).lower(): str(v) for k, v in headers.items() if v is not None}
