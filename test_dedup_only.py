#!/usr/bin/env python3
"""
简单测试：验证删除响应缓存后，只保留去重功能
"""

import requests
import time
import threading
import json

BASE_URL = "http://localhost:8080"

def test_deduplication_only():
    """测试去重功能（不包含响应缓存）"""
    payload = {
        "model": "claude-3-5-haiku-20241022",
        "messages": [{"role": "user", "content": "测试去重: 什么是Python？"}],
        "max_tokens": 50,
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print("=== 测试1: 并发去重测试 ===")
    results = []
    
    def make_request(request_id):
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            duration = time.time() - start_time
            results.append({
                'id': request_id,
                'status': response.status_code,
                'duration': duration,
                'headers': dict(response.headers)
            })
        except Exception as e:
            results.append({'id': request_id, 'error': str(e)})
    
    # 同时发送两个相同请求
    print("发送两个并发相同请求...")
    thread1 = threading.Thread(target=make_request, args=(1,))
    thread2 = threading.Thread(target=make_request, args=(2,))
    
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()
    
    # 分析结果
    if len(results) >= 2:
        for i, result in enumerate(results):
            print(f"请求{result['id']}: 状态={result['status']}, 耗时={result['duration']:.2f}s")
            if 'headers' in result:
                cache_hit = result['headers'].get('x-cache-hit', 'false')
                print(f"  x-cache-hit: {cache_hit}")
    
    print("\n=== 测试2: 间隔请求测试 ===")
    print("等待5秒后发送相同请求...")
    time.sleep(5)
    
    # 第三个请求（应该不命中缓存，因为没有响应缓存）
    start_time = time.time()
    response3 = requests.post(
        f"{BASE_URL}/v1/messages",
        headers=headers,
        json=payload,
        timeout=30
    )
    duration3 = time.time() - start_time
    
    print(f"间隔请求: 状态={response3.status_code}, 耗时={duration3:.2f}s")
    cache_hit3 = response3.headers.get('x-cache-hit', 'false')
    print(f"x-cache-hit: {cache_hit3}")
    
    if cache_hit3 == 'false':
        print("✅ 确认：间隔请求没有命中缓存（响应缓存已删除）")
    else:
        print("⚠️  意外：间隔请求仍然命中缓存")

if __name__ == "__main__":
    # 检查服务器
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print(f"❌ 服务器未正常运行，状态码: {response.status_code}")
            exit(1)
    except requests.exceptions.RequestException:
        print("❌ 无法连接到服务器，请确保服务器正在运行")
        print("   启动命令: python src/main.py")
        exit(1)
    
    test_deduplication_only()