# Mobile App Rules (Expo + React Native + TypeScript)

## 스택
- Expo SDK 55, React Native 0.83, React 19
- TypeScript 5.9 (strict), Expo Router (파일 기반 라우팅)
- react-native-webview (카카오맵), axios (API)

## 디렉토리 구조
```
mobile-app/
├── app/                    # Expo Router (파일 기반 라우팅)
│   ├── _layout.tsx         # 루트 레이아웃
│   ├── (tabs)/             # 탭 네비게이션
│   │   ├── index.tsx       # 홈 (지도+검색+넛지)
│   │   ├── search.tsx      # 검색
│   │   ├── chat.tsx        # 챗봇
│   │   └── settings.tsx    # 설정
│   └── detail/[pnu].tsx    # 상세 화면
├── src/
│   ├── components/         # UI 컴포넌트
│   ├── hooks/              # 비즈니스 로직 (useApartments, useNudge, useChat)
│   ├── services/api.ts     # API 클라이언트
│   └── types/              # 타입 정의
```

## 실행 명령
| 항목 | 명령 |
|------|------|
| Expo 서버 | `cd mobile-app && npx expo start --ios` |
| 백엔드 | `cd web/backend && ../../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000` |
| 타입 체크 | `cd mobile-app && npx tsc --noEmit` |
| 통합 테스트 | `/mobile-test` 스킬 사용 |

## 테스트 규칙 (필수)

### 코드 변경 후 필수 검증
- **컴포넌트/훅 수정 후**: `npx tsc --noEmit` 실행하여 타입 에러 확인
- **API 연동 변경 시**: `curl`로 엔드포인트 응답 확인 후 프론트 작업 진행
- **새 화면/라우트 추가 시**: Expo Router에 등록 여부 확인 (`_layout.tsx`)
- **필터/넛지 로직 변경 시**: `/mobile-test api` 실행하여 API 통합 검증

### 기능 추가/변경 완료 시
- `/mobile-test` 스킬을 실행하여 전체 통합 테스트 수행
- 테스트 실패 시 수정 후 재실행, 통과할 때까지 반복

### 금지 사항
- `'use client'` 디렉티브 사용 금지 (Next.js가 아닌 Expo 프로젝트)
- `any` 타입 사용 금지
- 테스트 없이 기능 완료 선언 금지

## API 의존성
- 백엔드: `http://localhost:8000` (개발 환경)
- 카카오맵 HTML: `GET /api/map` (백엔드에서 서빙)
- 카카오 API 키: `832af9764dadaf139a8e82517d49e9f3` (개발자 콘솔에 localhost:8000 등록 필요)
