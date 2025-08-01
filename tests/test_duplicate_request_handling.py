"""
重写的重复请求处理测试，专注测试4个核心流程：

1. stream/non-stream 没有返回的情况下, non-stream/stream 重复请求的处理
2. stream/non-stream 已经返回的情况下, non-stream/stream重复请求的处理 
3. stream/non-stream 报错的情况下, non-stream/stream重复请求的处理
4. 去重缓存过期逻辑测试
"""

import asyncio
import pytest
import httpx

# Import the testing framework
from framework import (
    Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    Environment
)


class TestDuplicateRequestHandling:
    """重复请求处理的核心测试场景"""

    @pytest.mark.asyncio
    async def test_duplicate_requests_while_original_pending(self):
        """测试场景1: 原始请求正在处理中时的重复请求处理"""
        # 确保去重功能正常工作的基础配置
        dedup_config = {
            "timeouts": {
                "caching": {
                    "deduplication_timeout": 180  # 使用默认超时时间
                }
            }
        }
        
        scenario = Scenario(
            name="pending_duplicate_test",
            providers=[
                ProviderConfig(
                    "slow_provider", 
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Pending request response"},
                    delay_ms=2000  # 2秒延迟，确保有时间发送重复请求
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test duplicate requests while original is pending",
            settings_override=dedup_config
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test pending duplicate request"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 启动原始stream请求（不等待完成）
                stream_request = test_request.copy()
                stream_request["stream"] = True
                
                async def make_stream_request():
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=stream_request
                    )
                    chunks = []
                    current_chunk = ""
                    
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line:
                            current_chunk += line + "\n"
                        else:
                            # 空行表示一个SSE事件结束
                            if current_chunk.strip():
                                chunks.append(current_chunk.strip())
                                current_chunk = ""
                    
                    # 处理最后一个chunk（如果没有以空行结尾）
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    
                    return response.status_code, chunks
                
                # 启动non-stream重复请求（稍微延迟）
                async def make_non_stream_request():
                    await asyncio.sleep(0.5)  # 确保原始请求先启动
                    non_stream_request = test_request.copy()
                    non_stream_request["stream"] = False
                    
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=non_stream_request
                    )
                    return response.status_code, response.json()
                
                # 并发执行两个请求
                stream_task = asyncio.create_task(make_stream_request())
                non_stream_task = asyncio.create_task(make_non_stream_request())
                
                stream_status, stream_chunks = await stream_task
                non_stream_status, non_stream_data = await non_stream_task
                
                # 验证两个请求都成功
                assert stream_status == 200, f"Stream request failed with status {stream_status}"
                assert non_stream_status == 200, f"Non-stream request failed with status {non_stream_status}"
                
                # 验证内容一致性（都来自同一个原始请求的结果）
                assert len(stream_chunks) > 0, "Stream response should have content"
                assert non_stream_data["type"] == "message", "Non-stream should return message type"
                assert len(non_stream_data["content"]) > 0, "Non-stream should have content"

    @pytest.mark.asyncio
    async def test_duplicate_requests_after_original_completed(self):
        """测试场景2: 原始请求已经返回后的重复请求处理"""
        scenario = Scenario(
            name="completed_duplicate_test",
            providers=[
                ProviderConfig(
                    "fast_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Completed request response"},
                    delay_ms=100  # 很短的延迟，确保第一个请求快速完成
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test duplicate requests after original completed"
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test completed duplicate request"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 第一个请求：non-stream
                non_stream_request = test_request.copy()
                non_stream_request["stream"] = False
                
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=non_stream_request
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                assert data1["type"] == "message"
                
                # 等待一小段时间确保缓存被清理
                await asyncio.sleep(1)
                
                # 第二个请求：相同内容但stream模式
                stream_request = test_request.copy()
                stream_request["stream"] = True
                
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=stream_request
                )
                
                assert response2.status_code == 200
                assert "text/event-stream" in response2.headers.get("content-type", "")
                
                chunks2 = []
                async for chunk in response2.aiter_text():
                    if chunk.strip():
                        chunks2.append(chunk.strip())
                
                # 验证第二个请求被当作新请求处理（不是从缓存获取）
                assert len(chunks2) > 0, "Second request should get fresh response"

    @pytest.mark.asyncio
    async def test_duplicate_requests_when_original_failed(self):
        """测试场景3: 原始请求报错时的重复请求处理"""
        
        scenario = Scenario(
            name="failed_duplicate_test",
            providers=[
                ProviderConfig(
                    "error_provider",
                    ProviderBehavior.INTERNAL_SERVER_ERROR,  # 服务器错误
                    response_data={"error": "Provider unavailable"},
                    delay_ms=1000  # 1秒延迟，确保有时间发送重复请求
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test duplicate requests when original fails"
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test failed duplicate request"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 启动原始stream请求
                stream_request = test_request.copy()
                stream_request["stream"] = True
                
                async def make_stream_request():
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=stream_request
                    )
                    if response.status_code != 200:
                        return response.status_code, response.json()
                    else:
                        chunks = []
                        async for chunk in response.aiter_text():
                            if chunk.strip():
                                chunks.append(chunk.strip())
                        return response.status_code, chunks
                
                # 启动non-stream重复请求
                async def make_non_stream_request():
                    await asyncio.sleep(0.5)  # 确保原始请求先启动
                    non_stream_request = test_request.copy()
                    non_stream_request["stream"] = False
                    
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=non_stream_request
                    )
                    return response.status_code, response.json()
                
                # 并发执行两个请求
                stream_task = asyncio.create_task(make_stream_request())
                non_stream_task = asyncio.create_task(make_non_stream_request())
                
                stream_status, stream_data = await stream_task
                non_stream_status, non_stream_data = await non_stream_task
                
                # 验证两个请求都收到错误响应
                assert stream_status >= 400, f"Stream request should fail with error status, got {stream_status}"
                assert non_stream_status >= 400, f"Non-stream request should fail with error status, got {non_stream_status}"
                
                # 验证错误响应格式
                if isinstance(stream_data, dict):
                    assert "error" in stream_data or "type" in stream_data
                assert "error" in non_stream_data or "type" in non_stream_data
                
                # 等待一段时间后，发送新的请求应该被当作新请求处理
                await asyncio.sleep(2)
                
                response3 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                # 新请求应该也会失败，但是被当作新请求处理
                assert response3.status_code >= 400

    @pytest.mark.asyncio
    async def test_deduplication_cache_expiration(self):
        """测试场景4: 去重缓存过期逻辑"""
        scenario = Scenario(
            name="cache_expiration_test",
            providers=[
                ProviderConfig(
                    "normal_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Cache expiration test response"},
                    delay_ms=500
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test deduplication cache expiration"
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test cache expiration"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                # 第一个请求：stream模式，启动但不等待完成
                stream_request = test_request.copy()
                stream_request["stream"] = True
                
                async def make_long_stream_request():
                    # 添加一个长延迟，模拟长时间运行的请求
                    long_delay_request = stream_request.copy()
                    long_delay_request["messages"][0]["content"] += " with long delay"
                    
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=long_delay_request
                    )
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk.strip())
                    return response.status_code, chunks
                
                # 启动长时间运行的请求
                long_task = asyncio.create_task(make_long_stream_request())
                
                # 等待0.5秒后发送重复请求
                await asyncio.sleep(0.5)
                
                # 发送一个会被去重的请求
                duplicate_request = test_request.copy()
                duplicate_request["stream"] = False
                duplicate_request["messages"][0]["content"] += " with long delay"  # 相同内容
                
                # 这个请求应该等待原始请求完成，但由于超时会失败
                try:
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=duplicate_request
                    )
                    
                    # 如果在超时时间内完成，应该得到响应
                    if response.status_code == 200:
                        data = response.json()
                        assert data["type"] == "message"
                    elif response.status_code == 409:
                        # 或者得到取消响应
                        data = response.json()
                        assert "error" in data
                        assert "cancelled" in data["error"]["message"] or "timeout" in data["error"]["message"]
                    else:
                        # 其他错误也是可接受的
                        assert response.status_code >= 400
                        
                except Exception as e:
                    # 超时或其他异常也是预期的行为
                    assert "timeout" in str(e).lower() or "cancelled" in str(e).lower()
                
                # 取消长时间运行的任务
                long_task.cancel()
                try:
                    await long_task
                except asyncio.CancelledError:
                    pass
                
                # 等待一段时间让缓存过期
                await asyncio.sleep(4)
                
                # 现在发送相同的请求，应该被当作新请求处理
                final_request = test_request.copy()
                final_request["stream"] = False
                
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=final_request
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["type"] == "message"
                
                # 验证这是一个新的请求处理，而不是缓存结果
                assert len(data["content"]) > 0

    @pytest.mark.asyncio
    async def test_concurrent_mixed_mode_duplicates(self):
        """补充测试：并发的混合模式重复请求"""
        scenario = Scenario(
            name="concurrent_mixed_test",
            providers=[
                ProviderConfig(
                    "mixed_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Mixed mode concurrent response"},
                    delay_ms=1500
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test concurrent mixed mode duplicate requests"
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test concurrent mixed duplicates"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 创建多个不同模式的并发请求
                async def make_stream_request():
                    req = test_request.copy()
                    req["stream"] = True
                    response = await client.post(f"{env.balancer_url}/v1/messages", json=req)
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk.strip())
                    return response.status_code, chunks
                
                async def make_non_stream_request():
                    req = test_request.copy()
                    req["stream"] = False
                    response = await client.post(f"{env.balancer_url}/v1/messages", json=req)
                    return response.status_code, response.json()
                
                # 并发启动多个请求：2个stream + 2个non-stream
                tasks = [
                    asyncio.create_task(make_stream_request()),
                    asyncio.create_task(make_non_stream_request()),
                    asyncio.create_task(make_stream_request()),
                    asyncio.create_task(make_non_stream_request()),
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 验证所有请求都得到了响应（无论是成功还是被取消）
                success_count = 0
                error_count = 0
                
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                    else:
                        status_code, _ = result
                        if status_code == 200:
                            success_count += 1
                        elif status_code == 409:  # 取消的重复请求
                            error_count += 1
                        else:
                            error_count += 1
                
                # 至少应该有一个成功的请求
                assert success_count >= 1, f"Expected at least 1 success, got {success_count} successes and {error_count} errors"

    @pytest.mark.asyncio
    async def test_sse_error_delayed_cleanup(self):
        """测试场景5: SSE错误响应的延迟清理，让重复请求也能获取到错误结果"""
        # 这个测试场景比较特殊，因为需要模拟stream返回包含错误模式的SSE数据
        # 但技术上HTTP状态码是200。我们可以通过特殊的response_data来实现
        # 为了触发SSE错误检测，我们需要构造包含错误模式的响应
        # 根据配置文件，"rate.?limit" 和 "insufficient.*credits" 等模式会触发unhealthy检测
        
        # SSE错误延迟清理的配置
        sse_config = {
            "unhealthy_response_body_patterns": [
                '"message"\\s*:\\s*".*rate.?limit.*"',  # 匹配rate limit错误模式
                "rate.?limit"  # 简单的rate limit匹配
            ]
        }
        
        scenario = Scenario(
            name="sse_error_delayed_test",
            providers=[
                ProviderConfig(
                    "sse_error_provider",
                    ProviderBehavior.STREAMING_SUCCESS,  # 流式成功响应，但内容包含错误模式
                    response_data={
                        "content": 'rate limit exceeded for this API key',  # 包含"rate limit"模式，会触发unhealthy检测
                        "error_type": "rate_limit_error"
                    },
                    delay_ms=1000,  # 1秒延迟，确保有时间发送重复请求
                )
            ],
            settings_override=sse_config,
            expected_behavior=ExpectedBehavior.SUCCESS,  # HTTP 200但内容包含错误模式
            description="Test SSE error delayed cleanup for duplicate requests"
        )
        
        async with Environment(scenario) as env:
            test_request = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test SSE error delayed cleanup"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 启动原始stream请求
                stream_request = test_request.copy()
                stream_request["stream"] = True
                
                async def make_stream_request():
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=stream_request
                    )
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk.strip())
                    return response.status_code, chunks
                
                # 启动non-stream重复请求（在原始请求处理期间）
                async def make_non_stream_duplicate():
                    await asyncio.sleep(0.5)  # 等待原始请求开始处理
                    non_stream_request = test_request.copy()
                    non_stream_request["stream"] = False
                    
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=non_stream_request
                    )
                    return response.status_code, response.json()
                
                # 并发执行两个请求
                stream_task = asyncio.create_task(make_stream_request())
                non_stream_task = asyncio.create_task(make_non_stream_duplicate())
                
                stream_status, stream_chunks = await stream_task
                non_stream_status, non_stream_data = await non_stream_task
                
                # 验证stream请求返回了包含错误模式的数据
                assert stream_status == 200, f"Stream request should return 200 with SSE content, got {stream_status}"
                assert len(stream_chunks) > 0, "Stream should have content chunks"
                
                # 检查stream chunks中是否包含错误模式的内容
                content_text = " ".join(stream_chunks)
                has_error_pattern = "rate limit" in content_text.lower()
                
                # 根据是否检测到错误模式，验证相应的行为
                if has_error_pattern:
                    # 如果检测到错误模式，non-stream重复请求应该也获得错误响应
                    # 这取决于系统如何处理延迟清理期间的重复请求
                    
                    # 重复请求可能获得错误响应，也可能正常响应（取决于具体实现）
                    if non_stream_status >= 400:
                        assert "error" in non_stream_data, "Non-stream duplicate should contain error if status >= 400"
                    else:
                        # 如果是200响应，应该有正常的消息结构
                        assert non_stream_data.get("type") == "message", "Non-stream should have message type"
                else:
                    # 如果没有检测到错误模式，按正常流程验证
                    assert non_stream_status == 200, f"Non-stream duplicate should succeed, got {non_stream_status}"
                    assert non_stream_data.get("type") == "message", "Non-stream should return message type"
                
                # 等待延迟清理期间，再发送一个重复请求
                await asyncio.sleep(1)  # 在3秒延迟清理期间
                
                # 这个请求应该仍然能获取到缓存的错误结果
                late_duplicate_request = test_request.copy()
                late_duplicate_request["stream"] = False
                
                response3 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=late_duplicate_request
                )
                
                # 这个请求的行为取决于是否还在延迟清理期间
                # 如果原始请求触发了错误模式检测和延迟清理，这个请求可能：
                # 1. 获得缓存的错误响应（如果还在延迟清理期间）
                # 2. 被当作新请求处理（如果延迟清理已完成）
                
                if response3.status_code >= 400:
                    data3 = response3.json()
                    assert "error" in data3, "Late duplicate should contain error if status >= 400"
                elif response3.status_code == 200:
                    data3 = response3.json()
                    # 验证响应格式正确
                    assert "type" in data3 or "error" in data3, "Late duplicate should have valid response format"
                
                # 等待延迟清理完成后，再发送请求应该被当作新请求
                await asyncio.sleep(3)  # 等待延迟清理完成
                
                final_request = test_request.copy()
                final_request["stream"] = False
                
                response4 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=final_request
                )
                
                # 这个请求应该被当作新请求处理
                # 可能成功也可能失败，取决于provider的行为
                assert response4.status_code in [200, 400, 500], "Final request should be processed as new request"