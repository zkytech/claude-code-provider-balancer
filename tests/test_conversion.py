import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from claude_proxy import conversion, models

# Fixtures for tool conversion tests
ANTHROPIC_TOOLS_FIXTURE = [
    models.Tool(
        name="dispatch_agent",
        description="Launch a new agent that has access to tools",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task for the agent to perform",
                }
            },
            "required": ["prompt"],
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    ),
    models.Tool(
        name="Bash",
        description="Executes a given bash command in a persistent shell session",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"},
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in milliseconds (max 600000)",
                },
                "description": {
                    "type": "string",
                    "description": "Clear, concise description of what this command does",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    ),
    models.Tool(
        name="GlobTool",
        description="Fast file pattern matching tool",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match files against",
                },
                "path": {"type": "string", "description": "The directory to search in"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    ),
]

OPENAI_TOOLS_FIXTURE = [
    {
        "type": "function",
        "function": {
            "name": "dispatch_agent",
            "description": "Launch a new agent that has access to tools",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task for the agent to perform",
                    }
                },
                "required": ["prompt"],
                "additionalProperties": False,
                "$schema": "http://json-schema.org/draft-07/schema#",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Executes a given bash command in a persistent shell session",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Optional timeout in milliseconds (max 600000)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Clear, concise description of what this command does",
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
                "$schema": "http://json-schema.org/draft-07/schema#",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GlobTool",
            "description": "Fast file pattern matching tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match files against",
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory to search in",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
                "$schema": "http://json-schema.org/draft-07/schema#",
            },
        },
    },
]


class MockDelta:
    def __init__(
        self,
        content: Optional[str] = None,
        role: Optional[str] = None,
        tool_calls: Optional[List[ChoiceDeltaToolCall]] = None,
    ):
        self.content = content
        self.role = role
        self.tool_calls = tool_calls


class MockChoiceChunk:
    def __init__(
        self,
        delta: MockDelta,
        finish_reason: Optional[str] = None,
        index: int = 0,
    ):
        self.delta = delta
        self.finish_reason = finish_reason
        self.index = index


class MockChatCompletionChunk:
    def __init__(
        self,
        id: str = "chatcmpl-mock-chunk-123",
        choices: Optional[List[MockChoiceChunk]] = None,
        model: str = "mock-model",
        object: str = "chat.completion.chunk",
        created: int = 1234567890,
    ):
        self.id = id
        self.choices = choices if choices is not None else []
        self.model = model
        self.object = object
        self.created = created


class MockFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, id: str, function: MockFunction, type: str = "function"):
        self.id = id
        self.function = function
        self.type = type


class MockMessage:
    def __init__(
        self,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[MockToolCall]] = None,
    ):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls


class MockChoice:
    def __init__(
        self,
        message: MockMessage,
        finish_reason: Optional[str] = "stop",
        index: int = 0,
    ):
        self.message = message
        self.finish_reason = finish_reason
        self.index = index


class MockUsage:
    def __init__(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class MockChatCompletion:
    def __init__(
        self,
        id: str = "chatcmpl-mock-123",
        choices: Optional[List[MockChoice]] = None,
        usage: Optional[MockUsage] = None,
        model: str = "mock-model",
        object: str = "chat.completion",
        created: int = 1234567890,
    ):
        self.id = id
        self.choices = choices if choices is not None else []
        self.usage = usage
        self.model = model
        self.object = object
        self.created = created

    def model_dump(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "choices": [
                {
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in choice.message.tool_calls
                        ]
                        if choice.message.tool_calls
                        else None,
                    },
                    "finish_reason": choice.finish_reason,
                    "index": choice.index,
                }
                for choice in self.choices
            ],
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            }
            if self.usage
            else None,
            "model": self.model,
            "object": self.object,
            "created": self.created,
        }




def test_anthropic_request_serialization():
    """Tests basic serialization of an Anthropic request."""
    data = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }
    request = models.MessagesRequest(**data)
    assert request.model == "claude-3-opus-20240229"
    assert request.max_tokens == 100
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"
    assert request.messages[0].content == "Hello"
    assert request.stream is False


