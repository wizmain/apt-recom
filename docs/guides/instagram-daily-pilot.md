# 인스타 데일리 파일럿 런북 (Phase 0)

- 대상 PRD: `docs/prd/2026-07-24-instagram-daily-content.md`
- 목적: **운영 가능성·계측 정상성 검증**(2주·14회 수동 발행). 콘텐츠 성과 판정 아님(포맷 단위 관찰만).
- 도구: `scripts/insta_cards/rotation.py`(리졸버, read-only) + `rotation.yaml`(설정) + 기존 생성기.

## 매일 절차 (개입 목표 ≤ 5분)

1. **오늘 배정 확인**
   ```
   .venv/bin/python -m scripts.insta_cards.rotation
   ```
   → 그날 `series`·`slug`·생성 명령이 출력된다. (전체 표: `--calendar 14`)

2. **dry-run 검증** (데이터 충분한지 먼저 확인 — PRD §9-3)
   출력된 `run` 명령 끝에 `--dry-run` 을 붙여 실행. 후보 부족/빈 결과면 **오늘 slot skip 또는
   `rotation.yaml` 큐의 다음 후보로 수동 대체**(조용한 축소 금지). value 자치구 키워드가 결과가
   적으면 더 넓은 키워드로 조정.

   **개수만 보지 말고 단지명·가격대를 눈으로 확인할 것.** 1일차(2026-07-25)에 강남구 value 가
   ㎡당 825~933만원의 "가성비 TOP5"를 뽑았는데 전부 전용 20~55㎡ 오피스텔·도시형생활주택이었다.
   → `min_smallest_area`(모든 주택형이 N㎡ 이상) 필터를 추가해 해소. 다른 시리즈에서도
   **훅과 실제 물건이 어긋나는지**가 검수의 핵심이다.

3. **생성 + 프론트 반영**
   `--dry-run` 없이 실행 → 다시 `--publish` 로 실행하면 posts.json·커버·IG 자산·content_index 가
   갱신된다(로컬 파일, "커밋 필요" 상태). **`--publish` 는 배포가 아니다.**

4. **브랜치 → PR → 머지** (main 직접 push 금지)
   ```
   git switch -c content/ig-YYYYMMDD
   git add web/frontend-next/src/content/instagram/ web/frontend-next/public/content/ web/backend/content/content_index.json
   git commit -m "content(ig): {slug} 발행"
   git push -u origin content/ig-YYYYMMDD && gh pr create ... && gh pr merge --merge
   ```

5. **배포 완료 확인** → **게시**
   머지 후 Cloudflare(웹) 배포가 끝나 원격 자산이 200이 되면:
   ```
   .venv/bin/python -m scripts.insta_cards.instagram {slug}
   ```
   `verify_assets` 가 원격 200/jpeg/8MB 를 강제하므로, 배포 전이면 게시가 실패한다(안전망). 실패 시
   배포 완료를 기다렸다 재실행.

6. **(선택) 스토리 리마인드** — 프로필 링크는 **고정 `/content` 인덱스**라 매일 갱신 불필요.

## CTA / 계측 (Phase 0 확정)
- **프로필 링크 = 고정 `https://apt-recom.kr/content?utm_source=instagram&utm_campaign=ig_daily`** (매일 갱신 없음).
- **포맷 성과는 `content_view` 의 `series` 필드로 측정** — 링크가 고정이라 포맷별 UTM 은 쓰지 않는다.
- 캡션은 기존 생성기가 자동으로 프로필 링크 안내 + 랜딩 URL 을 출력한다(`caption.py`).
- **알려진 갭(기록)**: index→detail 클라이언트 이동 시 `utm_source` 플래그가 소실된다. 채널 구분
  (프로필/스토리/DM)·IG 출처 정밀 귀속은 로거 확장(`utm_medium`/`utm_content`) 이후로 보류.

## 중복·재실행
- 같은 날짜 재실행 시 **같은 slug** 를 재사용(리졸버가 날짜 기반으로 고정). 이미 게시된 slug 재게시는
  게시 로그로 차단됨(`append_log` 선례). 랜딩도 upsert.

## 데이터 부족 정책 (PRD §9-3)
1) 같은 큐의 다음 후보로 대체 → 2) 그래도 부족하면 그날 skip + 주간 베스트 재발행 → 3) 기록.

## 데이터 품질 가드 (2026-07-25 추가)
- **value 시리즈는 `--min-smallest-area` 가 필수**다. `rotation.yaml` 의
  `series.value.min_smallest_area`(현재 59)가 정책값의 단일 출처이며, 리졸버가 명령에 자동으로
  실어준다. 인자를 빼면 CLI 가 실패한다(조용히 약한 필터로 돌아가지 않음).
- 의미: `min_area`(주택형 **하나라도** N㎡ 이상)와 방향이 반대인 **모든 주택형이 N㎡ 이상**.
  오피스텔 단지는 소형 주택형이 섞여 `min_area` 로는 걸러지지 않는다.
- 같은 필터가 `map_cta.filters` 에도 실려 랜딩 TOP5 와 지도 재계산 모집단이 일치한다.

## Phase 1 진입 기준 (수치)
- 계획 14회 중 **무결 발행 14/14**(랜딩 200·자산 200·CTA·게시 모두), 개입 시간 **중앙값 ≤ 5분**,
  게시 실패 0. 충족 시 `daily` 러너 + GH Actions(생성·PR 자동) 착수.

## 알림/담당 (Phase 0)
- 담당=본인, 알림=명령 실패 출력/로그 수동 확인, SLA=당일 best-effort.

## 참고: 요일 배치 (Phase 0)
월 trade_top(전국) · 화 value · 수 compare · 목 lifestyle · 금 budget_choice · 토 value · 일 lifestyle.
`trade_top` 은 지역 파라미터가 없어 전국 주 1회만(월). 지역별 trade_top·`daily_trade`·`ratio_top` 은 Phase 2.
