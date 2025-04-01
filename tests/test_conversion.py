"""
Unit tests for the conversion module.
"""

import json
from typing import List

import pytest

from claude_proxy import conversion, models


def test_anthropic_request_serialization():
    """Tests serializing raw Anthropic request JSON into MessagesRequest model."""
    raw_request = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Hello, world!"}],
        "system": "You are Claude, a helpful AI assistant.",
        "temperature": 0.7,
        "top_p": 0.9,
    }

    request = models.MessagesRequest.model_validate(raw_request)

    assert request.model == "claude-3-opus-20240229"
    assert request.max_tokens == 1024
    assert request.temperature == 0.7
    assert request.top_p == 0.9
    assert request.system == "You are Claude, a helpful AI assistant."
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"
    assert request.messages[0].content == "Hello, world!"


def test_anthropic_request_with_complex_content():
    """Tests serializing Anthropic request with complex content blocks."""
    raw_request = {
        "model": "claude-3-sonnet-20240229",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "base64encodeddata",
                        },
                    },
                ],
            }
        ],
    }

    request = models.MessagesRequest.model_validate(raw_request)

    assert request.model == "claude-3-sonnet-20240229"
    assert request.max_tokens == 1024
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"
    assert isinstance(request.messages[0].content, list)
    assert len(request.messages[0].content) == 2
    assert request.messages[0].content[0].type == "text"
    assert request.messages[0].content[0].text == "What's in this image?"
    assert request.messages[0].content[1].type == "image"
    assert request.messages[0].content[1].source.type == "base64"
    assert request.messages[0].content[1].source.media_type == "image/jpeg"
    assert request.messages[0].content[1].source.data == "base64encodeddata"


def test_anthropic_request_with_tools():
    """Tests serializing Anthropic request with tools and tool_choice."""
    raw_request = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "What's the weather like in San Francisco?"}
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state",
                        }
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "get_time",
                "description": "Get current time for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state",
                        },
                        "timezone": {
                            "type": "string",
                            "description": "The timezone code",
                        },
                    },
                    "required": ["location"],
                },
            },
        ],
        "tool_choice": {"type": "auto"},
    }

    request = models.MessagesRequest.model_validate(raw_request)

    assert request.model == "claude-3-opus-20240229"
    assert len(request.tools) == 2
    assert request.tools[0].name == "get_weather"
    assert request.tools[0].description == "Get current weather for a location"
    assert "location" in request.tools[0].input_schema["properties"]

    assert request.tools[1].name == "get_time"
    assert request.tools[1].description == "Get current time for a location"
    assert request.tools[1].input_schema["required"] == ["location"]

    assert request.tool_choice.type == "auto"
    assert request.tool_choice.name is None


@pytest.mark.parametrize(
    "anthropic_tool_input,expected_count,expected_names",
    [
        (
            [
                models.Tool(
                    name="get_weather",
                    description="Get weather information",
                    input_schema={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                )
            ],
            1,
            ["get_weather"],
        ),
        (
            [
                models.Tool(
                    name="get_weather",
                    description="Get weather information",
                    input_schema={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                ),
                models.Tool(
                    name="calculator",
                    description="Perform calculations",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                            "precision": {"type": "integer", "default": 2},
                        },
                        "required": ["expression"],
                    },
                ),
            ],
            2,
            ["get_weather", "calculator"],
        ),
        (
            [
                models.Tool(
                    name="database_query",
                    description="Query a database",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "options": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer"},
                                    "offset": {"type": "integer"},
                                    "sort": {"type": "string", "enum": ["asc", "desc"]},
                                },
                            },
                        },
                        "required": ["query"],
                    },
                )
            ],
            1,
            ["database_query"],
        ),
    ],
)
def test_convert_anthropic_tools_to_openai_comprehensive(
    anthropic_tool_input: List[models.Tool],
    expected_count: int,
    expected_names: List[str],
):
    """Tests comprehensive conversion of various Anthropic tool formats to OpenAI."""

    result = conversion.convert_anthropic_tools_to_openai(anthropic_tool_input)

    assert len(result) == expected_count

    for i, name in enumerate(expected_names):
        assert result[i]["type"] == "function"
        assert result[i]["function"]["name"] == name
        assert "description" in result[i]["function"]
        assert "parameters" in result[i]["function"]

        anthropic_schema = anthropic_tool_input[i].input_schema
        openai_parameters = result[i]["function"]["parameters"]

        assert openai_parameters["type"] == anthropic_schema["type"]

        if "properties" in anthropic_schema:
            assert "properties" in openai_parameters
            for prop_name, prop_schema in anthropic_schema["properties"].items():
                assert prop_name in openai_parameters["properties"]

        if "required" in anthropic_schema:
            assert "required" in openai_parameters
            assert openai_parameters["required"] == anthropic_schema["required"]


def test_comprehensive_tool_conversion_identity():
    """
    Tests that converting Anthropic tools to OpenAI and back would preserve
    all the essential information (identity test).
    """
    anthropic_tools = conversion.ANTHROPIC_TOOLS_FIXTURE
    openai_tools = conversion.convert_anthropic_tools_to_openai(anthropic_tools)

    assert len(openai_tools) == len(conversion.OPENAI_TOOLS_FIXTURE)

    for i, tool in enumerate(openai_tools):
        assert tool["type"] == "function"
        assert tool["function"]["name"] == anthropic_tools[i].name

        if anthropic_tools[i].description:
            assert tool["function"]["description"] == anthropic_tools[i].description

        assert tool["function"]["parameters"] == anthropic_tools[i].input_schema


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
