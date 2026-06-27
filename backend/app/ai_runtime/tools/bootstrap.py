from backend.app.ai_runtime.tools.registry import tool_registry
from backend.app.ai_runtime.tools.math_tool import math_tool


def bootstrap_tools():
    tool_registry.register("math_tool", math_tool)
