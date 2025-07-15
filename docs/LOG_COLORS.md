# 日志颜色功能使用指南

## 概述

Claude Code Provider Balancer 现已支持彩色日志输出，根据不同的日志级别自动显示不同颜色，提升开发和调试体验。

## 功能特性

### 日志级别颜色映射

- **DEBUG**: 青色 (Cyan) `\033[36m`
- **INFO**: 绿色 (Green) `\033[32m`
- **WARNING**: 黄色 (Yellow) `\033[33m`
- **ERROR**: 红色 (Red) `\033[31m`
- **CRITICAL**: 洋红色 (Magenta) `\033[95m`

### 自动检测

颜色功能会自动检测以下条件：
- 输出到 TTY 终端（`sys.stdout.isatty()` 返回 `True`）
- `log_color` 配置选项启用
- 终端支持 ANSI 颜色代码

## 配置

### 在 `providers.yaml` 中配置

```yaml
settings:
  # 其他配置...
  log_level: "DEBUG"
  # 日志颜色开关
  log_color: true  # 启用颜色 (默认: true)
```

### 环境变量配置

```bash
# 通过环境变量控制
export LOG_COLOR=true   # 启用颜色
export LOG_COLOR=false  # 禁用颜色
```

## 使用示例

### 启动服务器查看彩色日志

```bash
# 启动服务器
python src/main.py

# 或使用 uv
uv run src/main.py
```

### 测试颜色功能

```bash
# 运行颜色测试脚本
python test_log_colors.py

# 或运行简单颜色测试
python simple_color_test.py
```

## 实际效果

当启用颜色功能时，不同级别的日志会以不同颜色显示：

- **INFO 日志**（绿色）：正常操作信息
- **WARNING 日志**（黄色）：警告信息
- **ERROR 日志**（红色）：错误信息
- **CRITICAL 日志**（洋红色）：严重错误
- **DEBUG 日志**（青色）：调试信息

## 颜色禁用场景

在以下情况下，颜色会自动禁用：

1. **非 TTY 环境**：管道输出或重定向到文件
   ```bash
   python src/main.py > output.log  # 无颜色
   python src/main.py | grep ERROR  # 无颜色
   ```

2. **配置禁用**：`log_color: false`

3. **文件日志**：文件输出始终无颜色（避免污染日志文件）

## 技术实现

### ColoredConsoleFormatter

项目使用自定义的 `ColoredConsoleFormatter` 类：

```python
class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with color support based on log level."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    RESET = '\033[0m'
```

### 动态配置检查

Formatter 在运行时动态检查配置：

```python
use_colors = (
    current_settings is not None 
    and getattr(current_settings, 'log_color', True)
    and hasattr(sys.stdout, 'isatty') 
    and sys.stdout.isatty()
)
```

## 兼容性

### 支持的终端

- **macOS**: Terminal.app, iTerm2
- **Linux**: 大多数现代终端
- **Windows**: Windows Terminal, PowerShell (需支持 ANSI)

### 不支持的环境

- 旧版 Windows 命令提示符（不支持 ANSI）
- 某些 IDE 的内置终端
- 管道输出和文件重定向

## 故障排除

### 看不到颜色？

1. **检查配置**
   ```bash
   # 确认配置文件中 log_color 为 true
   grep "log_color" providers.yaml
   ```

2. **检查终端支持**
   ```bash
   # 测试终端是否支持颜色
   echo -e "\033[31m红色文本\033[0m"
   ```

3. **检查 TTY 状态**
   ```python
   import sys
   print(f"sys.stdout.isatty(): {sys.stdout.isatty()}")
   ```

### 调试工具

项目提供了多个调试脚本：

- `simple_color_test.py`: 基本颜色测试
- `debug_colors.py`: 详细诊断信息
- `debug_logging_config.py`: 日志配置检查
- `test_log_colors.py`: 完整功能测试

## 最佳实践

1. **开发环境**：启用颜色以提升开发体验
2. **生产环境**：根据需要选择，通常在容器环境中禁用
3. **日志分析**：使用无颜色输出便于自动化处理
4. **CI/CD**：通常自动禁用颜色（非 TTY 环境）

## 更新日志

- **v0.3.0**: 新增日志颜色功能
  - 支持按日志级别显示不同颜色
  - 自动检测 TTY 环境
  - 可配置的颜色开关
  - 保持文件日志无颜色