from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt

DESTRUCTIVE_TOOL_NAMES = {
    "create_vm",
    "execute_recovery",
}

def wrap_destructive_tools(tools: list[BaseTool]) -> list[BaseTool]:
    return [_make_confirmable(t) if t.name in DESTRUCTIVE_TOOL_NAMES else t for t in tools]

def _make_confirmable(tool: BaseTool) -> BaseTool:
    async def _arun(**kwargs) -> str:
        approved = interrupt({"tool_name": tool.name, "args": kwargs})
        if not approved:
            return f"[CANCELLED] User rejected '{tool.name}' execution. The action was NOT performed. Inform the user that the action has been cancelled."
        return await tool.ainvoke(kwargs)
    
    return StructuredTool(
        name=tool.name,
        description=tool.description,
        coroutine=_arun,
        args_schema=tool.args_schema,
    )