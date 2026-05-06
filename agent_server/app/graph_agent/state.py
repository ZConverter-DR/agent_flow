from langgraph.graph import MessagesState


class ChatState(MessagesState):
    session_id: str | None = None
    # 라우팅
    intent:          str | None

    # 복구 플로우
    server_id:       str | None 
    server_info:     dict | None 
    # 정보 -> 임베딩 -> 단계를 따르고 -> 정책이 유효한 정책인가? 문서에 따른 정책을 만들어낸건가? 할루 관련된 문서? 관련성 검사?
    # 반환값이 str_policy, 인자값을 키밸류로 
    recovery_policy: dict | None    # 정책 생성하는데 이미지랑 flavor, volume 어떤게 있는지 알아야 정책을 만들 수 있을까?
    vm_info:         str | None
    report:          str | None

    # 거절 관리
    retry_count:     int
    reject_reason:   str | None

    # 에러 관리
    error:           str | None