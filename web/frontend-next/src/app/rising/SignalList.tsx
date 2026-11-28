import type { RisingSignal } from "@/types/rising";

const SECTION_TITLE = "상승과 함께 보이는 정보";
const SECTION_NOTE = "원인을 단정하지 않아요. 같은 시기 이 단지에서 확인된 사실입니다.";

/** 상승 단지의 신호 목록(상세 전용). 신호가 없으면(하락·보합·비교 부족) 아무것도 그리지 않는다. */
export default function SignalList({ signals }: { signals: RisingSignal[] }) {
  if (signals.length === 0) return null;
  return (
    <section aria-label={SECTION_TITLE} className="rounded-lg border border-gray-200 p-3">
      <h3 className="text-sm font-semibold text-gray-900">{SECTION_TITLE}</h3>
      <p className="mt-0.5 text-[11px] text-gray-500">{SECTION_NOTE}</p>
      <ul className="mt-2 space-y-2">
        {signals.map((signal) => (
          <li key={signal.code} className="text-sm">
            <span className="font-medium text-gray-800">{signal.name}</span>
            <span className="ml-1.5 tabular-nums text-blue-700">{signal.evidence}</span>
            <span className="block text-[11px] leading-snug text-gray-500">
              {signal.description}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
