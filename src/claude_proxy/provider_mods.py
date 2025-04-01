"""
Applies provider-specific modifications to OpenAI request parameters.
Currently focuses on adjustments needed for Google Gemini models via OpenRouter.
"""

import copy
from typing import Any, Dict

from . import logger
from .logger import LogEvent, LogRecord


def _ensure_base_schema_elements(schema_node: Any) -> Any:
    """Ensures basic schema elements like type, properties, required exist at the top level."""
    if isinstance(schema_node, dict):
        if "parameters" in schema_node and isinstance(schema_node["parameters"], dict):
            params = schema_node["parameters"]
            if "type" not in params:
                params["type"] = "object"
                logger.debug(
                    LogRecord(
                        event=LogEvent.TOOL_HANDLING.value,
                        message="Applying Gemini fix: Added missing 'type: object' to parameters.",
                    )
                )
            if params["type"] == "object":
                if "properties" not in params:
                    params["properties"] = {}
                    logger.debug(
                        LogRecord(
                            event=LogEvent.TOOL_HANDLING.value,
                            message="Applying Gemini fix: Added missing 'properties: {}' to parameters.",
                        )
                    )
                if "required" not in params:
                    params["required"] = []
                    logger.debug(
                        LogRecord(
                            event=LogEvent.TOOL_HANDLING.value,
                            message="Applying Gemini fix: Added missing 'required: []' to parameters.",
                        )
                    )
    return schema_node


def _process_properties_recursively(schema_obj: Dict[str, Any], path: str = "") -> None:
    """Recursively processes properties in a schema to fix Gemini-specific issues."""
    if not isinstance(schema_obj, dict):
        return

    if (
        "type" in schema_obj
        and schema_obj["type"] == "object"
        and "properties" in schema_obj
    ):
        if not schema_obj["properties"]:
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_HANDLING.value,
                    message=f"Removing empty properties field at {path}",
                )
            )
            del schema_obj["properties"]

    if (
        "type" in schema_obj
        and schema_obj["type"] == "string"
        and "format" in schema_obj
    ):
        if schema_obj["format"] not in ["enum", "date-time"]:
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_HANDLING.value,
                    message=f"Removing unsupported format '{schema_obj['format']}' from string property at {path}",
                )
            )
            del schema_obj["format"]

    if "properties" in schema_obj and isinstance(schema_obj["properties"], dict):
        props_to_process = list(schema_obj["properties"].items())
        for prop_name, prop_def in props_to_process:
            new_path = f"{path}.{prop_name}" if path else prop_name
            _process_properties_recursively(prop_def, new_path)

    if "items" in schema_obj and isinstance(schema_obj["items"], dict):
        _process_properties_recursively(schema_obj["items"], f"{path}.items")

    if "additionalProperties" in schema_obj and isinstance(
        schema_obj["additionalProperties"], dict
    ):
        _process_properties_recursively(
            schema_obj["additionalProperties"], f"{path}.additionalProperties"
        )


def _modify_tool_schema_for_gemini(tool_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Applies all necessary modifications to a tool's parameter schema for Gemini."""
    if not isinstance(tool_schema, dict):
        logger.warning(
            LogRecord(
                event=LogEvent.TOOL_HANDLING.value,
                message=f"Gemini modification expected dict schema, got {type(tool_schema)}. Skipping.",
                data={"schema_type": str(type(tool_schema))},
            )
        )
        return tool_schema
    try:
        modified_schema = copy.deepcopy(tool_schema)

        modified_schema = _ensure_base_schema_elements({"parameters": modified_schema})[
            "parameters"
        ]

        _process_properties_recursively(modified_schema)

        if (
            "properties" in modified_schema
            and "invocations" in modified_schema["properties"]
        ):
            invoc_props = modified_schema["properties"]["invocations"]
            if "items" in invoc_props and "properties" in invoc_props["items"]:
                item_props = invoc_props["items"]["properties"]
                if "input" in item_props:
                    input_prop = item_props["input"]

                    if "type" in input_prop and input_prop["type"] == "object":
                        if (
                            "properties" not in input_prop
                            or not input_prop["properties"]
                        ):
                            logger.debug(
                                LogRecord(
                                    event=LogEvent.TOOL_HANDLING.value,
                                    message="Adding explicit dummy properties to BatchTool input object",
                                )
                            )
                            input_prop["properties"] = {
                                "dummy": {
                                    "type": "string",
                                    "description": "Placeholder parameter for Google AI compatibility",
                                }
                            }

                    if "additionalProperties" in input_prop:
                        if (
                            isinstance(input_prop["additionalProperties"], dict)
                            and not input_prop["additionalProperties"]
                        ):
                            del input_prop["additionalProperties"]
                        elif input_prop["additionalProperties"] is True:
                            input_prop["additionalProperties"] = {"type": "string"}

        if modified_schema != tool_schema:
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_HANDLING.value,
                    message="Applied Gemini schema modifications.",
                )
            )
        else:
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_HANDLING.value,
                    message="No Gemini schema modifications needed.",
                )
            )

        return modified_schema
    except Exception as e:
        logger.error(
            LogRecord(
                event=LogEvent.TOOL_HANDLING.value,
                message=f"Failed during Gemini tool schema modification: {e}. Returning original schema.",
            ),
            exc=e,
        )
        return tool_schema


def apply_provider_modifications(
    params: Dict[str, Any], target_provider: str
) -> Dict[str, Any]:
    """
    Applies provider-specific modifications to OpenAI request parameters.

    Args:
        params: The dictionary of OpenAI request parameters.
        target_provider: A string identifying the target provider (e.g., "google").

    Returns:
        A potentially modified dictionary of OpenAI request parameters.
        Returns a deep copy even if no modifications are applied for safety.
    """
    modified_params = copy.deepcopy(params)

    if target_provider == "google":
        logger.debug(
            LogRecord(
                event=LogEvent.TOOL_HANDLING.value,
                message=f"Applying modifications for target provider: {target_provider}",
                data={"provider": target_provider},
            )
        )
        if "tools" in modified_params and isinstance(modified_params["tools"], list):
            modified_tools = []
            for tool in modified_params["tools"]:
                if isinstance(tool, dict) and tool.get("type") == "function":
                    func_spec = tool.get("function")
                    if isinstance(func_spec, dict) and "parameters" in func_spec:
                        original_schema = func_spec["parameters"]
                        modified_schema = _modify_tool_schema_for_gemini(
                            original_schema
                        )
                        if modified_schema is not original_schema:
                            tool["function"]["parameters"] = modified_schema
                            logger.info(
                                LogRecord(
                                    event=LogEvent.TOOL_HANDLING.value,
                                    message=f"Applied Gemini schema mods for tool: {func_spec.get('name', 'Unnamed')}",
                                    data={
                                        "tool_name": func_spec.get("name", "Unnamed")
                                    },
                                )
                            )
                        else:
                            logger.debug(
                                LogRecord(
                                    event=LogEvent.TOOL_HANDLING.value,
                                    message=f"No Gemini schema mods needed/applied for tool: {func_spec.get('name', 'Unnamed')}",
                                    data={
                                        "tool_name": func_spec.get("name", "Unnamed")
                                    },
                                )
                            )
                modified_tools.append(tool)
            modified_params["tools"] = modified_tools
        else:
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_HANDLING.value,
                    message="No 'tools' found in params or not a list, skipping Gemini tool mods.",
                )
            )

    else:
        logger.debug(
            LogRecord(
                event=LogEvent.TOOL_HANDLING.value,
                message=f"No specific modifications defined for target provider: {target_provider}",
                data={"provider": target_provider},
            )
        )

    return modified_params
