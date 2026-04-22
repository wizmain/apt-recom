import type { ApartmentBasic } from "@/types/apartment";
import { DataList, Section } from "./_shared";

/**
 * 가격 정보 — 현재 백엔드 상세 API 는 basic.price_per_m2 만 제공.
 * Phase B 후반에 price_info 별도 객체(score, jeonse_ratio) 확장 시 필드 추가.
 * ₩/㎡ 과 평당 단가(₩/평) 두 형식으로 표기 → agent 가 둘 다 파싱 가능.
 */

const M2_PER_PYEONG = 3.3058;

export function PriceInfo({ basic }: { basic: ApartmentBasic }) {
  const p = basic.price_per_m2;
  if (p == null || p <= 0) return null;

  const manWonPerM2 = Math.round(p / 10000);
  const manWonPerPyeong = Math.round((p * M2_PER_PYEONG) / 10000);

  return (
    <Section title="가격 정보">
      <DataList
        items={[
          { label: "㎡당 단가", value: `${manWonPerM2.toLocaleString()}만원/㎡` },
          {
            label: "평당 단가",
            value: `${manWonPerPyeong.toLocaleString()}만원/평`,
          },
        ]}
      />
    </Section>
  );
}
