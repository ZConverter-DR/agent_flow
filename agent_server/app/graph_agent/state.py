from langgraph.graph import MessagesState


class ChatState(MessagesState):
    # 라우팅
    intent:          str | None

    # 복구 플로우
    server_id:       str | None
    server_info:     dict | None
    recovery_policy: dict | None
    vm_info:         str | None
    report:          str | None

    # 거절 관리
    retry_count:     int
    reject_reason:   str | None

    # 에러 관리
    error:           str | None