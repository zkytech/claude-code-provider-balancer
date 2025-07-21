
import asyncio
import os
import httpx
import logging
from typing import Dict, Any

# 使用项目中的日志工具
from log_utils import info, warning, error

import typing

# provider_manager 的类型提示，避免循环导入
if typing.TYPE_CHECKING:
    from provider_manager import ProviderManager

async def refresh_token(config: Dict[str, Any]) -> Dict[str, Any]:
    """使用 refresh token 获取新的 access token。"""
    try:
        client_id = os.environ[config["client_id_env"]]
        client_secret = os.environ[config["client_secret_env"]]
        refresh_token = os.environ[config["refresh_token_env"]]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            token_data = response.json()
            info(f"Successfully refreshed token for provider using client_id: {client_id[:5]}...")
            return token_data
            
    except httpx.HTTPStatusError as e:
        error(f"Failed to refresh token: {e.response.status_code} {e.response.text}")
    except KeyError as e:
        error(f"Missing environment variable: {e}")
    except Exception as e:
        error(f"An unexpected error occurred during token refresh: {e}")
    return {}

async def start_token_refresh_loop(provider_name: str, provider_config: Dict[str, Any], provider_manager: "ProviderManager"):
    """为单个 provider 启动一个无限的 token 刷新循环。"""
    info(f"Starting token refresh loop for provider: {provider_name}")
    while True:
        token_data = await refresh_token(provider_config["auto_refresh_config"])
        
        # 默认刷新间隔 (如果获取失败或响应中没有)
        sleep_duration = 3600  # 1 小时

        if token_data and "access_token" in token_data:
            new_access_token = token_data["access_token"]
            
            # 直接更新内存中的 provider Manager
            provider_manager.update_provider_auth(provider_name, new_access_token)
            
            # 从响应中获取过期时间，并设置一个缓冲
            # 例如，如果 token 50 分钟后过期，我们 45 分钟后就刷新
            if isinstance(token_data.get("expires_in"), int):
                sleep_duration = max(60, token_data["expires_in"] - 300) # 减去 5 分钟缓冲
        
        else:
            warning(f"Will retry refreshing token for {provider_name} in {sleep_duration / 60:.0f} minutes.")

        await asyncio.sleep(sleep_duration)
