import Link from "next/link";
import type {
  DashboardSummary,
  TrendMonth,
  RecentTrade,
  RegionApartment,
} from "@/types/region";

/**
 * 지역 허브 뷰 — Server Component 조립. 전부 텍스트/표 SSR (차트·클라이언트 컴포넌트 금지).
 *
 * 데이터 정확성 메모(브리프 문구와 실제 API 필드 차이):
 * - 요약 카드의 "중위가"는 dashboard_summary.trade.median_price_m2 (실제 median) 사용.
 * - 월별 추이표는 dashboard_trend.trade_avg_price_m2 (평균) 만 제공 — "중위가"로 라벨링하면
 *   부정확하므로 "평균가"로 표기.
 * - summary 의 전기 비교는 comparison_mode=yoy(전년 동기) 고정이며 MoM("전월 대비")이
 *   아니므로 prev_label 원본 문구를 그대로 사용.
 */

function formatWon(manwon: number): string {
  if (manwon >= 10000) {
    const eok = manwon / 10000;
    return `${eok.toFixed(eok >= 10 ? 0 : 1)}억`;
  }
  return `${Math.round(manwon).toLocaleString()}만`;
}

function formatPercentChange(cur: number, prev: number): string | null {
  if (!prev) return null;
  const pct = ((cur - prev) / prev) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function formatYearBuilt(useAprDay: string | null): string {
  if (!useAprDay || useAprDay.length < 4) return "-";
  return `${useAprDay.slice(0, 4)}년`;
}

export function RegionHubView({
  district,
  parent,
  summary,
  trend,
  recentTrades,
  apartments,
}: {
  code: string;
  district: string;
  parent: string;
  summary: DashboardSummary | null;
  trend: TrendMonth[];
  recentTrades: RecentTrade[];
  apartments: RegionApartment[];
}) {
  const label = parent ? `${parent} ${district}` : district;
  const priceChange = summary
    ? formatPercentChange(
        summary.trade.median_price_m2,
        summary.trade.prev_median_price_m2,
      )
    : null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-6 sm:py-10 text-gray-900">
      <nav className="text-sm text-gray-500">
        <Link href="/region" className="hover:underline">
          지역
        </Link>{" "}
        &gt; {label}
      </nav>
      <h1 className="mt-2 text-2xl font-bold sm:text-3xl">
        {label} 아파트 실거래가·시세
      </h1>

      {summary ? (
        <section className="mt-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <SummaryCard
              label={`이번 달 거래량 (${summary.current_period})`}
              value={`${summary.trade.volume.toLocaleString()}건`}
            />
            <SummaryCard
              label="㎡당 중위가"
              value={`${formatWon(summary.trade.median_price_m2)}원`}
            />
            <SummaryCard
              label={`${summary.prev_label} 대비`}
              value={priceChange ?? "비교 불가"}
            />
          </div>
          <p className="mt-3 text-xs text-gray-400">{summary.data_lag_notice}</p>
        </section>
      ) : (
        <p className="mt-6 text-sm text-gray-500">
          이 지역의 최근 거래 요약 데이터를 아직 불러올 수 없습니다.
        </p>
      )}

      {trend.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">월별 거래 추이 (최근 {trend.length}개월)</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="py-2 pr-4 font-medium">월</th>
                  <th className="py-2 pr-4 font-medium">거래량</th>
                  <th className="py-2 pr-4 font-medium">㎡당 평균가</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((row) => (
                  <tr key={row.month} className="border-b border-gray-100">
                    <td className="py-2 pr-4 text-gray-700">{row.month}</td>
                    <td className="py-2 pr-4 text-gray-700">
                      {row.trade_volume.toLocaleString()}건
                    </td>
                    <td className="py-2 pr-4 text-gray-700">
                      {row.trade_avg_price_m2 > 0
                        ? `${formatWon(row.trade_avg_price_m2)}원`
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {recentTrades.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">최근 거래 {recentTrades.length}건</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[480px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="py-2 pr-4 font-medium">거래일</th>
                  <th className="py-2 pr-4 font-medium">단지명</th>
                  <th className="py-2 pr-4 font-medium">면적(㎡)</th>
                  <th className="py-2 pr-4 font-medium">층</th>
                  <th className="py-2 pr-4 font-medium">거래가</th>
                </tr>
              </thead>
              <tbody>
                {recentTrades.map((trade, idx) => {
                  const displayName = trade.bld_nm ?? trade.apt_nm;
                  return (
                    <tr
                      key={`${trade.date}-${trade.apt_nm}-${idx}`}
                      className="border-b border-gray-100"
                    >
                      <td className="py-2 pr-4 text-gray-500">{trade.date}</td>
                      <td className="py-2 pr-4 text-gray-700">
                        {trade.pnu ? (
                          <Link
                            href={`/apartment/${trade.pnu}`}
                            className="text-blue-600 hover:underline"
                          >
                            {displayName}
                          </Link>
                        ) : (
                          displayName
                        )}
                      </td>
                      <td className="py-2 pr-4 text-gray-700">
                        {trade.area != null ? trade.area.toFixed(1) : "-"}
                      </td>
                      <td className="py-2 pr-4 text-gray-700">
                        {trade.floor != null ? `${trade.floor}층` : "-"}
                      </td>
                      <td className="py-2 pr-4 text-gray-700">
                        {formatWon(trade.price)}원
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {apartments.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">
            {label} 아파트 단지 목록 ({apartments.length.toLocaleString()}개)
          </h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="py-2 pr-4 font-medium">단지명</th>
                  <th className="py-2 pr-4 font-medium">세대수</th>
                  <th className="py-2 pr-4 font-medium">준공년</th>
                </tr>
              </thead>
              <tbody>
                {apartments.map((apt) => (
                  <tr key={apt.pnu} className="border-b border-gray-100">
                    <td className="py-2 pr-4">
                      <Link
                        href={`/apartment/${apt.pnu}`}
                        className="text-blue-600 hover:underline"
                      >
                        {apt.bld_nm}
                      </Link>
                    </td>
                    <td className="py-2 pr-4 text-gray-700">
                      {apt.total_hhld_cnt.toLocaleString()}세대
                    </td>
                    <td className="py-2 pr-4 text-gray-700">
                      {formatYearBuilt(apt.use_apr_day)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <p className="mt-10 text-sm text-gray-500">
          이 지역에 등록된 단지 정보가 아직 없습니다.
        </p>
      )}
    </main>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="mt-1 text-xl font-bold">{value}</div>
    </div>
  );
}
