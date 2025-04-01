"""
Tests provider-specific modifications to requests.
"""

import copy

from claude_proxy.provider_mods import (_modify_tool_schema_for_gemini,
                                        apply_provider_modifications)


def test_gemini_empty_properties_handling():
    """Test that empty properties are handled for Gemini BatchTool."""
    schema = {
        "type": "object",
        "properties": {
            "invocations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        }
                    },
                },
            }
        },
    }

    original = copy.deepcopy(schema)

    modified = _modify_tool_schema_for_gemini(schema)

    assert original != modified

    input_props = modified["properties"]["invocations"]["items"]["properties"]["input"]

    if "properties" in input_props:
        assert input_props["properties"] != {}


def test_gemini_string_format_removal():
    """Test that unsupported string formats are removed for Gemini."""
    schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "format": "uri",
                "description": "The URL to fetch content from",
            },
            "date": {
                "type": "string",
                "format": "date-time",
                "description": "Date value",
            },
        },
    }

    modified = _modify_tool_schema_for_gemini(schema)

    assert "format" not in modified["properties"]["url"]
    assert modified["properties"]["date"]["format"] == "date-time"


def test_additional_properties_handling():
    """Test handling of additionalProperties for Gemini."""
    schema = {
        "type": "object",
        "properties": {
            "test": {"type": "object", "additionalProperties": True, "properties": {}}
        },
    }

    modified = _modify_tool_schema_for_gemini(schema)

    test_prop = modified["properties"]["test"]
    assert "additionalProperties" in test_prop
    assert (
        test_prop["additionalProperties"] == {"type": "string"}
        or "properties" not in test_prop
    )


def test_apply_provider_modifications():
    """Test the public API for provider modifications."""
    params = {
        "model": "google/gemini-pro",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "WebFetchTool",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string", "format": "uri"}},
                    },
                },
            }
        ],
    }

    original = copy.deepcopy(params)

    modified = apply_provider_modifications(params, "google")

    assert original != modified

    url_prop = modified["tools"][0]["function"]["parameters"]["properties"]["url"]
    assert "format" not in url_prop

    other_provider_params = copy.deepcopy(params)
    other_modified = apply_provider_modifications(other_provider_params, "anthropic")

    assert other_modified is not other_provider_params
    assert other_modified == other_provider_params
    assert (
        other_modified["tools"][0]["function"]["parameters"]["properties"]["url"][
            "format"
        ]
        == "uri"
    )
