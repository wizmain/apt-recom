import type { RisingCaution, RisingItem } from "@/types/rising";

const CAUTION_LOW_SAMPLE = "low_sample";
const CAUTION_FLOOR_MIX_UP = "floor_mix_up";

type CautionSource = Pick<
  RisingItem,
  "cautions" | "trade_count_3m" | "avg_floor_3m" | "avg_floor_past_6m"
>;

function formatFloor(floor: number): string {
  return `${Math.round(floor)}층`;
}

/** 주의 코드별 근거 수치 문구. 판정은 배치가 했고, 여기서는 같은 행의 수치를 보여 주기만 한다. */
export function cautionEvidence(code: string, item: CautionSource): string | null {
  if (code === CAUTION_LOW_SAMPLE && item.trade_count_3m !== null) {
    return `최근 3개월 ${item.trade_count_3m}건`;
  }
  if (
    code === CAUTION_FLOOR_MIX_UP &&
    item.avg_floor_3m !== null &&
    item.avg_floor_past_6m !== null
  ) {
    return `최근 평균 ${formatFloor(item.avg_floor_3m)} · 6개월 전 ${formatFloor(item.avg_floor_past_6m)}`;
  }
  return null;
}

function tooltipText(caution: RisingCaution, evidence: string | null): string {
  return evidence ? `${evidence} — ${caution.description}` : caution.description;
}

function Chip({ caution, title }: { caution: RisingCaution; title: string }) {
  return (
    <span
      className="inline-block whitespace-nowrap rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-inset ring-amber-200"
      title={title}
    >
      {caution.name}
    </span>
  );
}

interface CautionBadgesProps {
  item: CautionSource;
  /** true 면 배지 아래에 근거·설명을 글로 보인다(상세 패널 — 터치 기기는 툴팁을 볼 수 없다). */
  showDescription?: boolean;
}

/** 변화율 해석 주의 배지. 주의가 없으면 아무것도 그리지 않는다. */
export default function CautionBadges({ item, showDescription = false }: CautionBadgesProps) {
  if (item.cautions.length === 0) return null;
  if (!showDescription) {
    return (
      <div className="mt-1 flex flex-wrap gap-1">
        {item.cautions.map((caution) => (
          <Chip
            key={caution.code}
            caution={caution}
            title={tooltipText(caution, cautionEvidence(caution.code, item))}
          />
        ))}
      </div>
    );
  }
  return (
    <ul className="mt-2 space-y-1.5">
      {item.cautions.map((caution) => {
        const evidence = cautionEvidence(caution.code, item);
        return (
          <li key={caution.code}>
            <Chip caution={caution} title={tooltipText(caution, evidence)} />
            <span className="mt-0.5 block text-[11px] leading-snug text-gray-500">
              {evidence && <span className="text-gray-700">{evidence} · </span>}
              {caution.description}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
