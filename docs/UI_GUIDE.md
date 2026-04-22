# UI 디자인 가이드: ZIASTACK DR 복구 자동화

## 디자인 원칙
1. **운영 도구처럼 보여야 한다.** 매일 쓰는 대시보드이지 마케팅 페이지가 아니다.
2. **상태가 항상 명확해야 한다.** 운영자는 복구가 어디까지 진행됐는지 한눈에 알 수 있어야 한다.
3. **행동 유도가 분명해야 한다.** Confirm 화면에서 승인/거절 외에 다른 선택지가 눈에 띄면 안 된다.

## AI 슬롭 안티패턴 — 하지 마라

| 금지 사항 | 이유 |
|-----------|------|
| backdrop-filter: blur() | glass morphism은 AI 템플릿의 가장 흔한 징후 |
| gradient-text (배경 그라데이션 텍스트) | AI가 만든 SaaS 랜딩의 1번 특징 |
| "Powered by AI" 배지 | 기능이 아니라 장식. 사용자에게 가치 없음 |
| box-shadow 글로우 애니메이션 | 네온 글로우 = AI 슬롭 |
| 보라/인디고 브랜드 색상 | "AI = 보라색" 클리셰 |
| 모든 카드에 동일한 rounded-2xl | 균일한 둥근 모서리는 템플릿 느낌 |
| 배경 gradient orb (blur-3xl 원형) | 모든 AI 랜딩 페이지에 있는 장식 |

## 색상

### 배경
| 용도 | 값 |
|------|------|
| 페이지 | #0f0f0f |
| 카드 / 패널 | #1a1a1a |
| 입력 필드 | #242424 |

### 텍스트
| 용도 | 값 |
|------|------|
| 주 텍스트 | #f0f0f0 |
| 본문 | #b0b0b0 |
| 보조 / 레이블 | #808080 |
| 비활성 | #505050 |

### 시맨틱 색상 (복구 상태)
| 상태 | 색상 | 용도 |
|------|------|------|
| completed | #22c55e | 복구 성공 |
| failed | #ef4444 | 복구 실패 |
| executing | #f59e0b | 진행 중 |
| blocked | #f97316 | 운영자 개입 필요 |
| pending / planning | #6b7280 | 대기 / 분석 중 |
| confirming | #3b82f6 | 승인 대기 |

## 주요 화면

### 1. 복구 요청 화면
- 서버 이름 입력 필드 (단일 입력, 전체 너비)
- "복구 시작" 버튼 1개
- 불필요한 옵션 없음

### 2. Confirm 화면 (정책 검토)
- AI 생성 복구 정책을 구조화된 텍스트로 표시
  - 백업 시점
  - 복구 유형 (Full / 증분)
  - 실행 순서 (numbered list)
  - 예상 소요 시간
- **승인** 버튼 (Primary — 흰 배경, 검은 글자)
- **거절** 버튼 (Secondary — 테두리만)
- 거절 클릭 시: 사유 입력 텍스트 영역 표시 (필수, placeholder: "거절 사유를 입력하세요")
- 재생성 횟수 표시: "재생성 1/3"

### 3. Execute 모니터링 화면
- 진행 단계 표시 (Plan → Confirm → Execute → Report)
- 현재 단계 강조
- 실시간 로그 스트림 (WebSocket, 아래에서 위로 스크롤)
- 상태 뱃지: executing / completed / failed / blocked
- 강제 중단 버튼 (우상단, 작게)

## 컴포넌트

### 카드
```
rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] p-6
```

### 버튼
```
Primary:   rounded bg-white text-black font-medium px-6 py-2 hover:bg-neutral-200
Secondary: rounded border border-[#404040] text-[#b0b0b0] px-6 py-2 hover:border-[#606060]
Danger:    rounded border border-[#7f1d1d] text-[#ef4444] px-4 py-1.5 text-sm
```

### 입력 필드
```
rounded bg-[#242424] border border-[#2a2a2a] px-4 py-3 text-[#f0f0f0]
focus:border-[#404040] outline-none w-full
```

### 상태 뱃지
```
rounded-full px-2.5 py-0.5 text-xs font-medium
예: executing → bg-amber-500/10 text-amber-400 border border-amber-500/20
```

### 로그 스트림
```
rounded bg-[#0a0a0a] border border-[#2a2a2a] p-4 font-mono text-xs
text-[#808080] h-64 overflow-y-auto
```

## 레이아웃
- 전체 너비: max-w-4xl
- 정렬: 좌측 정렬 기본. 중앙 정렬 금지 (버튼 그룹 제외)
- 간격: gap-4, 섹션 간 space-y-6

## 타이포그래피
| 용도 | 스타일 |
|------|--------|
| 페이지 제목 | text-xl font-semibold text-[#f0f0f0] |
| 섹션 제목 | text-sm font-medium text-[#808080] uppercase tracking-wider |
| 본문 | text-sm text-[#b0b0b0] leading-relaxed |
| 코드 / 로그 | font-mono text-xs text-[#808080] |

## 애니메이션
- 허용: fade-in 0.2s ease (화면 전환)
- 허용: 로그 스트림 새 줄 slide-in 0.1s
- 그 외 모든 애니메이션 금지

## 아이콘
- SVG 인라인, strokeWidth 1.5
- 아이콘 컨테이너(둥근 배경 박스)로 감싸지 않는다
