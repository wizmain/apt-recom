import type { ApartmentDetail, TradesResponse } from "@/types/apartment";
import { BasicInfo } from "./sections/BasicInfo";
import { LifeScores } from "./sections/LifeScores";
import { PriceInfo } from "./sections/PriceInfo";
import { School } from "./sections/School";
import { Facilities } from "./sections/Facilities";
import { Safety } from "./sections/Safety";
import { Population } from "./sections/Population";
import { RecentTrades } from "./sections/RecentTrades";

/**
 * 아파트 상세 뷰 — Server Component 조립자.
 *
 * agent 관점: 각 섹션이 Server Component 이므로 HTML 본문에 모든 정보가 포함.
 * 섹션들은 내부에서 데이터 부재 시 자체적으로 null 을 반환 → 빈 렌더 방지.
 *
 * 사용자 UX 관점: 탭 전환 없는 수직 스크롤 구조. 기존 DetailModal 의 7개 탭
 * 기능(Price 분석 차트·관리비 분포 차트 등 복잡한 interactive 차트)은 Phase C
 * 이후 Client Component 로 추가 가능.
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
  const { basic, scores, school, facility_summary, safety, population, kapt_info } =
    detail;
  const address = basic.new_plat_plc ?? basic.plat_plc ?? null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 sm:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{basic.bld_nm}</h1>
        {address ? (
          <p className="mt-1 text-sm text-gray-500">{address}</p>
        ) : null}
        <p className="mt-3 text-xs text-gray-400">PNU {pnu}</p>
      </header>

      <BasicInfo basic={basic} kapt={kapt_info} />
      <PriceInfo basic={basic} />
      <LifeScores scores={scores} />
      <School school={school} />
      <Facilities summary={facility_summary} />
      <Safety safety={safety} />
      <Population population={population} />
      <RecentTrades trades={trades} />
    </main>
  );
}
