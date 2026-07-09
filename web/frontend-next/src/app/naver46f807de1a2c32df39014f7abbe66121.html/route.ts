// 네이버 서치어드바이저 소유권 확인 파일.
// public/ 정적 파일로 두면 Cloudflare Pages 가 .html 을 떼는 307 리다이렉트
// (pretty URL)를 걸어 네이버 확인 크롤러가 실패할 수 있다 — 라우트 핸들러로
// 정확한 경로에서 200 직접 응답한다.
export function GET(): Response {
  return new Response(
    "naver-site-verification: naver46f807de1a2c32df39014f7abbe66121.html",
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}
