"""
Comprehensive tests for content handling between Anthropic and OpenAI formats.
These tests validate all aspects of content conversion including complex structures,
edge cases, and special formats.
"""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from claude_proxy.conversion import (_serialize_tool_result,
                                     convert_anthropic_to_openai_messages,
                                     convert_openai_to_anthropic)
from claude_proxy.models import (ContentBlockImage, ContentBlockText,
                                 ContentBlockToolResult, ContentBlockToolUse,
                                 Message, SystemContent)


@pytest.fixture
def image_base64_data():
    """Sample base64 image data for testing."""
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


@pytest.fixture
def text_block():
    """Fixture for a simple text content block."""

    def _create_text_block(text: str) -> ContentBlockText:
        return ContentBlockText(type="text", text=text)

    return _create_text_block


@pytest.fixture
def image_block():
    """Fixture for an image content block."""

    def _create_image_block(
        data: str, media_type: str = "image/jpeg"
    ) -> ContentBlockImage:
        return ContentBlockImage(
            type="image",
            source={"type": "base64", "media_type": media_type, "data": data},
        )

    return _create_image_block


@pytest.fixture
def tool_use_block():
    """Fixture for a tool use content block."""

    def _create_tool_use_block(
        id: str, name: str, input_dict: Dict
    ) -> ContentBlockToolUse:
        return ContentBlockToolUse(type="tool_use", id=id, name=name, input=input_dict)

    return _create_tool_use_block


@pytest.fixture
def tool_result_block():
    """Fixture for a tool result content block."""

    def _create_tool_result_block(
        tool_use_id: str, content: Any
    ) -> ContentBlockToolResult:
        return ContentBlockToolResult(
            type="tool_result", tool_use_id=tool_use_id, content=content
        )

    return _create_tool_result_block


@pytest.fixture
def system_content_block():
    """Fixture for a system content block."""

    def _create_system_content(text: str) -> SystemContent:
        return SystemContent(type="text", text=text)

    return _create_system_content


@pytest.fixture
def sample_tools():
    """Fixture providing sample tool definitions."""
    calculator_tool = {
        "name": "calculator",
        "description": "Evaluate mathematical expressions",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate",
                }
            },
            "required": ["expression"],
        },
    }

    weather_tool = {
        "name": "weather",
        "description": "Get weather information for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city or location to get weather for",
                },
                "units": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature units",
                },
            },
            "required": ["location"],
        },
    }

    return [calculator_tool, weather_tool]


@pytest.fixture
def mock_openai_response():
    """Fixture providing a mock OpenAI response."""

    def _create_response(
        content: Optional[str] = "This is a response",
        tool_calls: Optional[List[Dict]] = None,
        finish_reason: str = "stop",
    ) -> MagicMock:
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message = MagicMock()
        response.choices[0].message.content = content

        if tool_calls:
            response.choices[0].message.tool_calls = []
            for tc in tool_calls:
                tool_call = MagicMock()
                tool_call.id = tc.get("id", "call_123")
                tool_call.type = tc.get("type", "function")
                tool_call.function = MagicMock()
                tool_call.function.name = tc.get("function", {}).get(
                    "name", "default_tool"
                )
                tool_call.function.arguments = tc.get("function", {}).get(
                    "arguments", "{}"
                )
                response.choices[0].message.tool_calls.append(tool_call)
        else:
            response.choices[0].message.tool_calls = None

        response.choices[0].finish_reason = finish_reason
        response.id = "resp_123"
        response.usage = MagicMock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5

        return response

    return _create_response


@pytest.fixture
def mock_streaming_response():
    """Fixture for creating mock streaming responses."""

    def _create_streaming_response(chunks: List[Dict[str, Any]]) -> MagicMock:
        class MockAsyncGenerator:
            def __init__(self, chunks):
                self.chunks = chunks
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration

                chunk = MagicMock()
                for key, value in self.chunks[self.index].items():
                    setattr(chunk, key, value)

                self.index += 1
                return chunk

        return MockAsyncGenerator(chunks)

    return _create_streaming_response




