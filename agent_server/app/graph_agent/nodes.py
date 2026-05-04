import json
from datetime import datetime
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.exceptions import OutputParserException
from langgraph.types import interrupt
from pydantic import ValidationError
from . import agents
from .state import ChatState

import logging

logger = logging.getLogger(__name__)

MAX_POLICY_RETRIES = 3

# try:
#     from langchain_core.exceptions import OutputParserException
# except ImportError:
#     OutputParserException = ValueError


async def _invoke_with_retry(llm, messages, max_retries=3):
    last_error = None
    for _ in range(max_retries):
        try:
            return await llm.ainvoke(messages)
        except (ValidationError, OutputParserException, ValueError) as e:
            last_error = e
    raise last_error


# ── intent 라우터 ─────────────────────────────────────────

async def node_intent_router(state: ChatState):
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None
    )
    if not last_human:
        return {"error": "사용자 메시지 없음"}

    messages = [SystemMessage(content=agents.INTENT_SYSTEM), last_human]
    logger.info(f"[intent_router] 입력 메시지: {messages!r}")
    try:
        decision = await _invoke_with_retry(agents.intent_llm, messages)
    except Exception as e:
        logger.error(f"[intent_router] 분류 실패: {e}")
        return {"error": f"intent 분류 실패: {str(e)}"}
    logger.info(f"[intent_router] intent={decision.intent}, server_id={decision.server_id}")
    return {"intent": decision.intent, "server_id": decision.server_id}


# ── 복구 플로우 노드 ──────────────────────────────────────

async def node_get_server_info(state: ChatState):
    try:
        result = await agents.mcp_tools["get_server_info"].ainvoke({
            "server_id": state["server_id"]
        })
        
        if isinstance(result, list):
            text = result[0].get("text", "") if result else ""
            info = json.loads(text)
        elif isinstance(result, str):
            info = json.loads(result)
        else:
            info = result
        
        if isinstance(info, dict) and "error" in info:
            return {"error": info["error"]}
        return {
            "server_info": info,
            "messages": [AIMessage(content=f"서버 정보 수집 완료: {info.get('name', state['server_id'])}")]
        }
    except Exception as e:
        return {"error": f"서버 정보 수집 실패: {str(e)}"}


async def node_generate_policy(state: ChatState):
    retry = state.get("retry_count", 0) + 1
    server_info = state["server_info"]
    reject_reason = state.get("reject_reason")

    user_content = f"장애 서버 정보:\n{json.dumps(server_info, indent=2, ensure_ascii=False)}"
    if reject_reason:
        user_content += f"\n\n이전 정책 거절 이유: {reject_reason}\n다른 flavor/image 조합으로 재생성하세요."

    messages = [
        SystemMessage(content=agents.POLICY_SYSTEM),
        HumanMessage(content=user_content),
    ]
    try:
        policy = await _invoke_with_retry(agents.policy_llm, messages)
    except Exception as e:
        return {"error": f"정책 생성 실패: {str(e)}"}

    return {
        "recovery_policy": policy.model_dump(),
        "retry_count": retry,
        "reject_reason": None,
        "messages": [AIMessage(
            content=f"정책 생성 ({retry}회차):\n{policy.model_dump_json(indent=2)}"
        )]
    }

async def node_review_policy(state: ChatState):
    """HITL — interrupt()로 그래프 정지, Horizon UI에서 승인/거절 후 재개"""

    decision = interrupt({
        "type": "policy_review",
        "policy": state["recovery_policy"],
        "server_info": state["server_info"],
    })

    if decision.get("approved"):
        return {"messages": [AIMessage(content="정책 승인됨, VM 생성 진행")]}

    reason = decision.get("reason", "사용자 거절")
    return {
        "reject_reason": reason,
        "messages": [AIMessage(content=f"정책 거절됨: {reason}")]
    }


async def node_execute_recovery(state: ChatState):
    policy = state["recovery_policy"]
    try:
        result = await agents.mcp_tools["create_vm"].ainvoke({
            "name": policy["name"],
            "flavor": policy["flavor"],
            "image_id": policy["image_id"],
            "network_id": policy["network_id"],
        })

        if isinstance(result, list):
            text = result[0].get("text", "") if result else ""
            info = json.loads(text)
        elif isinstance(result, str):
            info = json.loads(result)
        else:
            info = result

        if isinstance(info, dict) and "error" in info:
            return {"error": info["error"]}
        return {
            "vm_info": json.dumps(info, ensure_ascii=False),
            "messages": [AIMessage(content=f"VM 생성 완료: {info}")]
        }
    except Exception as e:
        return {"error": f"VM 생성 실패: {str(e)}"}


async def node_generate_report(state: ChatState):
    try:
        report = (
            f"# 복구 완료 보고서\n"
            f"- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 대상 서버: {state.get('server_id')}\n"
            f"- 정책: {json.dumps(state.get('recovery_policy', {}), ensure_ascii=False)}\n"
            f"- 결과: {state.get('vm_info', '')}\n"
        )
        return {
            "report": report,
            "messages": [AIMessage(content=f"복구 완료\n{report}")]
        }
    except Exception as e:
        return {"error": f"리포트 생성 실패: {str(e)}"}


# ── 일반 응답 노드 ────────────────────────────────────────

async def node_response(state: ChatState):
    result = await agents.response_agent.ainvoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


# ── 에러 핸들러 ───────────────────────────────────────────

async def node_error_handler(state: ChatState):
    error = state.get("error", "알 수 없는 오류")
    retry = state.get("retry_count", 0)

    if retry >= MAX_POLICY_RETRIES:
        msg = f"정책 생성 {MAX_POLICY_RETRIES}회 거절. 관리자 확인이 필요합니다."
    else:
        msg = f"오류 발생: {error}"

    return {"messages": [AIMessage(content=msg)]}
