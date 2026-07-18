import type { ApartmentBasic } from "@/types/apartment";

/**
 * 단지 표시명 해석 — display_name(보정명) 우선, 없으면 bld_nm(건축물대장).
 * 둘 다 없으면 null: 호출부는 빈 이름을 화면 fallback(주소 등)으로 대체하거나
 * 구조화 데이터(JSON-LD)에서는 해당 블록을 생략해야 한다 — 빈 name 은
 * GSC '탐색경로 name/item.name 누락' 오류로 반복 보고된 이력이 있다.
 */
export function resolveApartmentName(basic: ApartmentBasic): string | null {
  const name = basic.display_name?.trim() || basic.bld_nm?.trim() || "";
  return name === "" ? null : name;
}