class TestAnthropicToOpenAIConversion:
    """Test conversion from Anthropic to OpenAI format."""

    def test_simple_text_conversion(self):
        """Test conversion of simple text messages."""
        messages = [
            Message(role="user", content="Hello, world!"),
            Message(role="assistant", content="Hi there! How can I help you?"),
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello, world!"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Hi there! How can I help you?"

    def test_system_message_conversion(self, system_content_block):
        """Test conversion of system messages in both string and list formats."""
        messages = [Message(role="user", content="Hello")]
        system_string = "You are a helpful assistant."

        result1 = convert_anthropic_to_openai_messages(messages, system_string)

        assert len(result1) == 2
        assert result1[0]["role"] == "system"
        assert result1[0]["content"] == "You are a helpful assistant."

        system_blocks = [
            system_content_block("You are a helpful assistant."),
            system_content_block("Be concise and accurate."),
        ]

        result2 = convert_anthropic_to_openai_messages(messages, system_blocks)

        assert len(result2) == 2
        assert result2[0]["role"] == "system"
        assert "You are a helpful assistant." in result2[0]["content"]
        assert "Be concise and accurate." in result2[0]["content"]

    def test_structured_content_conversion(self, text_block):
        """Test conversion of structured content blocks to OpenAI format."""
        messages = [
            Message(
                role="user",
                content=[
                    text_block("Hello, I have a question."),
                    text_block("What's the weather like today?"),
                ],
            )
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][0]["text"] == "Hello, I have a question."
        assert result[0]["content"][1]["type"] == "text"
        assert result[0]["content"][1]["text"] == "What's the weather like today?"

    def test_multimodal_content_conversion(
        self, text_block, image_block, image_base64_data
    ):
        """Test conversion of multimodal content with text and images."""
        messages = [
            Message(
                role="user",
                content=[
                    text_block("Check out this image:"),
                    image_block(image_base64_data),
                ],
            )
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][1]["type"] == "image_url"
        assert "url" in result[0]["content"][1]["image_url"]
        assert image_base64_data in result[0]["content"][1]["image_url"]["url"]

    def test_tool_use_conversion(self, text_block, tool_use_block):
        """Test conversion of assistant messages with tool use."""
        messages = [
            Message(
                role="assistant",
                content=[
                    text_block("I'll check the weather for you."),
                    tool_use_block(
                        "tool_123",
                        "weather",
                        {"location": "New York", "units": "celsius"},
                    ),
                ],
            )
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) == 2
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll check the weather for you."
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] is None
        assert "tool_calls" in result[1]
        assert len(result[1]["tool_calls"]) == 1
        assert result[1]["tool_calls"][0]["id"] == "tool_123"
        assert result[1]["tool_calls"][0]["function"]["name"] == "weather"
        args = json.loads(result[1]["tool_calls"][0]["function"]["arguments"])
        assert args["location"] == "New York"
        assert args["units"] == "celsius"

    def test_tool_result_conversion(self, text_block, tool_result_block):
        """Test conversion of user messages with tool result."""
        messages = [
            Message(
                role="user",
                content=[
                    text_block("Here's the result:"),
                    tool_result_block("tool_123", "It's currently 22°C in New York."),
                ],
            )
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) >= 2
        assert result[0]["role"] == "user"
        assert "Here's the result:" in result[0]["content"]

        tool_messages = [msg for msg in result if msg.get("role") == "tool"]
        assert len(tool_messages) >= 1
        assert tool_messages[0]["tool_call_id"] == "tool_123"
        assert "It's currently 22°C in New York." in tool_messages[0]["content"]

    def test_complex_tool_result_formats(self, text_block, tool_result_block):
        """Test conversion of tool results with various content formats."""
        test_cases = [
            "Simple string result",
            [
                {"type": "text", "text": "Text block 1"},
                {"type": "text", "text": "Text block 2"},
            ],
            json.dumps({"data": {"results": [{"value": 42, "unit": "degrees"}]}}),
            [{"type": "text", "text": "Text"}, {"value": 123}, "plain string"],
            [{"not_type": "invalid", "value": "test"}],
        ]

        for content in test_cases:
            messages = [
                Message(
                    role="user",
                    content=[
                        text_block("Tool result:"),
                        tool_result_block("tool_123", content),
                    ],
                )
            ]

            result = convert_anthropic_to_openai_messages(messages)

            assert len(result) >= 2

            tool_messages = [msg for msg in result if msg.get("role") == "tool"]
            assert len(tool_messages) >= 1
            assert tool_messages[0]["tool_call_id"] == "tool_123"
            assert (
                tool_messages[0]["content"] != ""
            )  

    def test_empty_content_handling(self):
        """Test handling of empty or None content."""
        messages1 = [Message(role="user", content="")]
        result1 = convert_anthropic_to_openai_messages(messages1)
        assert len(result1) == 1
        assert result1[0]["content"] == ""

        messages2 = [Message(role="user", content=[])]
        result2 = convert_anthropic_to_openai_messages(messages2)
        assert len(result2) == 1
        assert result2[0]["content"] == "" or result2[0]["content"] == []


