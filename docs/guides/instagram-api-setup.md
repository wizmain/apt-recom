# Instagram API 셀프 온보딩 (Instagram Login 방식)

전제: 인스타 계정이 프로페셔널(크리에이터/비즈니스)로 전환되어 있어야 한다.

## 1. Meta 앱 생성
1. https://developers.facebook.com/apps → **Create App**
2. Use case: **Instagram** 선택 (제품명: *Instagram API with Instagram Login* — Facebook Page 연결 불필요)
3. 앱 이름(예: jiptori-publisher) 입력 후 생성

## 2. Instagram 테스터 역할 부여 (계정 연결 전 필수)

개발 모드 앱은 역할이 부여된 계정만 토큰 발급이 가능하다 — 건너뛰면
계정 추가 시 **"insufficient role"** 에러가 난다 (2026-07-23 실측).

1. 앱 대시보드 → **앱 역할(App Roles) → 역할(Roles)** → 사람 추가
2. 역할 **Instagram 테스터** 선택 → 인스타 사용자명 입력(@ 없이) → 초대
   - 신규 계정이 검색에 안 잡히면: 정확한 핸들(점/언더스코어) 확인,
     웹 로그인 1회·공개 계정·프로필 채우기 후 재시도 (인덱싱 지연 최대 24h)
3. instagram.com 에 해당 계정으로 로그인 → **설정 → 웹사이트 권한
   (Apps and Websites) → 테스터 초대** 탭에서 초대 **수락**

## 3. 계정 연결·권한
1. App Dashboard → Instagram → **API setup with Instagram login**
2. *Generate access token* 에서 인스타 계정 로그인·승인
   — 요구 권한: `instagram_business_basic`, `instagram_business_content_publish`
3. 발급된 **장기 토큰(60일)** 과 **Instagram User ID** 를 복사

## 4. .env 기입 (프로젝트 루트)
INSTAGRAM_USER_ID=1784...
INSTAGRAM_ACCESS_TOKEN=IG...

## 5. 검증
.venv/bin/python -m scripts.insta_cards.instagram {발행된-slug} --dry-run
- 계정 username·쿼터·자산 검증·캡션 미리보기가 출력되면 성공
- 401/190 에러: 토큰 만료 또는 권한 부족 — 2번 재수행
- 이때 Graph API 버전이 낡았다는 에러가 나오면 scripts/insta_cards/instagram/api.py
  의 GRAPH_API_VERSION 상수를 현재 안정 버전으로 올릴 것

## 6. 토큰 갱신 (60일마다)
.venv/bin/python -m scripts.insta_cards.instagram --refresh-token
→ 출력된 새 토큰으로 .env 를 직접 교체 (만료 24시간 이후~60일 내 갱신 가능)

## 운영 3단계
1. 발행:  .venv/bin/python -m scripts.insta_cards --series ... --publish
2. 배포:  posts.json·public 자산 커밋 → push → CI 완료 대기
3. 업로드: .venv/bin/python -m scripts.insta_cards.instagram {slug}
