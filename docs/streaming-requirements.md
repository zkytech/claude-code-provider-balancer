# Claude Code Provider Balancer - Streaming业务需求文档

## 1. 核心Streaming需求

### 1.1 实时性要求
- **真实流传输**：客户端应该实时接收到数据，而不是等待所有数据完成后一次性接收
- **延迟最小化**：从provider返回数据到客户端接收到数据的延迟应该在毫秒级别
- **渐进式显示**：支持Claude Code客户端的打字机效果，用户能看到文本逐步生成

### 1.2 数据完整性要求
- **无数据丢失**：所有来自provider的数据都必须准确传递给客户端
- **顺序保持**：数据块必须按照provider发送的顺序到达客户端
- **格式保持**：SSE (Server-Sent Events) 格式必须正确维护

## 2. 业务功能需求

### 2.1 请求去重和缓存
- **重复请求处理**：多个相同签名的streaming请求应该能够共享同一个provider响应
- **并行客户端支持**：多个客户端可以同时接收同一个streaming响应
- **缓存机制**：已完成的streaming响应需要缓存，供后续重复请求使用

### 2.2 错误处理和健康检查
- **SSE错误检测**：在streaming过程中检测到provider错误时，需要记录并处理
- **Provider健康状态**：根据streaming响应的内容判断provider是否健康
- **Failover支持**：虽然streaming请求无法在传输过程中failover，但需要标记不健康的provider

### 2.3 日志和监控
- **详细日志**：记录每个chunk的接收和转发时间，用于性能监控
- **性能指标**：统计streaming延迟、throughput等关键指标
- **调试信息**：在DEBUG模式下提供详细的数据流追踪

## 3. 技术架构需求

### 3.1 多Provider支持
- **Anthropic格式**：支持Claude原生的SSE格式
- **OpenAI格式**：支持OpenAI兼容provider的streaming格式，并转换为Anthropic格式
- **格式转换**：实时进行格式转换，不能等待完整响应

### 3.2 并发处理
- **ParallelBroadcaster**：使用broadcaster模式支持多个客户端同时接收
- **异步处理**：所有streaming操作必须是异步的，不能阻塞其他请求
- **资源管理**：及时清理completed的streaming资源

### 3.3 网络层要求
- **HTTP Keep-Alive**：维持与provider的长连接
- **背压处理**：处理网络延迟或客户端接收速度慢的情况
- **超时管理**：适当的超时配置，既不过早断开，也不无限等待

## 4. 性能指标

### 4.1 延迟指标
- **Chunk接收延迟**：从provider发送到balancer接收 < 5ms
- **Chunk转发延迟**：从balancer接收到客户端接收 < 5ms
- **端到端延迟**：从provider到最终客户端 < 10ms

### 4.2 吞吐量指标
- **并发流数量**：单个balancer实例支持 >= 100个并发streaming请求
- **数据吞吐量**：支持高吞吐量文本生成，不成为瓶颈

## 5. 兼容性需求

### 5.1 客户端兼容性
- **Claude Code官方客户端**：完全兼容原生Claude Code的streaming行为
- **自定义客户端**：支持标准的SSE客户端
- **Curl测试**：支持curl -N进行streaming测试

### 5.2 Provider兼容性
- **官方Claude API**：完全兼容Anthropic官方API的streaming格式
- **第三方Provider**：兼容各种Claude Code代理服务的streaming实现
- **OpenAI兼容服务**：支持OpenAI格式的streaming并转换

## 6. 错误处理需求

### 6.1 网络错误
- **连接中断**：妥善处理provider连接中断
- **超时处理**：合理的超时策略，避免无限等待
- **重连机制**：在可能的情况下进行重连

### 6.2 数据错误
- **格式错误**：处理malformed SSE数据
- **编码错误**：处理UTF-8解码错误
- **不完整数据**：处理截断的JSON或SSE事件

## 7. 测试验证标准

### 7.1 功能测试
- **实时性验证**：使用mock provider验证数据是否实时到达
- **完整性验证**：确保所有数据都正确传递
- **并发性验证**：测试多客户端同时streaming

### 7.2 性能测试
- **延迟测试**：测量各环节的延迟时间
- **压力测试**：测试高并发下的streaming表现
- **长时间测试**：测试长时间streaming的稳定性

## 8. 当前问题总结

### 8.1 已识别问题
1. **数据缓冲问题**：当前实现会缓冲所有数据，然后一次性发送给客户端
2. **httpx使用问题**：没有使用正确的streaming context manager
3. **时间戳问题**：所有chunk在同一时刻到达客户端，而不是分散到达

### 8.2 修复目标
1. **实现真正的实时streaming**：数据从provider到客户端应该是流式的
2. **保持所有现有功能**：请求去重、错误处理、健康检查等不能丢失
3. **性能优化**：在实现实时性的同时，不能显著降低性能

---

*此文档将作为streaming功能修复和验证的基准。任何修改都需要确保满足以上所有需求。*