class TestToolResultSerialization:
    """Test the _serialize_tool_result helper function directly."""

    def test_string_serialization(self):
        """Test serialization of string content."""
        result = _serialize_tool_result("Simple string", "test_req_id", {})
        assert result == "Simple string"

    def test_text_block_list_serialization(self):
        """Test serialization of list of text blocks."""
        content = [
            {"type": "text", "text": "Block 1"},
            {"type": "text", "text": "Block 2"},
        ]
        result = _serialize_tool_result(content, "test_req_id", {})
        assert result == "Block 1\nBlock 2"

    def test_dict_serialization(self):
        """Test serialization of dictionary content."""
        content = {"key": "value", "nested": {"data": 42}}
        result = _serialize_tool_result(content, "test_req_id", {})
        parsed = json.loads(result)
        assert parsed["key"] == "value"
        assert parsed["nested"]["data"] == 42

    def test_mixed_list_serialization(self):
        """Test serialization of mixed content lists."""
        content = [{"type": "text", "text": "Text block"}, {"not_text": "Other data"}]
        result = _serialize_tool_result(content, "test_req_id", {})
        assert "Text block" in result

    def test_non_serializable_content(self):
        """Test error handling for non-serializable content."""
        circular = {}
        circular["self"] = circular

        result = _serialize_tool_result(circular, "test_req_id", {})
        assert "error" in result.lower()
        assert "serialization" in result.lower()

    def test_empty_content_serialization(self):
        """Test serialization of empty content."""
        result1 = _serialize_tool_result("", "test_req_id", {})
        assert result1 == ""

        result2 = _serialize_tool_result([], "test_req_id", {})
        assert result2 == "[]"

        result3 = _serialize_tool_result({}, "test_req_id", {})
        assert result3 == "{}"

        result4 = _serialize_tool_result(None, "test_req_id", {})
        assert "null" in result4 or "none" in result4.lower()


