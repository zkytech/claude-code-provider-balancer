# Zed Provider Support

## Overview

This document describes the support for Zed services in the Claude Code Provider Balancer. Zed is a modern code editor that provides hosted AI models with enhanced capabilities, including context-aware thread management and intelligent mode selection.

## Zed Request Structure

Zed uses a unique request structure that differs from standard Anthropic API requests:

```json
{
    "thread_id": "2fceb009-147e-4987-8cb3-81978e8ff38a",
    "prompt_id": "074d31be-1a11-4914-bb08-16a93dab1673",
    "intent": "user_prompt",
    "mode": "normal",
    "provider": "anthropic",
    "provider_request": {
        "model": "claude-sonnet-4",
        "max_tokens": 8192,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Hello, how are you?"
                    }
                ]
            }
        ]
    }
}
```

### Key Fields

- **thread_id**: Unique identifier for the conversation thread
- **prompt_id**: Unique identifier for individual prompts within a thread
- **intent**: Request type (typically "user_prompt")
- **mode**: Operation mode ("normal" or "burn")
- **provider**: Backend provider (typically "anthropic")
- **provider_request**: The actual Anthropic API request payload

## Zed Models and Pricing

Based on [Zed's official documentation](https://zed.dev/docs/ai/models), Zed offers various Claude models with different pricing structures:

### Available Models

| Model | Context Window | Normal Mode | Burn Mode |
|-------|---------------|-------------|-----------|
| Claude 3.5 Sonnet | 60k | $0.04/prompt | N/A |
| Claude 3.7 Sonnet | 120k | $0.04/prompt | $0.05/request |
| Claude Sonnet 4 | 120k | $0.04/prompt | $0.05/request |
| Claude Opus 4 | 120k | $0.20/prompt | $0.25/request |

### Mode Differences

**Normal Mode:**
- Limited to 25 tool calls per prompt
- Counted as single prompt for billing
- Requires user interaction after 25 tool calls

**Burn Mode:**
- Unlimited tool calls
- Each subsequent request counts as a prompt
- Enhanced reasoning capabilities
- Larger context windows (up to 200k tokens)

## Thread Management Strategy

### Context Window Management

Zed maintains separate context windows for each thread. Our implementation includes:

1. **Automatic Context Monitoring**: Track token usage per thread
2. **Smart Rotation**: Rotate threads before hitting context limits
3. **Context Summarization**: Preserve important context when rotating threads

### Thread Lifecycle

```python
@dataclass
class ZedThreadConfig:
    max_context_tokens: int = 120000  # Based on model
    max_tool_calls_per_prompt: int = 25
    thread_ttl: int = 3600  # 1 hour
    auto_rotate_on_context_full: bool = True
    summarize_on_rotate: bool = True
```

### Rotation Triggers

Threads are automatically rotated when:
- Context window reaches 80% capacity
- Thread exceeds TTL (default: 1 hour)
- Tool calls approach limit (normal mode only)
- User starts a new distinct task

## Configuration

### Provider Configuration

```yaml
providers:
  - name: "zed_provider"
    type: "zed"
    base_url: "https://zed-api.example.com"
    auth_type: "api_key"
    auth_value: "your-zed-api-key"
    enabled: true
    zed_config:
      default_mode: "normal"  # normal | burn
      auto_burn_mode_triggers:
        - "complex_coding_task"
        - "multi_step_analysis"
        - "agent_panel_usage"
      context_management:
        max_context_tokens: 120000
        rotation_threshold: 0.8  # 80% threshold
        summarization_method: "ai"
      thread_management:
        ttl: 3600
        auto_rotate: true
        task_based_isolation: true
```

### Model Routes

```yaml
model_routes:
  "claude-sonnet-4":
    - provider: "zed_provider"
      model: "claude-sonnet-4"
      priority: 1
      mode: "normal"
  
  "claude-sonnet-4-burn":
    - provider: "zed_provider"
      model: "claude-sonnet-4"
      priority: 1
      mode: "burn"
  
  "*sonnet*":
    - provider: "zed_provider"
      model: "passthrough"
      priority: 1
      mode: "auto"  # Automatically select based on request
```

## Implementation Details

### Request Processing Flow

1. **Request Analysis**: Analyze incoming request for task complexity
2. **Thread Management**: Get or create appropriate thread
3. **Mode Selection**: Choose normal/burn mode based on request
4. **Context Check**: Verify context window capacity
5. **Request Forwarding**: Forward to Zed with proper formatting
6. **Response Handling**: Process and return response
7. **State Updates**: Update thread state and statistics

### Thread State Management

The system maintains thread state including:
- Current context window usage
- Request count and tool call tracking
- Task context and conversation history
- Performance metrics and cost tracking

### Cost Optimization

To minimize costs:
- **Intelligent Mode Selection**: Use burn mode only when necessary
- **Context Window Management**: Rotate threads before hitting limits
- **Request Deduplication**: Avoid duplicate requests
- **Tool Call Limiting**: Monitor and limit tool usage in normal mode

## Error Handling

### Zed-Specific Errors

The system handles various Zed-specific error conditions:

- **Thread Expiration**: Automatically create new thread
- **Context Window Overflow**: Rotate with summarization
- **Mode Conflicts**: Resolve mode selection conflicts
- **Tool Call Limits**: Handle normal mode limitations

### Failover Strategy

When Zed provider fails:
1. Mark provider as unhealthy
2. Attempt failover to other providers
3. Preserve thread context for recovery
4. Log failure for monitoring

## Monitoring and Debugging

### Key Metrics

- Thread rotation frequency
- Context window utilization
- Mode selection patterns
- Cost per request/thread
- Tool call usage patterns

### Debug Commands

```bash
# Check Zed provider status
curl http://localhost:8080/providers | jq '.providers[] | select(.name=="zed_provider")'

# Monitor thread states
curl http://localhost:8080/zed/threads/status

# View cost analysis
curl http://localhost:8080/zed/cost-analysis
```

## Best Practices

### For Users

1. **Task Isolation**: Start new threads for distinct tasks
2. **Mode Selection**: Use burn mode for complex multi-step tasks
3. **Context Awareness**: Be mindful of context window limits
4. **Cost Monitoring**: Monitor usage and costs regularly

### For Administrators

1. **Configuration Tuning**: Adjust thread TTL and rotation thresholds
2. **Cost Monitoring**: Set up alerts for unusual usage patterns
3. **Performance Optimization**: Monitor and optimize thread management
4. **Capacity Planning**: Plan for peak usage scenarios

## Simplified Thread Management Flow

Based on practical requirements, we've designed a simplified and robust thread management flow:

### Core Design Principles

1. **Global Thread State**: Maintain one global thread_id until errors force rotation
2. **Error-Driven Rotation**: Only create new threads when Zed provider returns thread-related errors
3. **Context Preservation**: Use summarization API to preserve context when rotating threads
4. **Prompt-Level Continuation**: Handle tool call limits with new prompt_id, not thread rotation

### Implementation Flow

```python
@dataclass
class ZedGlobalState:
    """全局Zed状态管理"""
    current_thread_id: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    total_tool_calls: int = 0
    last_request_time: float = 0
    
    def reset_thread(self):
        """重置thread状态"""
        self.current_thread_id = None
        self.conversation_history = []
        self.total_tool_calls = 0

class ZedRequestHandler:
    def __init__(self):
        self.global_state = ZedGlobalState()
        self.lock = threading.Lock()
    
    async def handle_request(self, raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """处理Zed请求的主要逻辑"""
        with self.lock:
            # 1. 每次请求都生成新的prompt_id
            prompt_id = str(uuid.uuid4())
            
            # 2. 获取或创建thread_id（全局维护）
            thread_id = self._get_or_create_thread_id()
            
            # 3. 构建Zed请求
            zed_request = {
                "thread_id": thread_id,
                "prompt_id": prompt_id,
                "intent": raw_request.get("intent", "user_prompt"),
                "mode": raw_request.get("mode", "normal"),
                "provider": "anthropic",
                "provider_request": raw_request.get("provider_request", raw_request)
            }
            
            return zed_request
```

### Error Handling Strategy

#### Thread Rotation Errors
Errors that require creating a new thread with context summarization:

```python
THREAD_ROTATION_ERRORS = {
    "context_length_exceeded": "上下文长度超过限制",
    "thread_expired": "Thread已过期",
    "thread_not_found": "Thread不存在",
    "thread_limit_reached": "Thread达到最大限制",
    "invalid_thread_state": "Thread状态无效",
    "thread_corrupted": "Thread数据损坏"
}
```

#### Prompt Continuation Errors
Errors that only need a new prompt_id (no thread rotation):

```python
PROMPT_CONTINUATION_ERRORS = {
    "tool_calls_limit_exceeded": "工具调用次数超过25次限制",
    "user_interaction_required": "需要用户交互确认"
}
```

### Request Processing Flow

```python
async def process_zed_request(request: Request) -> Union[JSONResponse, StreamingResponse]:
    """主要的Zed请求处理流程"""
    raw_body = await request.json()
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 1. 构建Zed请求
            zed_request = await zed_handler.handle_request(raw_body)
            
            # 2. 发送到Zed provider
            response = await send_to_zed_provider(zed_request)
            
            # 3. 检查响应
            if response.status_code == 200:
                # 成功响应
                result = response.json()
                await zed_handler.handle_response(result, was_error=False)
                return JSONResponse(content=result)
            
            else:
                # 错误响应
                error_data = response.json()
                should_retry = await zed_handler.handle_response(error_data, was_error=True)
                
                if should_retry and retry_count < max_retries - 1:
                    retry_count += 1
                    continue
                else:
                    # 不重试或达到最大重试次数
                    return JSONResponse(content=error_data, status_code=response.status_code)
        
        except Exception as e:
            # 处理其他异常
            if retry_count < max_retries - 1:
                retry_count += 1
                continue
            else:
                raise e
    
    return JSONResponse(content={"error": "Max retries exceeded"}, status_code=500)
```

### Thread Rotation Implementation

```python
async def _rotate_thread(self):
    """轮转到新thread"""
    # 1. 获取当前对话历史总结
    summary = await self._summarize_conversation()
    
    # 2. 重置全局状态
    self.global_state.reset_thread()
    
    # 3. 用总结初始化新thread的历史
    if summary:
        self.global_state.conversation_history = [{
            "role": "assistant",
            "content": summary
        }]

async def _summarize_conversation(self) -> Optional[str]:
    """调用总结接口获取对话历史总结"""
    if not self.global_state.conversation_history:
        return None
    
    # 调用总结接口
    summary_request = {
        "conversation_history": self.global_state.conversation_history,
        "max_length": 2000  # 控制总结长度
    }
    
    return await self._call_summarization_service(summary_request)
```

### Key Implementation Considerations

1. **Thread Safety**: Use locks to protect global state modifications
2. **Error Classification**: Accurately identify error types from Zed responses
3. **Context Preservation**: Implement reliable conversation summarization
4. **Retry Logic**: Handle transient errors with appropriate retry strategies
5. **Monitoring**: Track thread rotation frequency and reasons

### Configuration Example

```yaml
providers:
  - name: "zed_provider"
    type: "zed"
    base_url: "https://zed-api.example.com"
    auth_type: "api_key"
    auth_value: "your-zed-api-key"
    enabled: true
    zed_config:
      thread_management:
        max_retries: 3
        summarization_max_length: 2000
        error_classification:
          thread_rotation_errors:
            - "context_length_exceeded"
            - "thread_expired"
            - "thread_not_found"
          prompt_continuation_errors:
            - "tool_calls_limit_exceeded"
            - "user_interaction_required"
```

## Future Enhancements

Planned improvements include:
- **Advanced Summarization**: Better context preservation algorithms
- **Predictive Rotation**: Anticipate thread rotation needs before errors
- **Cost Optimization**: More sophisticated cost management
- **Performance Monitoring**: Enhanced metrics and alerting
- **User Controls**: More granular user control over thread management

## Troubleshooting

### Common Issues

1. **Thread Not Found**: Check thread TTL and rotation settings
2. **Context Overflow**: Adjust rotation threshold or summarization
3. **Mode Conflicts**: Review mode selection logic
4. **High Costs**: Monitor burn mode usage and tool calls

### Debug Steps

1. Check provider health status
2. Review thread state and history
3. Analyze request patterns and costs
4. Verify configuration settings
5. Monitor error logs and metrics

For additional support, refer to the main documentation and provider health endpoints.