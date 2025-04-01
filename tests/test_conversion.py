"""
Unit tests for the conversion module.
"""

import json

import pytest

from claude_proxy import conversion, models


def test_convert_anthropic_to_openai_messages_simple():
    """Tests basic conversion of Anthropic messages to OpenAI format."""
    anthropic_messages = [
        models.Message(role="user", content="Hello, world!"),
        models.Message(role="assistant", content="Hi there!"),
    ]
    anthropic_system = "You are a helpful assistant named Claude."

    result = conversion.convert_anthropic_to_openai_messages(
        anthropic_messages, anthropic_system
    )

    assert len(result) == 3
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a helpful assistant named Claude."
    assert result[1]["role"] == "user"
    assert result[1]["content"] == "Hello, world!"
    assert result[2]["role"] == "assistant"
    assert result[2]["content"] == "Hi there!"


def test_convert_anthropic_to_openai_messages_with_complex_content():
    """Tests conversion with content blocks."""
    text_block = models.ContentBlockText(type="text", text="What is this image?")

    image_source = models.ContentBlockImageSource(
        type="base64", media_type="image/jpeg", data="base64encodedstring"
    )

    image_block = models.ContentBlockImage(type="image", source=image_source)

    anthropic_messages = [
        models.Message(role="user", content=[text_block, image_block]),
        models.Message(role="assistant", content="This appears to be a photograph."),
    ]

    result = conversion.convert_anthropic_to_openai_messages(anthropic_messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 2
    assert result[0]["content"][0]["type"] == "text"
    assert result[0]["content"][1]["type"] == "image_url"
    assert "base64encodedstring" in result[0]["content"][1]["image_url"]["url"]

    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "This appears to be a photograph."


def test_convert_anthropic_tools_to_openai():
    """Tests conversion of Anthropic tool definitions to OpenAI format."""
    anthropic_tools = [
        models.Tool(
            name="get_weather",
            description="Get weather information",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"],
            },
        )
    ]

    result = conversion.convert_anthropic_tools_to_openai(anthropic_tools)

    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "get_weather"
    assert result[0]["function"]["description"] == "Get weather information"
    assert "location" in result[0]["function"]["parameters"]["properties"]
    assert result[0]["function"]["parameters"]["required"] == ["location"]


@pytest.mark.parametrize(
    "tool_choice,expected_result",
    [
        (models.ToolChoice(type="auto"), "auto"),
        (models.ToolChoice(type="any"), "auto"),
        (
            models.ToolChoice(type="tool", name="get_weather"),
            {"type": "function", "function": {"name": "get_weather"}},
        ),
    ],
)
def test_convert_anthropic_tool_choice_to_openai(tool_choice, expected_result):
    """Tests conversion of Anthropic tool choice to OpenAI format."""
    result = conversion.convert_anthropic_tool_choice_to_openai(tool_choice)
    assert result == expected_result


def test_convert_openai_to_anthropic():
    """Tests conversion from OpenAI to Anthropic response format."""
    openai_response = {
        "id": "chatcmpl-123",
        "choices": [
            {
                "message": {
                    "content": "I am Claude, an AI assistant.",
                    "tool_calls": [],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }

    class MockResponse:
        def __init__(self, data):
            self.id = data["id"]
            self.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": data["choices"][0]["message"]["content"],
                                "tool_calls": data["choices"][0]["message"][
                                    "tool_calls"
                                ],
                            },
                        ),
                        "finish_reason": data["choices"][0]["finish_reason"],
                    },
                )
            ]
            self.usage = type(
                "Usage",
                (),
                {
                    "prompt_tokens": data["usage"]["prompt_tokens"],
                    "completion_tokens": data["usage"]["completion_tokens"],
                },
            )

        def model_dump(self):
            return {
                "id": self.id,
                "choices": [
                    {
                        "message": {
                            "content": self.choices[0].message.content,
                            "tool_calls": self.choices[0].message.tool_calls,
                        },
                        "finish_reason": self.choices[0].finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": self.usage.prompt_tokens,
                    "completion_tokens": self.usage.completion_tokens,
                },
            }

    mock_response = MockResponse(openai_response)

    original_model = "claude-3-opus-20240229"
    result = conversion.convert_openai_to_anthropic(mock_response, original_model)

    assert result.id.startswith("msg_")
    assert result.type == "message"
    assert result.role == "assistant"
    assert result.model == original_model
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert result.content[0].text == "I am Claude, an AI assistant."
    assert result.stop_reason == "end_turn"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20


def test_convert_openai_to_anthropic_with_tool_calls():
    """Tests conversion from OpenAI to Anthropic response format with tool calls."""
    openai_response = {
        "id": "chatcmpl-456",
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": json.dumps(
                                    {"location": "San Francisco, CA"}
                                ),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25},
    }

    class MockResponse:
        def __init__(self, data):
            self.id = data["id"]
            self.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": data["choices"][0]["message"].get("content"),
                                "tool_calls": [
                                    type(
                                        "ToolCall",
                                        (),
                                        {
                                            "id": tc["id"],
                                            "type": tc["type"],
                                            "function": type(
                                                "Function",
                                                (),
                                                {
                                                    "name": tc["function"]["name"],
                                                    "arguments": tc["function"][
                                                        "arguments"
                                                    ],
                                                },
                                            ),
                                        },
                                    )
                                    for tc in data["choices"][0]["message"].get(
                                        "tool_calls", []
                                    )
                                ],
                            },
                        ),
                        "finish_reason": data["choices"][0]["finish_reason"],
                    },
                )
            ]
            self.usage = type(
                "Usage",
                (),
                {
                    "prompt_tokens": data["usage"]["prompt_tokens"],
                    "completion_tokens": data["usage"]["completion_tokens"],
                },
            )

        def model_dump(self):
            return openai_response

    mock_response = MockResponse(openai_response)

    original_model = "claude-3-opus-20240229"
    result = conversion.convert_openai_to_anthropic(mock_response, original_model)

    assert result.id.startswith("msg_")
    assert result.type == "message"
    assert result.role == "assistant"
    assert result.model == original_model
    assert result.stop_reason == "tool_use"

    assert len(result.content) == 1
    tool_use_block = result.content[0]
    assert tool_use_block.type == "tool_use"
    assert tool_use_block.name == "get_weather"
    assert tool_use_block.input == {"location": "San Francisco, CA"}
    assert tool_use_block.id is not None
