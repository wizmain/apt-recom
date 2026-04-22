import type {
  ApartmentDetail,
  TradesResponse,
} from "@/types/apartment";

/**
 * Phase B 초기 — 서버 렌더 가능한 최소 상세 뷰 (DB 원본 컬럼 기반).
 *
 * 이 컴포넌트는 Server Component 로 유지. agent 가 HTML 파싱할 때 핵심 정보
 * (이름·주소·NUDGE 점수·학군·최근 거래)를 본문에 포함시키는 것이 목적.
 *
 * Phase B 후반에 기존 `DetailModal.tsx` (1527 LOC) 의 탭(기본정보/가격/관리비/
 * 주변시설/학군/안전/인구) 을 개별 Server/Client 컴포넌트로 분해해 여기 조립.
 */
export function ApartmentDetailView({
  pnu,
  detail,
  trades,
}: {
  pnu: string;
  detail: ApartmentDetail;
  trades: TradesResponse;
}) {
  const { basic, scores, school, facility_summary } = detail;
  const address = basic.new_plat_plc ?? basic.plat_plc ?? null;
  const areaLabel =
    basic.min_area && basic.max_area
      ? basic.min_area === basic.max_area
        ? `${Math.round(basic.min_area)}㎡`
        : `${Math.round(basic.min_area)}~${Math.round(basic.max_area)}㎡`
      : null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 sm:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{basic.bld_nm}</h1>
        {address ? (
          <p className="mt-1 text-sm text-gray-500">{address}</p>
        ) : null}
        <p className="mt-3 text-xs text-gray-400">PNU {pnu}</p>
      </header>

      <Section title="기본 정보">
        <DataList
          items={[
            basic.total_hhld_cnt
              ? { label: "세대수", value: `${basic.total_hhld_cnt}세대` }
              : null,
            basic.dong_count
              ? { label: "동수", value: `${basic.dong_count}동` }
              : null,
            basic.max_floor
              ? { label: "최고층", value: `${basic.max_floor}층` }
              : null,
            areaLabel ? { label: "전용면적", value: areaLabel } : null,
            basic.use_apr_day
              ? { label: "사용승인일", value: formatYyyymmdd(basic.use_apr_day) }
              : null,
          ]}
        />
      </Section>

      {scores && Object.keys(scores).length > 0 ? (
        <Section title="라이프 점수 (NUDGE)">
          <DataList
            items={Object.entries(scores).map(([k, v]) => ({
              label: k,
              value: typeof v === "number" ? v.toFixed(1) : String(v),
            }))}
          />
        </Section>
      ) : null}

      {school ? (
        <Section title="학군">
          <DataList
            items={[
              school.elementary_school_full_name
                ? {
                    label: "초등학교",
                    value: school.elementary_school_full_name,
                  }
                : school.elementary_school_name
                  ? { label: "초등학교", value: school.elementary_school_name }
                  : null,
              school.middle_school_zone
                ? { label: "중학교 학군", value: school.middle_school_zone }
                : null,
              school.high_school_zone
                ? {
                    label: "고등학교 학군",
                    value: school.high_school_zone_type
                      ? `${school.high_school_zone} (${school.high_school_zone_type})`
                      : school.high_school_zone,
                  }
                : null,
              school.edu_district
                ? { label: "교육지원청", value: school.edu_district }
                : null,
            ]}
          />
        </Section>
      ) : null}

      {facility_summary && Object.keys(facility_summary).length > 0 ? (
        <Section title="주변시설">
          <DataList
            items={Object.entries(facility_summary)
              .slice(0, 10)
              .map(([k, v]) => ({
                label: k,
                value: `${v?.nearest_distance_m ? Math.round(v.nearest_distance_m) : "-"}m · 1km 내 ${v?.count_1km ?? 0}개`,
              }))}
          />
        </Section>
      ) : null}

      {trades.trades && trades.trades.length > 0 ? (
        <Section title="최근 거래">
          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
            {trades.trades.slice(0, 5).map((t, i) => (
              <li
                key={i}
                className="flex items-center justify-between px-4 py-3 text-sm"
              >
                <span className="text-gray-500">
                  {t.deal_year}.{String(t.deal_month).padStart(2, "0")}
                </span>
                <span className="font-medium text-gray-900">
                  {formatPriceManwon(t.deal_amount)}
                </span>
                {t.exclu_use_ar ? (
                  <span className="text-gray-500">{t.exclu_use_ar}㎡</span>
                ) : null}
                {t.floor ? (
                  <span className="text-gray-500">{t.floor}층</span>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </main>
  );
}

function formatYyyymmdd(s: string): string {
  if (s.length === 8) {
    return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;
  }
  return s;
}

function formatPriceManwon(amount: number): string {
  if (amount >= 10000) {
    const ok = Math.floor(amount / 10000);
    const rest = amount % 10000;
    return rest > 0 ? `${ok}억 ${rest.toLocaleString()}만원` : `${ok}억원`;
  }
  return `${amount.toLocaleString()}만원`;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-base font-semibold text-gray-800">{title}</h2>
      {children}
    </section>
  );
}

function DataList({
  items,
}: {
  items: Array<{ label: string; value: string } | null | undefined>;
}) {
  const valid = items.filter(
    (i): i is { label: string; value: string } => !!i,
  );
  if (valid.length === 0) {
    return <p className="text-sm text-gray-400">정보 없음</p>;
  }
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-gray-200 bg-white p-4">
      {valid.map((it) => (
        <div key={it.label} className="text-sm">
          <dt className="text-gray-500">{it.label}</dt>
          <dd className="font-medium text-gray-900">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
