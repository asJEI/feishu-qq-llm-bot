"""Feishu + QQ Bot 主入口模块。

提供 FastAPI 应用和 Webhook 接收端点。
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，支持直接执行 `python src/main.py`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi import FastAPI, Request

from src.channels.feishu_handler import FeishuHandler
from src.channels.qq_handler import QQBotHandler
from src.core.config import settings
from src.core.logger import logger

# 创建 FastAPI 应用
app = FastAPI(title="Feishu + QQ Bot", version="1.0.0")

# 初始化处理器
feishu_handler = FeishuHandler()
qq_handler = QQBotHandler()


@app.get("/")
async def index():
    """健康检查端点。"""
    return {
        "status": "running",
        "service": "Feishu + QQ Bot",
        "version": "1.0.0",
    }


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    """
    飞书 Webhook 接收端点。

    处理飞书开放平台的事件推送，包括：
    - URL 验证（首次配置时使用）
    - 消息接收事件
    """
    # 解析请求体
    try:
        data = await request.json()
    except Exception as e:
        logger.error("[Feishu] 解析 JSON 失败: %s", e)
        return {"code": 1, "msg": "Invalid JSON"}

    # 调试模式：打印请求内容
    if settings.get("server.debug"):
        logger.info("[Feishu] 收到回调: %s", json.dumps(data, ensure_ascii=False))

    # URL 验证
    if data.get("type") == "url_verification":
        logger.info("[Feishu] URL 验证请求")
        return {"challenge": data.get("challenge")}

    # 处理事件
    try:
        result = await feishu_handler.handle_event(data)
        return result
    except Exception:
        logger.exception("[Feishu] 处理事件失败")
        return {"code": 1, "msg": "Internal error"}


@app.post("/webhook/qq")
async def qq_webhook(request: Request):
    """
    QQ 机器人 Webhook 接收端点。

    处理 QQ 开放平台的事件推送，包括：
    - 回调地址验证（op=13）
    - 消息推送事件（op=0）
    """
    # 读取原始请求体
    try:
        raw_body = await request.body()
        headers = dict(request.headers)
    except Exception as e:
        logger.error("[QQ] 读取请求失败: %s", e)
        return {"op": 12}

    # 调试模式：打印请求内容
    if settings.get("server.debug"):
        try:
            body_text = raw_body.decode("utf-8")
            logger.info("[QQ] 收到回调: %s", body_text[:500])
        except Exception:
            pass

    # 处理 Webhook
    try:
        result = await qq_handler.handle_webhook(headers, raw_body)
        return result
    except Exception:
        logger.exception("[QQ] 处理 Webhook 失败")
        return {"op": 12}


if __name__ == "__main__":
    # 获取配置
    port = int(settings.get("server.port", 8080))
    debug = settings.get("server.debug", False)

    logger.info("=" * 50)
    logger.info("服务启动中...")
    logger.info("监听地址: 0.0.0.0:%s", port)
    logger.info("调试模式: %s", "开启" if debug else "关闭")
    logger.info("飞书 Webhook: POST /webhook/feishu")
    logger.info("QQ Webhook: POST /webhook/qq")
    logger.info("健康检查: GET /")
    logger.info("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=port)
