#!/usr/bin/env node
/**
 * 빌드 직전에 백엔드 sitemap.xml 을 받아 public/sitemap.xml 로 저장한다.
 *
 * 왜 이렇게 하는가
 * - CF Pages `_redirects` 의 외부 host rewrite(200) 는 지원되지 않음 → SPA fallback 으로
 *   흡수돼 index.html 이 반환됨.
 * - CF Pages Function 도입은 별도 배포 경로·Worker 환경·Vite 빌드 산출물 외부 유지 등
 *   복잡도가 큼.
 * - 가장 단순한 방법: 빌드 시점에 백엔드에서 sitemap 을 pull 해 정적 파일로 굽는다.
 *   - Content-Type 자동 application/xml (static 서빙)
 *   - CF Pages CDN 캐싱 혜택
 *   - 배포 주기(데일리+) 에 맞춰 신선도 유지
 *
 * 실패 정책
 * - 백엔드가 안 뜬 상태의 로컬 개발을 배려하여 fetch 실패 시 **빌드를 실패시키지 않고**
 *   경고만 출력. 이미 생성된 public/sitemap.xml 이 있으면 그대로 사용, 없으면 sitemap 이
 *   없는 빌드가 된다 (AAO 입장에서 손실이지만 전체 빌드는 진행).
 * - CI 환경은 반드시 성공해야 하므로 `--strict` 플래그로 실패 시 exit 1.
 */

import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const UPSTREAM = process.env.SITEMAP_UPSTREAM ?? "https://api.apt-recom.kr/sitemap.xml";
const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = resolve(__dirname, "..", "public", "sitemap.xml");
const STRICT = process.argv.includes("--strict") || process.env.CI === "true";

async function main() {
  console.log(`[sitemap] fetching ${UPSTREAM}`);
  let res;
  try {
    res = await fetch(UPSTREAM, { headers: { accept: "application/xml" } });
  } catch (err) {
    const msg = `[sitemap] fetch 실패: ${err instanceof Error ? err.message : String(err)}`;
    if (STRICT) {
      console.error(msg);
      process.exit(1);
    }
    console.warn(`${msg} — 기존 public/sitemap.xml 을 그대로 사용합니다.`);
    return;
  }

  if (!res.ok) {
    const msg = `[sitemap] upstream ${res.status} ${res.statusText}`;
    if (STRICT) {
      console.error(msg);
      process.exit(1);
    }
    console.warn(`${msg} — 기존 public/sitemap.xml 유지.`);
    return;
  }

  const body = await res.text();
  if (!body.includes("<urlset")) {
    const msg = "[sitemap] upstream 응답에 <urlset> 이 없음 — XML 검증 실패.";
    if (STRICT) {
      console.error(msg);
      process.exit(1);
    }
    console.warn(msg);
    return;
  }

  writeFileSync(OUT_PATH, body, "utf-8");
  const locCount = (body.match(/<loc>/g) ?? []).length;
  const sizeKb = Math.round(body.length / 1024);
  console.log(`[sitemap] ${OUT_PATH} ← ${locCount} URLs, ${sizeKb}KB`);
}

main().catch((err) => {
  console.error("[sitemap] unexpected error:", err);
  if (STRICT) process.exit(1);
});
