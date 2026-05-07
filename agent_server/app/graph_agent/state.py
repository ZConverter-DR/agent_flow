from langgraph.graph import MessagesState


class ChatState(MessagesState):
    session_id: str | None = None
    # 라우팅
    # "recover_server" | "direct_response"
    intent:          str | None

    # 복구 플로우
    server_id:       str | None
    # OpenStack 서버 상세 정보 필요한 값을 추출하기 쉽게 dict로 저장
    server_info:     dict | None
    # 정책에서 정해진 인자값을 추출하기 쉽게 dict로 저장
    # 정책 생성하는데 이미지랑 flavor, volume 어떤게 있는지 알아야 정책을 만들 수 있을까?
    # 현재 프로젝트에서 생성해둔 image, volume, network 등의 list도 저장을 해둬야 하는가?
    # 정책이라는게 어떤 방향으로 만들어지는지?
    recovery_policy: dict | None
    vm_info:         str | None # create_vm 결과 JSON 문자열
    report:          str | None # 최종 복구 보고서 문자열

    # 거절 관리
    retry_count:     int # 정책 생성 시도 횟수
    reject_reason:   str | None # 사용자 거절 이유 (다음 generate_policy에 반영)

    # 에러 관리
    error:           str | None # 에러 메시지 (노드가 설정, 라우터가 분기 판단에 사용)
