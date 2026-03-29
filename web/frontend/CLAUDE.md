# Frontend Rules (React 19 + TypeScript + Vite)

## 스택
- React 19.2.4, TypeScript 5.9 (strict)
- Vite 8 + @tailwindcss/vite 플러그인
- Tailwind CSS 4 (utility classes)
- axios (API 호출), recharts (차트), react-markdown (마크다운)

## 디렉토리 구조 (Flat)
```
src/
├── App.tsx                     # 루트 컴포넌트 (전체 상태 오케스트레이션)
├── main.tsx                    # React entry point
├── config.ts                   # API_BASE 설정
├── index.css                   # 글로벌 스타일
├── types/apartment.ts          # 타입 정의
├── components/                 # 모든 컴포넌트 (flat)
│   ├── Map.tsx                 # 카카오 지도
│   ├── FilterPanel.tsx         # 필터 UI
│   ├── NudgeBar.tsx            # 넛지 스코어 바
│   ├── WeightDrawer.tsx        # 가중치 조절 드로어
│   ├── ResultCards.tsx         # 검색 결과 카드
│   ├── DetailModal.tsx         # 아파트 상세 모달
│   ├── CompareModal.tsx        # 아파트 비교 모달
│   ├── ChatButton.tsx          # 챗봇 버튼
│   ├── ChatModal.tsx           # 챗봇 모달
│   ├── ChatInput.tsx           # 챗봇 입력
│   └── ChatMessage.tsx         # 챗봇 메시지
└── hooks/
    ├── useApartments.ts        # 아파트 데이터 페칭/필터링
    ├── useChat.ts              # 챗봇 상태 관리
    └── useNudge.ts             # 넛지 추천 로직
```

**Feature 폴더 구조 사용하지 않음.** 새 컴포넌트는 `src/components/`에 추가.

## 컴포넌트 규칙
- 함수형 컴포넌트만 사용
- Props 타입 정의 필수 (interface 또는 type)
- 파일명 PascalCase, 한 파일 한 exported 컴포넌트

## API 호출
- `import { API_BASE } from '../config'` + axios
- Vite dev 서버가 `/api`를 백엔드(localhost:8000)로 프록시
- hooks에서 상태 관리 + API 호출 통합

## 타입
- `any` 사용 금지
- API 응답 타입은 `src/types/apartment.ts`에 정의
- 새 도메인 타입은 `src/types/`에 파일 추가

## 스타일
- Tailwind CSS utility classes
- 다크모드 미지원 (현재)
- 반응형: 모바일 우선

## 검증 (테스트 프레임워크 없음)
- 타입 체크: `npm run check` (tsc -b)
- 린트: `npm run lint` (eslint)
- 빌드: `npm run build` (tsc -b && vite build)