def test_anthropic_request_with_complex_content():
    """Tests serialization with complex content blocks."""
    data = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Okay, I see the image."},
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "image_analyzer",
                        "input": {"detail": "high"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": "The image contains a single black pixel.",
                    }
                ],
            },
        ],
    }
    request = models.MessagesRequest(**data)
    assert len(request.messages) == 3
    assert isinstance(request.messages[0].content, list)
    assert isinstance(request.messages[1].content, list)
    assert isinstance(request.messages[2].content, list)
    assert request.messages[0].content[0].type == "text"
    assert request.messages[0].content[1].type == "image"
    assert request.messages[1].content[0].type == "text"
    assert request.messages[1].content[1].type == "tool_use"
    assert request.messages[2].content[0].type == "tool_result"


def test_anthropic_request_with_tools():
    """Tests serialization with tools and tool_choice."""
    data = {
        "model": "claude-3-sonnet-20240229",
        "max_tokens": 150,
        "messages": [{"role": "user", "content": "What's the weather in SF?"}],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get weather information",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            }
        ],
        "tool_choice": {"type": "auto"},
    }
    request = models.MessagesRequest(**data)
    assert request.tools is not None
    assert len(request.tools) == 1
    assert request.tools[0].name == "get_weather"
    assert request.tool_choice is not None
    assert request.tool_choice.type == "auto"


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
                    },
                )
            ],
            1,
            ["get_weather"],
        ),
        (ANTHROPIC_TOOLS_FIXTURE, 3, ["dispatch_agent", "Bash", "GlobTool"]),
        ([], 0, []),
        (None, 0, []),
    ],
)
def test_convert_anthropic_tools_to_openai_comprehensive(
    anthropic_tool_input: List[models.Tool],
    expected_count: int,
    expected_names: List[str],
):
    """Tests conversion of various Anthropic tool lists to OpenAI format."""
    openai_tools = conversion.convert_anthropic_tools_to_openai(anthropic_tool_input)

    if expected_count == 0:
        assert openai_tools is None
    else:
        assert openai_tools is not None
        assert len(openai_tools) == expected_count
        assert all(tool["type"] == "function" for tool in openai_tools)
        actual_names = [tool["function"]["name"] for tool in openai_tools]
        assert sorted(actual_names) == sorted(expected_names)
        if anthropic_tool_input:
            # Sort both lists by name to ensure comparison is correct
            sorted_anthropic = sorted(anthropic_tool_input, key=lambda x: x.name)
            sorted_openai = sorted(openai_tools, key=lambda x: x["function"]["name"])
            for i, tool in enumerate(sorted_anthropic):
                assert (
                    sorted_openai[i]["function"]["description"] == tool.description or ""
                )
                assert sorted_openai[i]["function"]["parameters"] == tool.input_schema


def test_comprehensive_tool_conversion_identity():
    """Ensures the fixture conversion matches the expected OpenAI fixture."""
    openai_tools = conversion.convert_anthropic_tools_to_openai(
        ANTHROPIC_TOOLS_FIXTURE
    )
    # Sort both lists by function name before comparing
    sorted_actual = sorted(openai_tools, key=lambda x: x["function"]["name"])
    sorted_expected = sorted(OPENAI_TOOLS_FIXTURE, key=lambda x: x["function"]["name"])
    assert sorted_actual == sorted_expected


def test_convert_anthropic_to_openai_messages_simple():
    """Tests conversion of simple user/assistant text messages."""
    anthropic_messages = [
        models.Message(role="user", content="Hello Claude"),
        models.Message(role="assistant", content="Hello! How can I help you?"),
    ]
    openai_messages = conversion.convert_anthropic_to_openai_messages(
        anthropic_messages
    )
    assert openai_messages == [
        {"role": "user", "content": "Hello Claude"},
        {"role": "assistant", "content": "Hello! How can I help you?"},
    ]


