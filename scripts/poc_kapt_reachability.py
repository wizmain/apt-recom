"""K-APT 자료실 다운로드 PoC — GitHub Actions reachability + board 구조 탐색.

목적(로컬에서 보안 훅에 막혀 CI에서 검증):
  1. CI runner IP 에서 k-apt.go.kr 접근 가능 여부 (한국 gov 사이트의 해외/데이터센터 IP 차단 확인)
  2. 자료실 board 의 목록 AJAX 응답 구조 + 파일 다운로드 링크 패턴 파악

실행: GitHub Actions workflow_dispatch (poc-kapt-download.yml).
이 스크립트는 읽기 전용 탐색만 한다 (대량 다운로드 없음).
의존성 없음 — 표준 라이브러리(urllib)만 사용.
"""

from __future__ import annotations

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.k-apt.go.kr/web/board/webReference"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _open(opener, url: str, data: dict | None = None, timeout: int = 25):
    headers = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    resp = opener.open(req, timeout=timeout)
    return resp.getcode(), resp.read().decode("utf-8", "replace"), dict(resp.headers)


def main() -> int:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 1) Reachability — board 페이지
    section("1) board 페이지 reachability")
    board_html = ""
    try:
        code, board_html, hdrs = _open(opener, f"{BASE}/boardList.do")
        print(f"  GET boardList.do → HTTP {code}, len {len(board_html):,}, "
              f"cookies {[c.name for c in cj]}")
        print(f"  server={hdrs.get('Server')} ct={hdrs.get('Content-Type')}")
        print(f"  본문 앞부분: {' '.join(board_html.split())[:300]}")
    except (urllib.error.URLError, OSError) as e:
        print(f"  ❌ board 페이지 접근 실패: {e}")
        print("  → CI IP 에서 k-apt.go.kr 차단 가능성 (한국 gov 사이트 해외/데이터센터 IP 차단)")
        return 1

    # 2) 목록 AJAX 응답 구조
    section("2) boardListAjax.do 응답 구조 (파라미터 변형)")
    found = False
    for params in (
        {"pageIndex": "1"},
        {"currentPage": "1"},
        {"pageIndex": "1", "searchType": "", "searchWord": ""},
        {"pageNo": "1", "categoryCd": ""},
    ):
        try:
            code, body, _ = _open(opener, f"{BASE}/boardListAjax.do", data=params)
            body = body.strip()
            print(f"  POST {params} → HTTP {code}, len {len(body):,}")
            if body:
                print(f"     head: {' '.join(body.split())[:400]}")
                found = True
                break
        except (urllib.error.URLError, OSError) as e:
            print(f"  POST {params} → 실패 {e}")
    if not found:
        print("  ⚠️ AJAX 목록 응답 없음 — 세션/CSRF/렌더링 필요할 수 있음 (Playwright 검토)")

    # 3) 다운로드 링크/엔드포인트 흔적
    section("3) 다운로드 엔드포인트 흔적 (board 소스 + 참조 JS)")
    pats = re.findall(
        r"(boardListAjax|boardView|FileDown|fileDown|fn_egov_download|"
        r"atchFileId|fileSn|nttId|bbsId|/cmm/fms/[A-Za-z]+\.do)[\w./?=&]*",
        board_html,
    )
    print(f"  매칭 패턴: {sorted(set(pats))[:25] or '없음(JS 렌더링 추정)'}")
    js = re.findall(r'<script[^>]+src="([^"]+)"', board_html)
    print(f"  참조 JS: {js[:10]}")

    print("\n[요약] 1) 200 + 실제 목록 → urllib 로 다운로드 가능.")
    print("        1) 차단/타임아웃 → CI IP 차단 → 다른 경로 필요.")
    print("        2)/3) 비면 → JS 렌더링(Playwright) 필요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
