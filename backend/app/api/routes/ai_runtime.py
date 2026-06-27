from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

from backend.app.ai_runtime.tools.bootstrap import bootstrap_tools
from backend.app.ai_runtime.tools.registry import tool_registry

router = APIRouter(prefix="/ai-runtime", tags=["AI Runtime"])

bootstrap_tools()


class ToolExecutionRequest(BaseModel):
    tool_name: str
    payload: Dict[str, Any]


@router.get("/tools")
def list_tools():
    return {
        "tools": tool_registry.list_tools()
    }


@router.post("/tools/execute")
def execute_tool(request: ToolExecutionRequest):
    return tool_registry.execute(
        request.tool_name,
        request.payload
    )


class AgentTaskRequest(BaseModel):
    task: str
    context: Dict[str, Any]


from backend.app.ai_runtime.agents.runtime import agent_runtime


@router.post("/agents/execute")
def execute_agent_task(request: AgentTaskRequest):
    return agent_runtime.execute_task(
        request.task,
        request.context
    )
