"""
Applies provider-specific modifications to OpenAI request parameters.
Currently focuses on adjustments needed for Google Gemini models via OpenRouter.
"""
import copy
import logging
from typing import Dict, Any, List

try:
    from .logging_config import logger
except ImportError:
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.INFO)
        logger.warning(
            "Running provider_mods standalone or logger not found, using basicConfig."
        )



def _ensure_base_schema_elements(schema_node: Any) -> Any:
    """Ensures basic schema elements like type, properties, required exist at the top level."""
    if isinstance(schema_node, dict):
        if "parameters" in schema_node and isinstance(schema_node["parameters"], dict):
            params = schema_node["parameters"]
            if "type" not in params:
                params["type"] = "object"
                logger.debug(
                    "Applying Gemini fix: Added missing 'type: object' to parameters."
                )
            if params["type"] == "object":
                if "properties" not in params:
                    params["properties"] = {}
                    logger.debug(
                        "Applying Gemini fix: Added missing 'properties: {}' to parameters."
                    )
                if "required" not in params:
                    params["required"] = []
                    logger.debug(
                        "Applying Gemini fix: Added missing 'required: []' to parameters."
                    )
    return schema_node




def _modify_tool_schema_for_gemini(tool_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Applies all necessary modifications to a tool's parameter schema for Gemini."""
    if not isinstance(tool_schema, dict):
        logger.warning(
            "Gemini modification expected dict schema, got %s. Skipping.",
            type(tool_schema),
        )
        return tool_schema
    try:
        modified_schema = copy.deepcopy(tool_schema)

        modified_schema = _ensure_base_schema_elements({"parameters": modified_schema})[
            "parameters"
        ]

        if modified_schema != tool_schema:
             logger.debug("Applied Gemini schema modifications (ensured base elements).")
        else:
             logger.debug("No Gemini schema modifications needed (base elements already present).")

        return modified_schema
    except Exception as e:
        logger.error(
            f"Failed during Gemini tool schema modification: {e}. Returning original schema.",
            exc_info=True,
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
        logger.debug(f"Applying modifications for target provider: {target_provider}")
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
                        if (
                            modified_schema is not original_schema
                        ):
                            tool["function"]["parameters"] = modified_schema
                            logger.info(
                                f"Applied Gemini schema mods for tool: {func_spec.get('name', 'Unnamed')}"
                            )
                        else:
                            logger.debug(
                                f"No Gemini schema mods needed/applied for tool: {func_spec.get('name', 'Unnamed')}"
                            )
                modified_tools.append(tool)
            modified_params["tools"] = modified_tools
        else:
            logger.debug(
                "No 'tools' found in params or not a list, skipping Gemini tool mods."
            )


    else:
        logger.debug(
            f"No specific modifications defined for target provider: {target_provider}"
        )

    return modified_params
