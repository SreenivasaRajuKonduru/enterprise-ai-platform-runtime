from typing import Dict, Any
from backend.app.ai_runtime.tools.registry import tool_registry


class AgentRuntime:
    def execute_task(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        task_lower = task.lower()

        if "multiply" in task_lower:
            tool_result = tool_registry.execute(
                "math_tool",
                {
                    "operation": "multiply",
                    "a": context.get("a"),
                    "b": context.get("b"),
                },
            )

            return {
                "agent": "basic_agent",
                "task": task,
                "selected_tool": "math_tool",
                "tool_result": tool_result,
            }

        return {
            "agent": "basic_agent",
            "task": task,
            "selected_tool": None,
            "error": "No suitable tool found",
        }


agent_runtime = AgentRuntime()
