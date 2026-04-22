/**
 * 상세 페이지 섹션 공통 컴포넌트 — `components/presentation/` 재노출.
 *
 * 실제 구현은 `@/components/presentation/` 로 이관됨 (Server/Client 공용).
 * 기존 섹션 파일의 `from "./_shared"` import 를 깨지 않기 위해 re-export 만 남긴다.
 */

export { Section } from "@/components/presentation/Section";
export { DataList, type DataItem } from "@/components/presentation/DataList";
export { Empty } from "@/components/presentation/Empty";
export {
  formatYyyymmdd,
  formatPriceManwon,
  formatMeters,
} from "@/components/presentation/format";