def test_convert_anthropic_to_openai_messages_with_complex_content():
    """Tests conversion involving image, tool use, and tool result blocks."""
    anthropic_messages = [
        models.Message(
            role="user",
            content=[
                models.ContentBlockText(type="text", text="Analyze this."),
                models.ContentBlockImage(
                    type="image",
                    source=models.ContentBlockImageSource(
                        type="base64", media_type="image/jpeg", data="base64data"
                    ),
                ),
            ],
        ),
        models.Message(
            role="assistant",
            content=[
                models.ContentBlockText(type="text", text="Okay, using the tool."),
                models.ContentBlockToolUse(
                    type="tool_use", id="tool_abc", name="analyzer", input={"level": 5}
                ),
            ],
        ),
        models.Message(
            role="user",
            content=[
                models.ContentBlockToolResult(
                    type="tool_result",
                    tool_use_id="tool_abc",
                    content=[{"type": "text", "text": "Analysis complete: High complexity."}],
                )
            ],
        ),
        models.Message(role="assistant", content="The analysis shows high complexity."),
    ]
    openai_messages = conversion.convert_anthropic_to_openai_messages(
        anthropic_messages
    )


    assert len(openai_messages) == 5

    assert openai_messages[0]["role"] == "user"
    assert isinstance(openai_messages[0]["content"], list)
    assert len(openai_messages[0]["content"]) == 2
    assert openai_messages[0]["content"][0] == {"type": "text", "text": "Analyze this."}
    assert openai_messages[0]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,base64data"},
    }

    assert openai_messages[1]["role"] == "assistant"
    assert openai_messages[1]["content"] == "Okay, using the tool."
    assert "tool_calls" not in openai_messages[1]

    assert openai_messages[2]["role"] == "assistant"
    assert openai_messages[2]["content"] is None
    assert "tool_calls" in openai_messages[2]
    assert len(openai_messages[2]["tool_calls"]) == 1
    assert openai_messages[2]["tool_calls"][0] == {
        "id": "tool_abc",
        "type": "function",
        "function": {"name": "analyzer", "arguments": '{"level": 5}'},
    }

    assert openai_messages[3]["role"] == "tool"
    assert openai_messages[3]["tool_call_id"] == "tool_abc"
    assert openai_messages[3]["content"] == "Analysis complete: High complexity."

    assert openai_messages[4]["role"] == "assistant"
    assert openai_messages[4]["content"] == "The analysis shows high complexity."


def test_convert_anthropic_tools_to_openai():
    """Tests conversion of a specific Anthropic tool list to OpenAI format."""
    anthropic_tools = [
        models.Tool(
            name="get_weather",
            description="Get weather information",
            input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
        )
    ]
    openai_tools = conversion.convert_anthropic_tools_to_openai(anthropic_tools)
    assert openai_tools == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather information",
                "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
            },
        }
    ]


@pytest.mark.parametrize(
    "tool_choice,expected_result",
    [
        (models.ToolChoice(type="auto"), "auto"),
        (models.ToolChoice(type="any"), "auto"),
        (
            models.ToolChoice(type="tool", name="get_weather"),
            {"type": "function", "function": {"name": "get_weather"}},
        ),
        (None, None),
    ],
)
def test_convert_anthropic_tool_choice_to_openai(tool_choice, expected_result):
    """Tests conversion of Anthropic tool_choice to OpenAI format."""
    openai_choice = conversion.convert_anthropic_tool_choice_to_openai(tool_choice)
    assert openai_choice == expected_result


def test_convert_openai_to_anthropic():
    """Tests conversion from OpenAI to Anthropic response format."""
    openai_response = MockChatCompletion(
        id="chatcmpl-test12345",
        choices=[
            MockChoice(
                message=MockMessage(
                    role="assistant", content="This is the main text response."
                ),
                finish_reason="stop",
            )
        ],
        usage=MockUsage(prompt_tokens=10, completion_tokens=20),
        model="gpt-mock- S",
    )

    anthropic_response = conversion.convert_openai_to_anthropic(
        openai_response, "claude-mock-small"
    )

    assert anthropic_response.id == "msg_chatcmpl-test12345"
    assert anthropic_response.type == "message"
    assert anthropic_response.role == "assistant"
    assert anthropic_response.model == "claude-mock-small"
    assert len(anthropic_response.content) == 1
    assert isinstance(anthropic_response.content[0], models.ContentBlockText)
    assert anthropic_response.content[0].text == "This is the main text response."
    assert anthropic_response.stop_reason == "end_turn"
    assert anthropic_response.usage.input_tokens == 10
    assert anthropic_response.usage.output_tokens == 20


