from typing import Dict, Any


def math_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    operation = payload.get("operation")
    a = payload.get("a")
    b = payload.get("b")

    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return {"success": False, "error": "Division by zero"}
        result = a / b
    else:
        return {"success": False, "error": "Unsupported operation"}

    return {
        "success": True,
        "tool": "math_tool",
        "result": result
    }