class TestOpenAIToAnthropicConversion:
    """Test conversion from OpenAI to Anthropic format."""

    def test_text_response_conversion(self, mock_openai_response):
        """Test conversion of text responses."""
        openai_response = mock_openai_response(content="This is a test response.")
        original_model = "claude-3-opus-20240229"

        result = convert_openai_to_anthropic(openai_response, original_model)

        assert result.id == "msg_resp_123"
        assert result.model == original_model
        assert result.role == "assistant"
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == "This is a test response."
        assert result.stop_reason == "end_turn"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5

    def test_tool_call_response_conversion(self, mock_openai_response):
        """Test conversion of responses with tool calls."""
        tool_calls = [
            {
                "id": "call_456",
                "type": "function",
                "function": {
                    "name": "weather",
                    "arguments": '{"location": "New York", "units": "celsius"}',
                },
            }
        ]
        openai_response = mock_openai_response(
            content=None, tool_calls=tool_calls, finish_reason="tool_calls"
        )
        original_model = "claude-3-opus-20240229"

        result = convert_openai_to_anthropic(openai_response, original_model)

        assert result.id == "msg_resp_123"
        assert result.model == original_model
        assert result.role == "assistant"
        assert len(result.content) >= 1

        tool_use_blocks = [b for b in result.content if b.type == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0].id == "call_456"
        assert tool_use_blocks[0].name == "weather"
        assert tool_use_blocks[0].input["location"] == "New York"
        assert tool_use_blocks[0].input["units"] == "celsius"

        assert result.stop_reason == "tool_use"

    def test_tool_call_with_text_conversion(self, mock_openai_response):
        """Test conversion of responses with both text and tool calls."""
        tool_calls = [
            {
                "id": "call_789",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": '{"expression": "42 + 7"}',
                },
            }
        ]
        openai_response = mock_openai_response(
            content="Let me calculate that for you.",
            tool_calls=tool_calls,
            finish_reason="tool_calls",
        )
        original_model = "claude-3-opus-20240229"

        result = convert_openai_to_anthropic(openai_response, original_model)

        assert result.id == "msg_resp_123"
        assert result.model == original_model
        assert result.role == "assistant"
        assert len(result.content) == 2  

        assert result.content[0].type == "text"
        assert result.content[0].text == "Let me calculate that for you."

        assert result.content[1].type == "tool_use"
        assert result.content[1].id == "call_789"
        assert result.content[1].name == "calculator"
        assert result.content[1].input["expression"] == "42 + 7"

        assert result.stop_reason == "tool_use"

    def test_error_handling_in_tool_arguments(self, mock_openai_response):
        """Test handling of malformed tool arguments."""
        tool_calls = [
            {
                "id": "call_error",
                "type": "function",
                "function": {"name": "broken_tool", "arguments": "{invalid json}"},
            }
        ]
        openai_response = mock_openai_response(content=None, tool_calls=tool_calls)
        original_model = "claude-3-opus-20240229"

        result = convert_openai_to_anthropic(openai_response, original_model)

        assert len(result.content) >= 1
        tool_use_blocks = [b for b in result.content if b.type == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0].id == "call_error"
        assert tool_use_blocks[0].name == "broken_tool"
        assert "error" in tool_use_blocks[0].input or "raw" in tool_use_blocks[0].input

    def test_different_finish_reasons(self, mock_openai_response):
        """Test mapping of different finish reasons."""
        finish_reason_mapping = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "content_filter": "stop_sequence",
        }

        for openai_reason, anthropic_reason in finish_reason_mapping.items():
            openai_response = mock_openai_response(finish_reason=openai_reason)
            original_model = "claude-3-opus-20240229"

            result = convert_openai_to_anthropic(openai_response, original_model)

            assert result.stop_reason == anthropic_reason