def test_convert_openai_to_anthropic_with_tool_calls():
    """Tests conversion from OpenAI to Anthropic response format with tool calls."""
    openai_response = MockChatCompletion(
        id="chatcmpl-toolcall67890",
        choices=[
            MockChoice(
                message=MockMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        MockToolCall(
                            id="call_1",
                            function=MockFunction(
                                name="get_weather", arguments='{"location": "SF"}'
                            ),
                        ),
                        MockToolCall(
                            id="call_2",
                            function=MockFunction(
                                name="get_time", arguments='{"timezone": "PST"}'
                            ),
                        ),
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=MockUsage(prompt_tokens=30, completion_tokens=40),
        model="gpt-mock-L",
    )

    anthropic_response = conversion.convert_openai_to_anthropic(
        openai_response, "claude-mock-large"
    )

    assert anthropic_response.id == "msg_chatcmpl-toolcall67890"
    assert anthropic_response.model == "claude-mock-large"
    assert len(anthropic_response.content) == 2
    assert all(
        isinstance(block, models.ContentBlockToolUse)
        for block in anthropic_response.content
    )

    assert anthropic_response.content[0].type == "tool_use"
    assert anthropic_response.content[0].id == "call_1"
    assert anthropic_response.content[0].name == "get_weather"
    assert anthropic_response.content[0].input == {"location": "SF"}

    assert anthropic_response.content[1].type == "tool_use"
    assert anthropic_response.content[1].id == "call_2"
    assert anthropic_response.content[1].name == "get_time"
    assert anthropic_response.content[1].input == {"timezone": "PST"}

    assert anthropic_response.stop_reason == "tool_use"
    assert anthropic_response.usage.input_tokens == 30
    assert anthropic_response.usage.output_tokens == 40



anthropic_tool_sequence_messages = [
    models.Message(role="user", content="Use the echo tool with message 'hello world'"),
    models.Message(
        role="assistant",
        content=[
            models.ContentBlockToolUse(
                type="tool_use",
                id="echo_tool_123",
                name="echo_tool",
                input={"message": "hello world"},
            )
        ],
    ),
    models.Message(
        role="user",
        content=[
            models.ContentBlockToolResult(
                type="tool_result",
                tool_use_id="echo_tool_123",
                content="Echo: hello world",
            )
        ],
    ),
]

expected_openai_tool_sequence = [
    {"role": "user", "content": "Use the echo tool with message 'hello world'"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "echo_tool_123",
                "type": "function",
                "function": {
                    "name": "echo_tool",
                    "arguments": '{"message": "hello world"}',
                },
            }
        ],
    },
    {"role": "tool", "tool_call_id": "echo_tool_123", "content": "Echo: hello world"},
]

mock_openai_response_after_tool = MockChatCompletion(
    id="chatcmpl-after-tool-resp",
    choices=[
        MockChoice(
            message=MockMessage(
                role="assistant",
                content="Okay, the tool echoed 'Echo: hello world'. What should I do next?",
            ),
            finish_reason="stop",
        )
    ],
    usage=MockUsage(prompt_tokens=50, completion_tokens=25),
    model="gpt-mock-tool-test",
)


def test_tool_use_result_sequence_conversion():
    """Verify the Anthropic tool sequence converts correctly to OpenAI format."""
    openai_messages = conversion.convert_anthropic_to_openai_messages(
        anthropic_tool_sequence_messages
    )
    assert openai_messages == expected_openai_tool_sequence


