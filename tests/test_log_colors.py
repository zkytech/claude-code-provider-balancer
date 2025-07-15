#!/usr/bin/env python3
"""
测试脚本：验证日志颜色功能
"""

import sys
import os
sys.path.append('src')

from main import LogRecord, LogEvent, debug, info, warning, error, critical

def test_log_colors():
    """测试不同级别的日志颜色输出"""
    
    print("=== 测试日志颜色功能 ===")
    print("注意：只有在终端(TTY)环境下才会显示颜色\n")
    
    # 测试 DEBUG 级别 (青色)
    debug(LogRecord(
        event=LogEvent.HEALTH_CHECK.value,
        message="这是一条 DEBUG 级别的日志消息",
        data={"test": "debug_data"}
    ))
    
    # 测试 INFO 级别 (绿色) 
    info(LogRecord(
        event=LogEvent.REQUEST_START.value,
        message="这是一条 INFO 级别的日志消息",
        request_id="test-req-001",
        data={"provider": "test_provider"}
    ))
    
    # 测试 WARNING 级别 (黄色)
    warning(LogRecord(
        event=LogEvent.PARAMETER_UNSUPPORTED.value,
        message="这是一条 WARNING 级别的日志消息",
        data={"unsupported_param": "test_param"}
    ))
    
    # 测试 ERROR 级别 (红色)
    try:
        raise ValueError("这是一个测试异常")
    except Exception as e:
        error(LogRecord(
            event=LogEvent.REQUEST_FAILURE.value,
            message="这是一条 ERROR 级别的日志消息",
            request_id="test-req-002"
        ), exc=e)
    
    # 测试 CRITICAL 级别 (洋红色)
    critical(LogRecord(
        event=LogEvent.REQUEST_FAILURE.value,
        message="这是一条 CRITICAL 级别的日志消息",
        data={"critical_error": True}
    ))
    
    print("\n=== 测试完成 ===")
    print("如果您看到了不同颜色的日志输出，说明颜色功能正常工作！")
    print("如果没有颜色，可能的原因：")
    print("1. 不在 TTY 终端环境中（如管道输出或重定向）")
    print("2. log_color 配置被设置为 false")
    print("3. 终端不支持 ANSI 颜色代码")

if __name__ == "__main__":
    test_log_colors()