import asyncio, os
from pydantic_ai import Agent
# from pydantic_ai.models.ollama import OllamaModel
# from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.tools import ToolDefinition

from app.common.config import settings

model = OpenAIModel(
    model_name="qwen2.5:7b",
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
        api_key="ollama",    
    )
)

print(f"NOTION_API_KEY 로드됨: {bool(settings.notion_api_key)}")
print(f"slack_bot_token 로드됨: {bool(settings.slack_bot_token)}")
print(f"slack_team_id 로드됨: {bool(settings.slack_team_id)}")

notion = MCPServerStdio(
    "npx",
    args=["-y", "@notionhq/notion-mcp-server"],
    env={
        **os.environ,
        "OPENAPI_MCP_HEADERS": f'{{"Authorization": "Bearer {settings.notion_api_key}", "Notion-Version": "2022-06-28"}}'},
)

slack = MCPServerStdio(
    "npx",
    args = ["-y", "@modelcontextprotocol/server-slack"],
    env={
        **os.environ,
        "SLACK_BOT_TOKEN": settings.slack_bot_token or "",
        "SLACK_TEAM_ID": settings.slack_team_id or "",
    }
)

# agent = Agent(
#     model=model,
#     mcp_servers=[notion, slack],
#     system_prompt="""
#     You are a helpful assistant. Follow these rules strictly:
#     1. Call each tool only ONCE per task.
#     2. Do NOT call the same tool multiple times.
#     3. After getting tool results, immediately respond with the answer.
#     4. Answer in Korean.
#     """,
# )

# Notion 전용 Agent
notion_agent = Agent(
    model=model,
    mcp_servers=[notion],
    system_prompt="""
    You are a helpful assistant that uses Notion tools.
    모든 답변은 한국어로 하세요.
    
    Never pass sort as an empty string "{}". It must be a proper JSON object.
    Call each tool ONLY ONCE. Never repeat tool calls. You MUST always respond in Korean (한국어)
    """,
)

# Slack 전용 Agent
slack_agent = Agent(
    model=model,
    mcp_servers=[slack],
    system_prompt="""
    You are a Slack assistant.
    Call each tool ONLY ONCE. Never repeat tool calls. You MUST always respond in Korean (한국어)
    """,
)

async def main():
    # async with notion_agent.run_mcp_servers():
    #     # tool 목록 + 파라미터 스키마까지 확인
    #     # print("\n=== MCP Tool 목록 ===")
    #     # for server in [notion, slack]:
    #     #     tools = await server.list_tools()
    #     #     for tool in tools:
    #     #         print(f"  - {tool.name}")
    #     #     print("=========\n")
    #     # print("=========\n")
        
    #     result = await notion_agent.run("내 최상위 페이지명을 출력해줘")
    #     print("=== Notion 결과 ===")
    #     print(result.output)
            
    #     # Slack 채널 목록 조회
    #      # ✅ tool 1번만 호출하도록 강제
    #     # result = await slack_agent.run(
    #     #     "slack_list_channels tool을 호출해서 채널 이름과 ID 목록을 보여줘."
    #     # )
    #     # print(result.output)
        
    #     # # 어떤 tool call이 일어났는지 확인
    #     # for msg in result.all_messages():
    #     #     print(msg)
    
    # Notion 테스트
    # async with notion_agent.run_mcp_servers():
    #     result = await notion_agent.run("개인페이지에 '일기장' 페이지를 새로 만들어줘")
    #     print("=== Notion 결과 ===")
    #     print(result.output)

    # Slack 테스트
    async with slack_agent.run_mcp_servers():
        result = await slack_agent.run(
            "test_team 워크스페이스에 들어온 유저 리스트 알려줘"
        )
        print("=== Slack 결과 ===")
        print(result.output)
    
if __name__ == "__main__":
    asyncio.run(main())