def test_tool_use_result_sequence_non_streaming():
    """
    Tests the non-streaming case: ensures the response after a tool result
    doesn't incorrectly repeat the tool_use block.
    """
    openai_response = mock_openai_response_after_tool
    original_model = "claude-test-model"

    anthropic_response = conversion.convert_openai_to_anthropic(
        openai_response, original_model
    )

    assert anthropic_response.id == f"msg_{openai_response.id}"
    assert anthropic_response.model == original_model
    assert anthropic_response.stop_reason == "end_turn"
    assert len(anthropic_response.content) == 1

    assert isinstance(anthropic_response.content[0], models.ContentBlockText)
    assert anthropic_response.content[0].type == "text"
    assert anthropic_response.content[0].text == "Okay, the tool echoed 'Echo: hello world'. What should I do next?"


@pytest.mark.asyncio
async def test_tool_use_result_sequence_streaming():
    """
    Tests the streaming case: ensures the SSE events after a tool result
    don't incorrectly repeat the tool_use block.
    """
    original_model = "claude-test-model-stream"
    request_id = "stream_req_abc"
    initial_input_tokens = 50

    async def mock_openai_stream_after_tool() -> AsyncGenerator[MockChatCompletionChunk, None]:
        yield MockChatCompletionChunk(
            choices=[MockChoiceChunk(delta=MockDelta(role="assistant"))]
        )
        yield MockChatCompletionChunk(
            choices=[MockChoiceChunk(delta=MockDelta(content="Okay, the tool echoed "))]
        )
        yield MockChatCompletionChunk(
            choices=[MockChoiceChunk(delta=MockDelta(content="'Echo: hello world'. "))]
        )
        yield MockChatCompletionChunk(
            choices=[MockChoiceChunk(delta=MockDelta(content="What should I do next?"))]
        )
        yield MockChatCompletionChunk(
            choices=[MockChoiceChunk(delta=MockDelta(content=None), finish_reason="stop")]
        )

    sse_events = []
    openai_stream_cast = mock_openai_stream_after_tool()
    async for event_str in conversion.handle_streaming_response(
        openai_stream_cast,
        original_model,
        initial_input_tokens,
        request_id,
    ):
        sse_events.append(event_str)

    assert len(sse_events) > 3

    assert sse_events[0].startswith("event: message_start")
    start_data = json.loads(sse_events[0].split("data: ")[1])
    assert start_data["type"] == "message_start"
    assert start_data["message"]["model"] == original_model
    assert start_data["message"]["usage"]["input_tokens"] == initial_input_tokens

    text_block_start_found = False
    for event in sse_events:
        if event.startswith("event: content_block_start"):
            data = json.loads(event.split("data: ")[1])
            assert data["content_block"]["type"] == "text"
            text_block_start_found = True
            break
    assert text_block_start_found, "Did not find content_block_start for text"

    aggregated_text = ""
    for event in sse_events:
        if event.startswith("event: content_block_delta"):
            data = json.loads(event.split("data: ")[1])
            assert data["delta"]["type"] == "text_delta"
            aggregated_text += data["delta"]["text"]
    assert aggregated_text == "Okay, the tool echoed 'Echo: hello world'. What should I do next?"

    text_block_stop_found = False
    for event in sse_events:
        if event.startswith("event: content_block_stop"):
             data = json.loads(event.split("data: ")[1])
             assert data["index"] == 0
             text_block_stop_found = True
             break
    assert text_block_stop_found, "Did not find content_block_stop for text block"

    message_delta_found = False
    for event in sse_events:
        if event.startswith("event: message_delta"):
            data = json.loads(event.split("data: ")[1])
            assert data["delta"]["stop_reason"] == "end_turn"
            message_delta_found = True
            break
    assert message_delta_found, "Did not find message_delta event"

    assert sse_events[-1].startswith("event: message_stop")

    for event in sse_events:
        if event.startswith("event: content_block_start"):
            data = json.loads(event.split("data: ")[1])
            assert data["content_block"]["type"] != "tool_use", "Incorrectly found tool_use start event"
        if event.startswith("event: content_block_delta"):
             data = json.loads(event.split("data: ")[1])
             assert data["delta"]["type"] != "input_json_delta", "Incorrectly found tool_use delta event"