class TestComplexContentScenarios:
    """Test complex content scenarios that combine multiple features."""

    def test_multi_turn_conversation(
        self, text_block, tool_use_block, tool_result_block
    ):
        """Test conversion of a multi-turn conversation with tools."""
        conversation = [
            Message(role="user", content="What's 135 + 7.5 divided by 2.5?"),
            Message(
                role="assistant",
                content=[
                    text_block("I'll calculate that for you."),
                    tool_use_block(
                        "tool_1", "calculator", {"expression": "135 + (7.5 / 2.5)"}
                    ),
                ],
            ),
            Message(
                role="user",
                content=[
                    text_block("Here's the result:"),
                    tool_result_block("tool_1", "138"),
                ],
            ),
            Message(
                role="assistant",
                content="The answer is 138. I calculated 135 + (7.5 / 2.5) which is 135 + 3 = 138.",
            ),
        ]

        result = convert_anthropic_to_openai_messages(conversation)

        assert len(result) >= 5  

        assert result[0]["role"] == "user"
        assert "What's 135 + 7.5 divided by 2.5?" in result[0]["content"]

        assistant_text_msg = [
            msg
            for msg in result
            if msg["role"] == "assistant"
            and isinstance(msg["content"], str)
            and "calculate" in msg["content"]
        ]
        assert len(assistant_text_msg) >= 1

        tool_call_msgs = [
            msg
            for msg in result
            if msg["role"] == "assistant" and msg.get("tool_calls") is not None
        ]
        assert len(tool_call_msgs) >= 1
        assert tool_call_msgs[0]["tool_calls"][0]["function"]["name"] == "calculator"

        tool_result_msgs = [msg for msg in result if msg.get("role") == "tool"]
        assert len(tool_result_msgs) >= 1
        assert (
            tool_result_msgs[0]["content"] == "138"
            or "138" in tool_result_msgs[0]["content"]
        )

        final_msg = [
            msg
            for msg in result
            if msg["role"] == "assistant"
            and isinstance(msg["content"], str)
            and "answer is 138" in msg["content"]
        ]
        assert len(final_msg) >= 1

    def test_mixed_content_types(
        self, text_block, image_block, tool_use_block, image_base64_data
    ):
        """Test conversion with multiple content types in the same conversation."""
        conversation = [
            Message(
                role="user",
                content=[
                    text_block("I have a question about this image:"),
                    image_block(image_base64_data),
                ],
            ),
            Message(
                role="assistant",
                content=[
                    text_block("Let me analyze that image."),
                    tool_use_block("tool_1", "image_analyzer", {"image_id": "img1"}),
                ],
            ),
        ]

        result = convert_anthropic_to_openai_messages(conversation)

        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][1]["type"] == "image_url"

        assistant_msgs = [msg for msg in result if msg["role"] == "assistant"]
        assert len(assistant_msgs) >= 2  

        text_content_msgs = [
            msg for msg in assistant_msgs if isinstance(msg.get("content"), str)
        ]
        assert len(text_content_msgs) >= 1
        assert "analyze" in text_content_msgs[0]["content"]

        tool_call_msgs = [
            msg for msg in assistant_msgs if msg.get("tool_calls") is not None
        ]
        assert len(tool_call_msgs) >= 1
        assert (
            tool_call_msgs[0]["tool_calls"][0]["function"]["name"] == "image_analyzer"
        )

    def test_nested_tool_result_content(self, text_block, tool_result_block):
        """Test conversion of complex nested structures in tool results."""
        nested_content = {
            "results": {
                "weather": {
                    "location": "New York",
                    "current": {
                        "temperature": 22,
                        "conditions": "Partly cloudy",
                        "precipitation": {"probability": 0.3, "type": "rain"},
                    },
                    "forecast": [
                        {"day": "Monday", "high": 24, "low": 18},
                        {"day": "Tuesday", "high": 26, "low": 19},
                    ],
                }
            }
        }

        nested_content_str = json.dumps(nested_content)

        messages = [
            Message(
                role="user",
                content=[
                    text_block("Here's the weather data:"),
                    tool_result_block("tool_123", nested_content_str),
                ],
            )
        ]

        result = convert_anthropic_to_openai_messages(messages)

        assert len(result) >= 2

        tool_messages = [msg for msg in result if msg.get("role") == "tool"]
        assert len(tool_messages) >= 1
        assert tool_messages[0]["tool_call_id"] == "tool_123"

        content_str = tool_messages[0]["content"]
        assert "New York" in content_str or "New York" in json.dumps(content_str)
        assert "temperature" in content_str or "temperature" in json.dumps(content_str)
