# ADR-007: 프론트엔드 Flat 컴포넌트 구조

- **상태**: Accepted
- **날짜**: 2026-03-21

## 맥락

프론트엔드 컴포넌트 구조를 설계할 때, 기능별 폴더(feature-based) 또는 계층별 폴더(atomic design) 등 여러 패턴을 고려했다.

## 결정

모든 컴포넌트를 `src/components/`에 flat하게 배치한다. 하위 폴더를 만들지 않는다.

## 근거

- **프로젝트 규모**: 컴포넌트 수가 11개 수준으로, 복잡한 디렉토리 구조가 불필요하다.
- **빠른 탐색**: 모든 컴포넌트가 한 곳에 있어 파일을 찾기 쉽다.
- **단순성**: 폴더 구조 고민 없이 바로 컴포넌트를 추가할 수 있다.

## 구조

```
src/
├── components/     # 모든 컴포넌트 (flat)
│   ├── Map.tsx, NudgeBar.tsx, DetailModal.tsx, ...
│   ├── ChatModal.tsx, ChatMessage.tsx, ...
│   └── ComparePanel.tsx, FilterPanel.tsx, ...
├── hooks/          # 커스텀 훅 (useApartments, useChat, useNudge)
└── types/          # TypeScript 타입 정의
```

## 트레이드오프

- 컴포넌트가 30개 이상으로 늘어나면 폴더 분류가 필요할 수 있다.
- 컴포넌트 간 관계(부모-자식)가 파일명에서 드러나지 않는다.

## 결과

- 새 컴포넌트는 `src/components/`에 직접 생성한다.
- 커스텀 훅은 `src/hooks/`에 분리하여 비즈니스 로직과 UI를 구분한다.
