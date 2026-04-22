/**
 * 공용 axios 인스턴스 — 클라이언트 컴포넌트 전용.
 *
 * - 모든 요청에 X-Device-Id 헤더 자동 주입.
 * - opt-out 된 사용자는 device_id null → 헤더 미추가 (서버가 자동 no-op).
 * - SSE 스트리밍(fetch 기반, useChat)은 interceptor 미적용이므로 호출 지점에서
 *   getDeviceId() 를 직접 읽어 헤더 구성.
 *
 * 서버 컴포넌트에서는 이 인스턴스 대신 native fetch() 사용 — Next.js 의
 * revalidate/tag 캐시 통합을 활용하기 위해.
 */

import axios from "axios";
import { API_URL } from "@/lib/site";
import { getDeviceId } from "@/lib/device";

export const api = axios.create({ baseURL: API_URL });
export const isCancel = axios.isCancel;

api.interceptors.request.use((config) => {
  const id = getDeviceId();
  if (id) {
    config.headers = config.headers ?? {};
    config.headers["X-Device-Id"] = id;
  }
  return config;
});
