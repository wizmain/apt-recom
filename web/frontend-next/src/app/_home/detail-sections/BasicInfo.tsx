"use client";

import type { ApartmentBasic, KaptInfo } from "@/types/apartment";
import { Section } from "@/components/presentation/Section";
import { DataList } from "@/components/presentation/DataList";
import { formatYyyymmdd } from "@/components/presentation/format";

/**
 * 기본 정보 섹션 — 아파트 테이블 원본 컬럼 + K-APT 부가 정보 병합.
 * 값이 전부 null 이면 섹션 생략.
 */
export function BasicInfo({
  basic,
  kapt,
}: {
  basic: ApartmentBasic;
  kapt: KaptInfo | null | undefined;
}) {
  const areaLabel =
    basic.min_area && basic.max_area
      ? basic.min_area === basic.max_area
        ? `${Math.round(basic.min_area)}㎡`
        : `${Math.round(basic.min_area)}~${Math.round(basic.max_area)}㎡`
      : null;
  const supplyLabel =
    basic.min_supply_area && basic.max_supply_area
      ? basic.min_supply_area === basic.max_supply_area
        ? `${Math.round(basic.min_supply_area)}㎡`
        : `${Math.round(basic.min_supply_area)}~${Math.round(basic.max_supply_area)}㎡`
      : null;

  const items = [
    basic.total_hhld_cnt
      ? { label: "세대수", value: `${basic.total_hhld_cnt}세대` }
      : null,
    basic.dong_count ? { label: "동수", value: `${basic.dong_count}동` } : null,
    basic.max_floor ? { label: "최고층", value: `${basic.max_floor}층` } : null,
    areaLabel ? { label: "전용면적", value: areaLabel } : null,
    supplyLabel ? { label: "공급면적", value: supplyLabel } : null,
    formatYyyymmdd(basic.use_apr_day)
      ? { label: "사용승인일", value: formatYyyymmdd(basic.use_apr_day)! }
      : null,
    kapt?.builder ? { label: "시공사", value: kapt.builder } : null,
    kapt?.heat_type ? { label: "난방", value: kapt.heat_type } : null,
    kapt?.structure ? { label: "구조", value: kapt.structure } : null,
    kapt?.hall_type ? { label: "복도", value: kapt.hall_type } : null,
    kapt?.parking_cnt ? { label: "주차", value: `${kapt.parking_cnt}대` } : null,
    kapt?.elevator_cnt
      ? { label: "승강기", value: `${kapt.elevator_cnt}대` }
      : null,
    kapt?.cctv_cnt ? { label: "CCTV", value: `${kapt.cctv_cnt}대` } : null,
    kapt?.ev_charger_cnt
      ? { label: "전기차충전", value: `${kapt.ev_charger_cnt}대` }
      : null,
    kapt?.mgr_type ? { label: "관리", value: kapt.mgr_type } : null,
  ];
  const list = <DataList items={items} />;
  if (!list) return null;
  return <Section title="기본 정보">{list}</Section>;
}
