"""QQ 机器人消息处理器：处理 Webhook 事件、消息收发、访问令牌管理。"""

import asyncio
import json
import re
import time
from collections import OrderedDict
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from src.channels.qq_crypto import (
    normalize_headers,
    sign_validation_response,
    signing_key_from_secret,
    verify_webhook_signature,
)
from src.core.agent import agent
from src.core.config import settings
from src.core.logger import logger

# 常量配置
MAX_PROCESSED_EVENTS = 1000  # 事件去重队列最大长度
MAX_SEND_RETRIES = 2  # 消息发送重试次数
REQUEST_TIMEOUT = 30.0  # HTTP 请求超时时间
TOKEN_REFRESH_MARGIN = 60  # 令牌提前刷新时间（秒）
QQ_MSG_MAX_LEN = 3800  # QQ 消息最大长度


def _strip_mentions(text: str) -> str:
    """去除消息中的 @ 提及标记。"""
    if not text:
        return ""
    return re.sub(r"<@[^>]+>\s*", "", text).strip()


class QQAccessToken:
    """QQ 机器人访问令牌管理器，支持自动缓存和刷新。"""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    async def get(self, app_id: str, secret: str) -> str:
        """获取有效的访问令牌，必要时自动刷新。"""
        now = time.time()
        if self._token and now < self._expires_at - TOKEN_REFRESH_MARGIN:
            return self._token

        url = "https://bots.qq.com/app/getAppAccessToken"
        payload = {"appId": str(app_id), "clientSecret": str(secret)}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("获取 QQ 访问令牌失败: HTTP %s - %s", e.response.status_code, e.response.text)
            raise HTTPException(status_code=502, detail=f"QQ token request failed: HTTP {e.response.status_code}")
        except Exception:
            logger.exception("获取 QQ 访问令牌时发生异常")
            raise HTTPException(status_code=502, detail="QQ token request failed")

        self._token = data.get("access_token")
        expires_in = data.get("expires_in", 7200)

        try:
            self._expires_at = now + float(expires_in)
        except (TypeError, ValueError):
            self._expires_at = now + 7200  # 默认 2 小时

        logger.info("QQ 访问令牌已刷新，有效期 %.0f 秒", expires_in)
        return self._token


