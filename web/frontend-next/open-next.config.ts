// open-next.config.ts
// OpenNext Cloudflare 빌드 설정.
// 레퍼런스: https://opennext.js.org/cloudflare

import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig({
  // 필요 시 override:
  // incrementalCache, tagCache, queue, dangerous 등을 여기에 명시.
  // 기본값(메모리 캐시) 로 시작 — ISR/revalidate 를 쓰면
  // R2 또는 Workers KV 기반 캐시로 업그레이드.
});
