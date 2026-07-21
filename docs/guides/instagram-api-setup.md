# Instagram API 셀프 온보딩 (Instagram Login 방식)

전제: 인스타 계정이 프로페셔널(크리에이터/비즈니스)로 전환되어 있어야 한다.

## 1. Meta 앱 생성
1. https://developers.facebook.com/apps → **Create App**
2. Use case: **Instagram** 선택 (제품명: *Instagram API with Instagram Login* — Facebook Page 연결 불필요)
3. 앱 이름(예: jiptori-publisher) 입력 후 생성

## 2. 계정 연결·권한
1. App Dashboard → Instagram → **API setup with Instagram login**
2. *Generate access token* 에서 인스타 계정 로그인·승인
   — 요구 권한: `instagram_business_basic`, `instagram_business_content_publish`
3. 발급된 **장기 토큰(60일)** 과 **Instagram User ID** 를 복사

## 3. .env 기입 (프로젝트 루트)
INSTAGRAM_USER_ID=1784...
INSTAGRAM_ACCESS_TOKEN=IG...

## 4. 검증
.venv/bin/python -m scripts.insta_cards.instagram {발행된-slug} --dry-run
- 계정 username·쿼터·자산 검증·캡션 미리보기가 출력되면 성공
- 401/190 에러: 토큰 만료 또는 권한 부족 — 2번 재수행
- 이때 Graph API 버전이 낡았다는 에러가 나오면 scripts/insta_cards/instagram/api.py
  의 GRAPH_API_VERSION 상수를 현재 안정 버전으로 올릴 것

## 5. 토큰 갱신 (60일마다)
.venv/bin/python -m scripts.insta_cards.instagram --refresh-token
→ 출력된 새 토큰으로 .env 를 직접 교체 (만료 24시간 이후~60일 내 갱신 가능)

## 운영 3단계
1. 발행:  .venv/bin/python -m scripts.insta_cards --series ... --publish
2. 배포:  posts.json·public 자산 커밋 → push → CI 완료 대기
3. 업로드: .venv/bin/python -m scripts.insta_cards.instagram {slug}