class QQBotHandler:
    """QQ 机器人 Webhook 事件处理器。"""

    def __init__(self) -> None:
        self._token_cache = QQAccessToken()
        # LRU 缓存：防止内存无限增长
        self._processed_events: OrderedDict[str, None] = OrderedDict()

        # 加载配置
        qq_config = settings.get("qq", {})
        self._sandbox = bool(qq_config.get("sandbox", False))
        self._verify_sig = bool(qq_config.get("verify_signature", True))
        self._app_id = str(qq_config.get("app_id") or qq_config.get("bot_id") or "")
        self._secret = str(qq_config.get("client_secret") or qq_config.get("secret") or "")

        # API 基础 URL
        self._base_url = (
            "https://sandbox.api.sgroup.qq.com" if self._sandbox else "https://api.sgroup.qq.com"
        )

        if not self._app_id or not self._secret:
            logger.warning("QQ 机器人配置不完整，请检查 config.yaml 中的 qq.app_id 和 qq.client_secret")

    def _is_duplicate(self, event_id: str) -> bool:
        """检查事件是否已处理，使用 LRU 缓存。"""
        if event_id in self._processed_events:
            return True
        self._processed_events[event_id] = None
        if len(self._processed_events) > MAX_PROCESSED_EVENTS:
            self._processed_events.popitem(last=False)
        return False

    def _api_headers(self, token: str) -> dict[str, str]:
        """生成 API 请求头。"""
        return {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def handle_webhook(self, headers: dict[str, str], raw_body: bytes) -> dict[str, Any]:
        """
        处理 QQ Webhook 请求。

        Args:
            headers: HTTP 请求头
            raw_body: 原始请求体

        Returns:
            响应字典

        Raises:
            HTTPException: 签名验证失败或请求格式错误
        """
        normalized = normalize_headers(headers)

        # 签名验证
        if self._verify_sig and self._secret:
            if not verify_webhook_signature(self._secret, normalized, raw_body):
                logger.warning("QQ Webhook 签名验证失败")
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # App ID 校验
        expected_app = normalized.get("x-bot-appid")
        if self._app_id and expected_app and expected_app != self._app_id:
            logger.warning("QQ Webhook App ID 不匹配: 期望 %s, 实际 %s", self._app_id, expected_app)
            raise HTTPException(status_code=403, detail="X-Bot-Appid mismatch")

        # 解析请求体
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error("QQ Webhook 请求体解析失败: %s", e)
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        op = payload.get("op")

        # 回调地址验证 (op=13)
        if op == 13:
            return self._handle_validation(payload)

        # 普通事件推送 (op=0)
        if op == 0:
            event_id = payload.get("id")
            if event_id:
                if self._is_duplicate(event_id):
                    logger.debug("QQ 重复事件，跳过: %s", event_id)
                    return {"op": 12}

            event_type = payload.get("t", "")
            event_data = payload.get("d", {})

            # 异步处理事件，立即返回
            asyncio.create_task(self._dispatch_event(event_type, event_data, payload))
            return {"op": 12}

        # 未知操作码
        logger.warning("QQ Webhook 收到未知操作码: op=%s", op)
        return {"op": 12}

    def _handle_validation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """处理回调地址验证请求 (op=13)。"""
        data = payload.get("d", {})
        plain_token = data.get("plain_token", "")
        event_ts = str(data.get("event_ts", ""))

        if not plain_token or not event_ts or not self._secret:
            logger.warning("QQ 回调验证参数不完整")
            return {"plain_token": plain_token, "signature": ""}

        signature = sign_validation_response(self._secret, event_ts, plain_token)
        logger.info("QQ 回调地址验证已响应")
        return {"plain_token": plain_token, "signature": signature}

    async def _dispatch_event(self, event_type: str, data: dict[str, Any], envelope: dict[str, Any]) -> None:
        """分发并处理事件。"""
        try:
            handlers = {
                "C2C_MESSAGE_CREATE": self._on_c2c,
                "GROUP_AT_MESSAGE_CREATE": self._on_group,
                "AT_MESSAGE_CREATE": self._on_guild,
            }

            handler = handlers.get(event_type)
            if handler:
                await handler(data)
            else:
                logger.debug("QQ 未处理的事件类型: %s", event_type)

        except Exception:
            logger.exception("QQ 事件处理异常 (%s)", event_type)

    async def _on_c2c(self, data: dict[str, Any]) -> None:
        """处理私聊消息。"""
        author = data.get("author", {})
        user_id = author.get("user_openid")
        content = _strip_mentions(data.get("content", ""))
        msg_id = data.get("id")

        if not content or not user_id:
            return

        chat_id = f"qq:c2c:{user_id}"
        logger.info("QQ 私聊消息: %s", content[:80])

        reply = await agent.get_response(chat_id, content)
        await self._send_message("c2c", user_id, reply, msg_id)

    async def _on_group(self, data: dict[str, Any]) -> None:
        """处理群聊 @ 消息。"""
        group_id = data.get("group_openid")
        content = _strip_mentions(data.get("content", ""))
        msg_id = data.get("id")

        if not content or not group_id:
            return

        chat_id = f"qq:group:{group_id}"
        logger.info("QQ 群聊消息: %s", content[:80])

        reply = await agent.get_response(chat_id, content)
        await self._send_message("group", group_id, reply, msg_id)

    async def _on_guild(self, data: dict[str, Any]) -> None:
        """处理频道 @ 消息。"""
        channel_id = data.get("channel_id")
        guild_id = data.get("guild_id")
        content = _strip_mentions(data.get("content", ""))
        msg_id = data.get("id")

        if not content or not channel_id:
            return

        chat_id = f"qq:guild:{guild_id}:{channel_id}"
        logger.info("QQ 频道消息: %s", content[:80])

        reply = await agent.get_response(chat_id, content)
        await self._send_message("guild", channel_id, reply, msg_id)

    async def _send_message(
        self,
        msg_type: str,
        target_id: str,
        text: str,
        reply_msg_id: Optional[str] = None,
    ) -> bool:
        """
        发送消息到指定目标。

        Args:
            msg_type: 消息类型 (c2c/group/guild)
            target_id: 目标 ID (用户/群/频道)
            text: 消息内容
            reply_msg_id: 回复的消息 ID

        Returns:
            是否发送成功
        """
        # 构建 URL
        endpoints = {
            "c2c": f"{self._base_url}/v2/users/{target_id}/messages",
            "group": f"{self._base_url}/v2/groups/{target_id}/messages",
            "guild": f"{self._base_url}/channels/{target_id}/messages",
        }
        url = endpoints.get(msg_type)
        if not url:
            logger.error("QQ 未知消息类型: %s", msg_type)
            return False

        # 构建请求体
        body: dict[str, Any] = {
            "content": self._truncate(text),
            "msg_type": 0,
        }
        if msg_type == "guild":
            del body["msg_type"]  # 频道消息不需要 msg_type
        if reply_msg_id:
            body["msg_id"] = reply_msg_id

        # 获取访问令牌
        try:
            token = await self._token_cache.get(self._app_id, self._secret)
        except HTTPException:
            return False

        # 发送消息（带重试）
        for attempt in range(MAX_SEND_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    resp = await client.post(url, headers=self._api_headers(token), json=body)
                    resp.raise_for_status()
                    logger.info("QQ %s 消息已发送", msg_type)
                    return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Token 可能已过期，强制刷新并重试
                    logger.warning("QQ %s 发送失败 (401)，尝试刷新令牌", msg_type)
                    try:
                        token = await self._token_cache.get(self._app_id, self._secret)
                        continue
                    except HTTPException:
                        return False
                if attempt < MAX_SEND_RETRIES:
                    wait_time = 0.5 * (attempt + 1)
                    logger.warning("QQ %s 发送失败 (HTTP %s)，%s 秒后重试: %s",
                                   msg_type, e.response.status_code, wait_time, e.response.text[:100])
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("QQ %s 发送失败，已重试%d次: HTTP %s - %s",
                                 msg_type, MAX_SEND_RETRIES, e.response.status_code, e.response.text)
            except Exception:
                if attempt < MAX_SEND_RETRIES:
                    wait_time = 0.5 * (attempt + 1)
                    logger.exception("QQ %s 发送异常，%s 秒后重试", msg_type, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    logger.exception("QQ %s 发送失败，已重试%d次", msg_type, MAX_SEND_RETRIES)

        return False

    @staticmethod
    def _truncate(text: str, max_len: int = QQ_MSG_MAX_LEN) -> str:
        """截断过长的消息。"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 20] + "\n...(消息已截断)"
