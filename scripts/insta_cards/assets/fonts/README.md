# 카드 렌더 폰트 — 출처와 고정 이유

## 파일

| 항목 | 값 |
|------|-----|
| 파일 | `NotoSansKR-VF.ttf` |
| 받은 곳 | https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf |
| SHA-256 | `194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252` |
| 크기 | 10,414,588 bytes |
| 받은 날 | 2026-07-27 |
| 라이선스 | SIL Open Font License 1.1 (`OFL.txt` — 같은 디렉토리) |

파일명은 업스트림의 `NotoSansKR[wght].ttf` 에서 대괄호만 제거했다(셸·glob 취급 문제).
내용은 동일하며 위 SHA-256 으로 검증할 수 있다.

## 이름에 관한 주의 (혼동 방지)

바이너리의 name 테이블 실측값:

```
family      : Noto Sans KR
postscript  : NotoSansKR-Thin        (가변 폰트의 기본 인스턴스 = wght 100)
manufacturer: Adobe
copyright   : (c) 2014-2021 Adobe, with Reserved Font Name 'Source'.
```

**copyright 에 Adobe 와 예약명 `'Source'` 가 보이지만 이 폰트의 이름은 `Noto Sans KR` 이다.**
Google 의 Noto Sans CJK 는 Adobe 의 Source Han Sans 소스로 빌드되므로 상류 저작권 표기를
유지한다. OFL 1.1 clause 3 이 보호하는 예약명은 `'Source'` 이므로:

- 이 파일을 `Noto Sans KR` 로 부르는 것은 정확하다.
- 파생본을 만들 때 `Source...` 로 이름 붙이면 안 된다.

## 왜 저장소에 넣었나

이전에는 macOS 전용 경로(`/System/Library/Fonts/AppleSDGothicNeo.ttc`)를 참조했다.
문제는 두 가지였다.

1. Linux(CI)에서 렌더가 불가능해 테스트 119건 중 34건이 실행되지 못했다.
2. 더 중요한 이유 — `textrules.check_field()` 가 **실제 폰트로 픽셀 폭을 재서** 텍스트
   한도를 검증한다. 즉 폰트는 렌더링만이 아니라 **검증 로직의 입력**이다. 환경마다 폰트가
   다르면 같은 문구가 환경에 따라 통과/실패하고, CI 초록불이 실제 안전을 보장하지 못한다.

그래서 로컬과 CI 가 같은 파일을 쓰도록 고정했다.

## 교체 시 확인할 것

폰트를 바꾸면 폭 측정값이 달라져 **기존 발행물이 텍스트 한도를 넘길 수 있다.** 다음을 모두 할 것.

1. `get_variation_names()` 로 named instance 확인 → `theme.FONT_WEIGHT_VARIATION` 갱신.
   (가변축 기본값이 최저 굵기인 경우가 많다. 지정을 빼먹으면 전체가 얇게 렌더된다.)
2. `reports/insta/*/*/publication.json` 전량에 `textrules.check_field()` 재검증 → 초과 0건 확인.
3. 슬라이드를 실제로 렌더해 잘림·굵기 위계 육안 확인.

Apple SD Gothic Neo → Noto Sans KR 교체(2026-07-27) 시 실측: Noto 가 4~7% 넓었고
(hook +4.4% / summary +5.3% / methodology +7.1% / caveat +7.2%), 기존 발행물 6건은
전량 한도 내였다.
