# Comprehensive Mapping Between Anthropic Messages API and OpenAI Chat Completions API

<!--toc:start-->
- [Comprehensive Mapping Between Anthropic Messages API and OpenAI Chat Completions API](#comprehensive-mapping-between-anthropic-messages-api-and-openai-chat-completions-api)
  - [Overview](#overview)
  - [API Endpoints](#api-endpoints)
  - [Count Tokens Endpoint](#count-tokens-endpoint)
  - [Request Mapping](#request-mapping)
    - [Endpoint Parameters](#endpoint-parameters)
    - [Request Body Parameters](#request-body-parameters)
    - [Messages and Content Blocks](#messages-and-content-blocks)
      - [Anthropic Messages Format](#anthropic-messages-format)
      - [OpenAI Messages Format](#openai-messages-format)
      - [Mapping Messages](#mapping-messages)
    - [System Prompts](#system-prompts)
    - [Tools and Functions](#tools-and-functions)
      - [Tool Definitions](#tool-definitions)
      - [Mapping Tool Definitions](#mapping-tool-definitions)
      - [Tool Usage](#tool-usage)
      - [Mapping Tool Choices](#mapping-tool-choices)
      - [Tool Calls in Messages](#tool-calls-in-messages)
      - [Mapping Tool Calls](#mapping-tool-calls)
    - [Streaming Responses](#streaming-responses)
      - [Anthropic Streaming](#anthropic-streaming)
      - [OpenAI Streaming](#openai-streaming)
      - [Mapping Streaming Responses](#mapping-streaming-responses)
  - [Response Mapping](#response-mapping)
    - [Response Body Structure](#response-body-structure)
      - [Anthropic Response Structure](#anthropic-response-structure)
      - [OpenAI Response Structure](#openai-response-structure)
    - [Content Blocks and Messages](#content-blocks-and-messages)
      - [Mapping Assistant Responses](#mapping-assistant-responses)
    - [Stop Reasons and Finish Reasons](#stop-reasons-and-finish-reasons)
      - [Mapping Stop/Finish Reasons](#mapping-stopfinish-reasons)
    - [Usage Statistics](#usage-statistics)
      - [Mapping Usage](#mapping-usage)
  - [Error Handling](#error-handling)
    - [Error Response Structures](#error-response-structures)
      - [Anthropic Error Structure](#anthropic-error-structure)
      - [OpenAI Error Structure](#openai-error-structure)
    - [HTTP Status Code Mapping](#http-status-code-mapping)
    - [API Client Errors](#api-client-errors)
    - [Implementation Considerations](#implementation-considerations)
  - [Important Considerations](#important-considerations)
<!--toc:end-->

This document provides a detailed mapping between the Anthropic Messages API and the OpenAI Chat Completions API. It outlines how to translate requests and responses between the two APIs, ensuring a 100% accurate correspondence. This mapping is essential for the proxy server that translates Anthropic HTTP requests to OpenAI requests and vice versa.

## Overview

The purpose of this document is to map each aspect of the Anthropic Messages API to the corresponding element in the OpenAI Chat Completions API. This includes request parameters, message formats, tools (functions), streaming mechanisms, and response structures. The goal is to facilitate accurate translation between the two APIs for seamless proxying.

---

## API Endpoints

- **Anthropic Messages API Endpoint:**

  ```
  POST /v1/messages
  ```

- **OpenAI Chat Completions API Endpoint:**

  ```
  POST /v1/chat/completions
  ```

---

## Count Tokens Endpoint

Anthropic provides an endpoint for token counting, for example:

```
POST /v1/messages/count_tokens
```

This calculates how many tokens the input would consume.

OpenAI does not provide a direct HTTP endpoint for token counting. Instead, token usage can be observed during chat completion calls, or estimated using the `tiktoken` library. Ensure your proxy implements any necessary logic to count tokens consistently across both platforms.

---

## Request Mapping

### Endpoint Parameters

Anthropic and OpenAI APIs use similar authentication mechanisms and headers.

- **Authorization Header:**
  - Anthropic: `x-api-key: YOUR_ANTHROPIC_API_KEY`
  - OpenAI: `Authorization: Bearer YOUR_OPENAI_API_KEY`
- **API Version Header:**
  - Anthropic: `anthropic-version: VERSION_STRING`
  - OpenAI: Not required in the same way; versions are tied to the model specified.

### Request Body Parameters

Below is a comprehensive mapping of request body parameters:

| Anthropic Parameter | OpenAI Parameter       | Notes                                                                                           |
| ------------------- | ---------------------- | ----------------------------------------------------------------------------------------------- |
| `model`             | `model`                | Direct mapping. Model names differ between providers and need to be translated appropriately.   |
| `messages`          | `messages`             | Message format differs; requires conversion of roles and content structure.                     |
| `system`            | Included in `messages` | Anthropic uses a separate `system` parameter; OpenAI includes system prompts within `messages`. |
| `max_tokens`        | `max_tokens`           | Direct mapping, but ensure values are within the limits of the target model.                    |
| `temperature`       | `temperature`          | Direct mapping.                                                                                 |
| `top_p`             | `top_p`                | Direct mapping.                                                                                 |
| `top_k`             | Not supported          | Anthropic-specific; needs handling or omission when proxying to OpenAI.                         |
| `stream`            | `stream`               | Direct mapping.                                                                                 |
| `stop_sequences`    | `stop`                 | Convert Anthropic's array of stop sequences to OpenAI's `stop` parameter.                       |
| `tools`             | `functions`            | Tools in Anthropic map to functions in OpenAI. Requires conversion of definitions.              |
| `tool_choice`       | `function_call`        | Anthropic's `tool_choice` maps to OpenAI's `function_call` parameter.                           |
| `metadata`          | `metadata`             | OpenAI does not support this; may need to be stored or handled separately.                      |
| `thinking`          | Not supported          | Anthropic-specific feature; cannot be directly mapped to OpenAI.                                |
| `stop_sequences`    | `stop`                 | Convert directly.                                                                               |
| `stream_options`    | `stream_options`       | May need to adjust for equivalent streaming parameters if available.                            |
| `user`              | `user`                 | Optional in OpenAI; can pass through if provided.                                               |

### Messages and Content Blocks

#### Anthropic Messages Format

Anthropic messages can contain structured content with multiple content blocks, including text, images, and tool interactions.

Example Anthropic message:

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Hello, Claude"
    },
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "<base64-encoded-data>"
      }
    }
  ]
}
```

#### OpenAI Messages Format

OpenAI messages are simpler and generally contain a `role` and a `content` field, with optional `function_call`.

Example OpenAI message:

```json
{
  "role": "user",
  "content": "Hello, Claude"
}
```

#### Mapping Messages

- **Roles:**
  - Anthropic roles `user`, `assistant` map directly to OpenAI roles.
  - Anthropic does not support a `system` role within `messages`; instead, it uses a separate `system` parameter.
- **Content Conversion:**
  - **Text Blocks:** Concatenate text blocks into a single string for OpenAI's `content` field.
  - **Image Blocks:** Images are not directly supported in OpenAI's Chat API. Need to handle or omit.
  - **Tool Use and Tool Result Blocks:**
    - Convert `tool_use` blocks into OpenAI's `function_call` in assistant messages.
    - Convert `tool_result` blocks into `assistant` messages with `content` containing the tool result.

### System Prompts

Anthropic uses a separate `system` parameter for system prompts, which can be a string or a list of `SystemContent` blocks.

- **Mapping to OpenAI:**
  - Prepend the system prompt as a `system` role message in the OpenAI `messages` array.
  - If `system` is a string, create a `system` message with that content.
  - If `system` is a list of content blocks, concatenate text blocks into the `system` message `content`.

### Tools and Functions

#### Tool Definitions

- **Anthropic `tools`:**
  - An array of tool definitions, each with `name`, `description`, and `input_schema`.
- **OpenAI `functions`:**
  - An array of function definitions, each with `name`, `description`, and `parameters`.

#### Mapping Tool Definitions

- Directly map each Anthropic tool to an OpenAI function:
  - `name` maps to `name`.
  - `description` maps to `description`.
  - `input_schema` maps to `parameters`.

#### Tool Usage

- **Anthropic `tool_choice`:**
  - Dictates how the model should use the provided tools (`auto`, `any`, `tool`, `none`).
- **OpenAI `function_call`:**
  - Controls which function the model should call (`auto`, `none`, or specify a function by name).

#### Mapping Tool Choices

- Map `tool_choice` to `function_call` as follows:

| Anthropic `tool_choice`                     | OpenAI `function_call`      |
| ------------------------------------------- | --------------------------- |
| `"auto"`                                    | `"auto"`                    |
| `"any"`                                     | `"auto"`                    |
| `{"type": "tool", "name": "function_name"}` | `{"name": "function_name"}` |
| `"none"`                                    | `"none"`                    |

#### Tool Calls in Messages

- **Anthropic `tool_use` Content Blocks (Assistant messages):**
  - Represented as blocks with `type`: `"tool_use"`, containing `id`, `name`, `input`.
- **OpenAI `function_call` in Assistant messages:**
  - Include a `function_call` field with `name` and `arguments`.

#### Mapping Tool Calls

- Convert `tool_use` blocks into OpenAI assistant messages with:

```json
{
  "role": "assistant",
  "content": null,
  "function_call": {
    "name": "tool_name",
    "arguments": "{...}" // JSON stringified arguments
  }
}
```

- Ensure that `content` is `null` when `function_call` is used.

### Streaming Responses

Both Anthropic and OpenAI support streaming responses using Server-Sent Events (SSE), but with significantly different event structures and sequences.

#### Anthropic Streaming

Anthropic uses a structured event-based approach with specific event types:

1. **Event Sequence**:

   - `message_start` - Initiates the streaming session with message metadata
   - `ping` - Periodic heartbeat events
   - `content_block_start` - Marks the beginning of a content block (text or tool_use)
   - `content_block_delta` - Delivers incremental updates to a content block
     - Text blocks use `text_delta` type
     - Tool blocks use `input_json_delta` type for arguments
   - `content_block_stop` - Marks the end of a content block
   - `message_delta` - Updates message metadata (e.g., stop_reason, usage)
   - `message_stop` - Concludes the streaming session

2. **Event Structure**:

   ```
   event: message_start
   data: {"type": "message_start", "message": {"id": "msg_...", "role": "assistant", ...}}

   event: content_block_start
   data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

   event: content_block_delta
   data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}
   ```

3. **Multiple Content Blocks**:
   - Text content is always index 0
   - Tool calls are separate blocks with their own indices
   - Each block has discrete start/delta/stop events

#### OpenAI Streaming

OpenAI uses a simpler approach with a single event type containing delta updates:

1. **Event Sequence**:

   - Single stream of `chat.completion.chunk` objects
   - No explicit event types or named events
   - First chunk typically contains role only
   - Subsequent chunks contain content or tool_calls deltas
   - Final chunk contains finish_reason

2. **Event Structure**:

   ```
   data: {"id": "...", "object": "chat.completion.chunk", "choices": [{"delta": {"role": "assistant"}, ...}]}

   data: {"id": "...", "object": "chat.completion.chunk", "choices": [{"delta": {"content": "Hello"}, ...}]}

   data: {"id": "...", "object": "chat.completion.chunk", "choices": [{"delta": {}, "finish_reason": "stop"}]}
   ```

3. **Tool Call Structure**:
   - Tool calls sent as incremental deltas to `tool_calls` array
   - Arguments often streamed in partial JSON fragments

#### Mapping Streaming Responses

To convert OpenAI streaming to Anthropic streaming format:

1. **Initialization**:

   - Upon first OpenAI chunk, generate Anthropic `message_start` event
   - Send initial `ping` event

2. **Text Content Handling**:

   - When first text content delta arrives, send `content_block_start` with index 0
   - Convert each OpenAI content delta to Anthropic `content_block_delta` events
   - When content completes, send `content_block_stop` event

3. **Tool Call Handling**:

   - When tool_calls first appear, generate `content_block_start` with tool metadata
   - Convert each function argument delta to `content_block_delta` with `input_json_delta` type
   - Track and accumulate partial JSON to ensure complete tool input
   - Send `content_block_stop` for each tool when complete

4. **Completion Handling**:

   - Map OpenAI finish_reason to Anthropic stop_reason
   - Send `message_delta` with final metadata
   - Send `message_stop` to conclude stream

5. **Special Considerations**:
   - Handle multi-tool scenarios by tracking each tool separately
   - Ensure proper index management across different content block types
   - Manage partial/incomplete JSON in tool argument streams
   - Estimate token counts for usage statistics

---

## Response Mapping

### Response Body Structure

#### Anthropic Response Structure

```json
{
  "id": "msg_...",
  "model": "model_name",
  "content": [...],  // Array of content blocks
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

#### OpenAI Response Structure

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "model_name",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

### Content Blocks and Messages

- **Anthropic Content Blocks:**
  - Types include `text`, `image`, `tool_use`, `tool_result`, etc.
- **OpenAI Messages:**
  - Assistant messages may contain `content`, `function_call`, or both.

#### Mapping Assistant Responses

- **Text Content:**
  - Extract `content` from OpenAI assistant message and convert to an Anthropic `ContentBlockText`.
- **Function Calls:**
  - Convert OpenAI `function_call` to an Anthropic `ContentBlockToolUse`.
- **Tool Results:**
  - Handle tool results by incorporating them into subsequent messages as needed.

### Stop Reasons and Finish Reasons

- **Anthropic `stop_reason`:**
  - Possible values: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `error`.
- **OpenAI `finish_reason`:**
  - Possible values: `stop`, `length`, `function_call`, `content_filter`.

#### Mapping Stop/Finish Reasons

| OpenAI `finish_reason` | Anthropic `stop_reason` |
| ---------------------- | ----------------------- |
| `"stop"`               | `"end_turn"`            |
| `"length"`             | `"max_tokens"`          |
| `"function_call"`      | `"tool_use"`            |
| `"content_filter"`     | `"stop_sequence"`       |
| `null`                 | `null` or infer         |

### Usage Statistics

- **Anthropic `usage`:**
  - Contains `input_tokens` and `output_tokens`.
- **OpenAI `usage`:**
  - Contains `prompt_tokens`, `completion_tokens`, and `total_tokens`.

#### Mapping Usage

- Map `prompt_tokens` to `input_tokens`.
- Map `completion_tokens` to `output_tokens`.

---

## Error Handling

### Error Response Structures

#### Anthropic Error Structure

```json
{
  "type": "error",
  "error": {
    "type": "not_found_error",
    "message": "The requested resource could not be found."
  }
}
```

#### OpenAI Error Structure

```json
{
  "error": {
    "message": "The requested resource could not be found.",
    "type": "invalid_request_error",
    "param": null,
    "code": null
  }
}
```

### HTTP Status Code Mapping

| Anthropic HTTP Code | Anthropic Error Type    | OpenAI HTTP Code | OpenAI Error Type                                  |
| ------------------- | ----------------------- | ---------------- | -------------------------------------------------- |
| 400                 | `invalid_request_error` | 400              | `BadRequestError` (formerly `InvalidRequestError`) |
| 401                 | `authentication_error`  | 401              | `AuthenticationError`                              |
| 403                 | `permission_error`      | 403              | `PermissionDeniedError`                            |
| 404                 | `not_found_error`       | 404              | `NotFoundError`                                    |
| 413                 | `request_too_large`     | 400              | `BadRequestError`                                  |
| 429                 | `rate_limit_error`      | 429              | `RateLimitError`                                   |
| 500                 | `api_error`             | 500              | `InternalServerError`                              |
| 529                 | `overloaded_error`      | 503              | `ServiceUnavailableError`                          |

### API Client Errors

Ensure proper translation between client library error types:

| OpenAI Python Error        | Anthropic Equivalent Context     |
| -------------------------- | -------------------------------- |
| `APIConnectionError`       | Network connectivity issues      |
| `APITimeoutError`          | Request timeout issues           |
| `RateLimitError`           | Rate limiting information        |
| `ConflictError`            | Resource contention issues       |
| `UnprocessableEntityError` | Invalid but well-formed requests |

### Implementation Considerations

- Preserve error messages when translating between APIs to maintain context
- Include request IDs in responses for troubleshooting
- Add proxy-specific context when helpful (e.g., "Error from upstream provider: ...")
- Handle streaming errors appropriately, which may occur after a 200 response
- Implement exponential backoff for retry-eligible errors

## Important Considerations

- **Token Limits:**
  - Be mindful of the token limits of the target OpenAI model when forwarding requests.
- **Unsupported Features:**
  - Anthropic features like `thinking` and `top_k` are not supported by OpenAI and need to be handled appropriately.
- **Content Types:**
  - OpenAI Chat API does not support image inputs or outputs in the same way Anthropic does. May need to omit or handle image content blocks specially.
