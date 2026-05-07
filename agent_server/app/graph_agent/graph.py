from . import nodes
from langgraph.graph import StateGraph, START, END
from .state import ChatState

MAX_POLICY_RETRIES = 3
# ── 라우팅 함수 ───────────────────────────────────────────

def route_by_intent(state: ChatState):
    if state["intent"] == "recover_server":
        if not state.get("server_id"):
            return "response"   # server_id 없으면 일반 응답으로
        return "get_server_info"
    return "response"

def route_after_server_info(state: ChatState):
    return "error_handler" if state.get("error") else "generate_policy"

def route_after_policy(state: ChatState):
    return "error_handler" if state.get("error") else "review_policy"

def route_after_review(state: ChatState):
    """정책 검토 후 분기"""
    if state.get("error"):
        return "error_handler"
    if state.get("reject_reason"):
        if state.get("retry_count", 0) >= MAX_POLICY_RETRIES:
            return "error_handler"
        return "generate_policy"   # 재생성
    return "execute_recovery"      # 승인 → VM 생성

def route_after_recovery(state: ChatState):
    """VM 생성 후 분기 (단순 성공/실패)"""
    return "error_handler" if state.get("error") else "generate_report"

def route_after_report(state: ChatState):
    return "error_handler" if state.get("error") else END

# ── 그래프 빌드 ───────────────────────────────────────────

def build_graph(checkpointer):
    return (
        StateGraph(ChatState)

        .add_node("intent_router",    nodes.node_intent_router)
        .add_node("get_server_info",  nodes.node_get_server_info)
        .add_node("generate_policy",  nodes.node_generate_policy)
        .add_node("review_policy",    nodes.node_review_policy)
        .add_node("execute_recovery", nodes.node_execute_recovery)
        .add_node("generate_report",  nodes.node_generate_report)
        .add_node("response",         nodes.node_response)
        .add_node("error_handler",    nodes.node_error_handler)

        .add_edge(START, "intent_router")

        .add_conditional_edges("intent_router", route_by_intent, {
            "get_server_info": "get_server_info",
            "response":        "response",
        })

        .add_conditional_edges("get_server_info", route_after_server_info, {
            "generate_policy": "generate_policy",
            "error_handler":   "error_handler",
        })

        .add_conditional_edges("generate_policy", route_after_policy, {
            "review_policy": "review_policy",
            "error_handler": "error_handler",
        })

        .add_conditional_edges("review_policy", route_after_review, {
            "execute_recovery": "execute_recovery",
            "generate_policy":  "generate_policy",
            "error_handler":    "error_handler",
        })

        .add_conditional_edges("execute_recovery", route_after_recovery, {
            "generate_report": "generate_report",
            "error_handler":   "error_handler",
        })

        .add_conditional_edges("generate_report", route_after_report, {
            "error_handler": "error_handler",
            END: END,
        })

        .add_edge("response",      END)
        .add_edge("error_handler", END)

        .compile(checkpointer=checkpointer)
    )
    