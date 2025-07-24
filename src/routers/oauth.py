"""
OAuth-related API routes for Claude Code Provider Balancer.
"""

import time
from typing import Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from oauth import oauth_manager
from utils import LogRecord, info, error
from core.provider_manager import ProviderManager


def create_oauth_router(provider_manager: ProviderManager) -> APIRouter:
    """Create OAuth router with provider manager dependency."""
    router = APIRouter(prefix="/oauth", tags=["OAuth"])

    def _format_duration_for_response(seconds: float) -> str:
        """Format duration in human readable format for API responses"""
        if seconds <= 0:
            return "已过期"
        elif seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds/60)}分钟"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}小时{minutes}分钟"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            return f"{days}天{hours}小时"

    @router.get("/generate-url")
    async def generate_oauth_url():
        """
        Generate OAuth authorization URL for manual account setup.
        
        This endpoint allows users to manually initiate OAuth authorization
        without waiting for a 401 error. Useful for proactive account setup.
        """
        try:
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "OAuth manager not initialized"
                    }
                )
            
            # Generate OAuth login URL
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "OAuth manager not initialized. Please check server logs."
                    }
                )
            
            login_url = oauth_manager.generate_login_url()
            
            if not login_url:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Failed to generate OAuth URL"
                    }
                )
            
            # Return the URL with instructions
            return JSONResponse(content={
                "status": "success",
                "login_url": login_url,
                "instructions": {
                    "step_1": "Open the login_url in your browser",
                    "step_2": "Complete OAuth authorization in browser",
                    "step_3": "Copy the authorization code from callback URL",
                    "step_4": "Use POST /oauth/exchange-code with the authorization code and required account_email"
                },
                "callback_format": "https://console.anthropic.com/oauth/code/callback?code=YOUR_CODE&state=STATE",
                "exchange_example": "curl -X POST /oauth/exchange-code -d '{\"code\": \"YOUR_CODE\", \"account_email\": \"user@example.com\"}'",
                "expires_in_minutes": 10
            })
            
        except Exception as e:
            error(LogRecord(
                event="oauth_url_generation_error",
                message=f"Error generating OAuth URL: {str(e)}"
            ))
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Internal server error: {str(e)}"
                }
            )

    @router.post("/exchange-code")
    async def exchange_oauth_code(request: Request) -> JSONResponse:
        """Exchange OAuth authorization code for access tokens"""
        try:
            body = await request.json()
            authorization_code = body.get("code")
            account_email = body.get("account_email")  # Required email parameter
            
            if not authorization_code:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing authorization code"}
                )
            
            if not account_email:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing account_email parameter. Please provide your email address for account identification."}
                )
            
            # Exchange code for tokens (with required account email)
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={"error": "OAuth manager not initialized. Please check server logs."}
                )
            
            credentials = await oauth_manager.exchange_code(authorization_code, account_email)
            
            if credentials:
                # Start auto-refresh for the new token (if enabled)
                if provider_manager and provider_manager.oauth_auto_refresh_enabled:
                    await oauth_manager.start_auto_refresh()
                else:
                    info(LogRecord(
                        event="oauth_auto_refresh_disabled",
                        message="Auto-refresh disabled - new token will not be auto-refreshed"
                    ))
                
                # Build response with account information
                response_data = {
                    "status": "success",
                    "message": "Authorization successful", 
                    "account_email": credentials.account_email,  # Use email as primary identifier
                    "expires_at": credentials.expires_at,
                    "scopes": credentials.scopes
                }
                
                # Add account name if available
                if credentials.account_name:
                    response_data["account_name"] = credentials.account_name
                
                return JSONResponse(content=response_data)
            else:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Failed to exchange authorization code"}
                )
        
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"OAuth exchange failed: {str(e)}"}
            )

    @router.get("/status")
    async def get_oauth_status() -> JSONResponse:
        """Get comprehensive status of stored OAuth tokens and system state"""
        try:
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={"error": "OAuth manager not initialized. Please check server logs."}
                )
            
            tokens_status = oauth_manager.get_tokens_status()
            
            # Calculate summary statistics
            total_tokens = len(tokens_status)
            healthy_tokens = sum(1 for token in tokens_status if token.get("is_healthy", False))
            expired_tokens = sum(1 for token in tokens_status if token.get("is_expired", False))
            expiring_soon = sum(1 for token in tokens_status if token.get("will_expire_soon", False))
            
            # Get current time for reference
            current_time = int(time.time())
            
            # Find currently active token
            active_token = next((token for token in tokens_status if token.get("is_current", False)), None)
            
            # System info
            system_info = {
                "oauth_manager_status": "active",
                "current_time": current_time,
                "current_time_iso": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time)),
                "timezone": "Local",
            }
            
            # Summary
            summary = {
                "total_tokens": total_tokens,
                "healthy_tokens": healthy_tokens,
                "expired_tokens": expired_tokens,
                "expiring_soon": expiring_soon,
                "current_token_index": oauth_manager.current_token_index if (oauth_manager and total_tokens > 0) else None,
                "rotation_enabled": total_tokens > 1,
            }
            
            # Active token info (safe)
            active_info = None
            if active_token:
                active_info = {
                    "account_email": active_token["account_email"],
                    "expires_in_human": active_token["expires_in_human"],
                    "is_healthy": active_token["is_healthy"],
                    "scopes": active_token["scopes"]
                }
            
            return JSONResponse(content={
                "system": system_info,
                "summary": summary,
                "active_token": active_info,
                "tokens": tokens_status
            })
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get OAuth status: {str(e)}"}
            )

    @router.delete("/tokens/{account_email}")
    async def remove_oauth_token(account_email: str) -> JSONResponse:
        """Remove a specific OAuth token"""
        try:
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={"error": "OAuth manager not initialized. Please check server logs."}
                )
            
            success = oauth_manager.remove_token(account_email)
            if success:
                return JSONResponse(content={
                    "status": "success",
                    "message": f"Token for {account_email} removed"
                })
            else:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Token for {account_email} not found"}
                )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to remove token: {str(e)}"}
            )

    @router.post("/refresh/{account_email}")
    async def refresh_oauth_token(account_email: str) -> JSONResponse:
        """Manually refresh OAuth token for a specific account"""
        try:
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={"error": "OAuth manager not initialized. Please check server logs."}
                )
            
            # Refresh the token for the specified account
            refreshed_credentials, error_details = await oauth_manager.refresh_token_by_email(account_email)
            
            if not refreshed_credentials:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Token not found or refresh failed for account: {account_email}",
                        "details": error_details or "Account may not exist, or refresh token may be invalid/expired"
                    }
                )
            
            # Calculate token expiry information
            current_time = time.time()
            expires_in_seconds = max(0, refreshed_credentials.expires_at - current_time)
            expires_in_minutes = round(expires_in_seconds / 60, 1)
            
            return JSONResponse(content={
                "status": "success",
                "message": f"Token refreshed successfully for account: {account_email}",
                "account_email": refreshed_credentials.account_email,
                "account_id": refreshed_credentials.account_id,
                "expires_at": refreshed_credentials.expires_at,
                "expires_in_seconds": int(expires_in_seconds),
                "expires_in_minutes": expires_in_minutes,
                "expires_in_human": _format_duration_for_response(expires_in_seconds),
                "access_token_preview": f"{refreshed_credentials.access_token[:8]}...{refreshed_credentials.access_token[-4:]}" if refreshed_credentials.access_token else None,
                "scopes": refreshed_credentials.scopes,
                "refreshed_at": int(time.time())
            })
            
        except Exception as e:
            error(LogRecord(
                event="oauth_manual_refresh_error",
                message=f"Error during manual token refresh for {account_email}: {str(e)}"
            ))
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to refresh token: {str(e)}"}
            )

    @router.delete("/tokens")
    async def clear_all_oauth_tokens() -> JSONResponse:
        """Clear all stored OAuth tokens"""
        try:
            if not oauth_manager:
                return JSONResponse(
                    status_code=500,
                    content={"error": "OAuth manager not initialized. Please check server logs."}
                )
            
            oauth_manager.clear_all_tokens()
            return JSONResponse(content={
                "status": "success",
                "message": "All tokens cleared"
            })
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to clear tokens: {str(e)}"}
            )

    return router