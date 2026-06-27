from typing import Callable, Dict, Any, List


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register(self, name: str, func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.tools[name] = func

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def execute(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.tools:
            return {
                "success": False,
                "error": f"Tool '{name}' not found"
            }

        try:
            return self.tools[name](payload)
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


tool_registry = ToolRegistry()
