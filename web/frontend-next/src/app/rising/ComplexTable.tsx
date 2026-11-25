import type { RisingItem } from "@/types/rising";
import ChangeCell from "./ChangeCell";
import { ComplexGradeCell, RegionGradeBadge } from "./GradeBadge";
import { formatEok } from "./format";
import Pagination from "./Pagination";

const EMPTY_RESULT_TEXT = "조건에 맞는 단지가 없습니다";

interface ComplexTableProps {
  items: RisingItem[];
  page: number;
  pageSize: number;
  totalCount: number;
  loading: boolean;
  onPageChange: (page: number) => void;
  /** 행/카드 선택. trigger 는 닫을 때 포커스를 돌려줄 요소. */
  onSelect: (pnu: string, trigger: HTMLElement) => void;
}

type SelectHandler = ComplexTableProps["onSelect"];

const ROW_INTERACTION_CLASS =
  "cursor-pointer hover:bg-gray-50 focus-visible:bg-gray-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue-500";

/** 클릭·Enter 로 단지를 선택하는 공통 props. */
function selectableProps(item: RisingItem, onSelect: SelectHandler) {
  return {
    tabIndex: 0,
    onClick: (event: React.MouseEvent<HTMLElement>) => onSelect(item.pnu, event.currentTarget),
    onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => {
      if (event.key !== "Enter") return;
      // 기본 동작을 막지 않으면 패널의 닫기 버튼이 같은 Enter 로 즉시 눌린다.
      event.preventDefault();
      onSelect(item.pnu, event.currentTarget);
    },
  };
}

function PriceCell({ item }: { item: RisingItem }) {
  if (item.median_price_3m === null) return <span className="text-gray-400">—</span>;
  return (
    <div>
      <span className="font-semibold tabular-nums text-gray-900">
        {formatEok(item.median_price_3m)}
      </span>
      {item.trade_count_3m !== null && (
        <span className="block text-[11px] text-gray-400">{item.trade_count_3m}건</span>
      )}
    </div>
  );
}

function NameCell({ item }: { item: RisingItem }) {
  return (
    <div>
      <span className="font-medium text-gray-900">{item.name}</span>
      {item.address && <span className="block text-xs text-gray-500">{item.address}</span>}
    </div>
  );
}

function DesktopTable({ items, onSelect }: { items: RisingItem[]; onSelect: SelectHandler }) {
  const head = "whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-gray-500";
  return (
    <table className="hidden w-full md:table">
      <thead className="border-b border-gray-200 bg-gray-50">
        <tr>
          <th className={head}>단지</th>
          <th className={head}>지역 등급</th>
          <th className={head}>지역 내 단지 등급</th>
          <th className={head}>3개월 중위가격</th>
          <th className={head}>6개월</th>
          <th className={head}>12개월</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {items.map((item) => (
          <tr
            key={item.pnu}
            className={`align-top text-sm ${ROW_INTERACTION_CLASS}`}
            {...selectableProps(item, onSelect)}
          >
            <td className="px-3 py-3"><NameCell item={item} /></td>
            <td className="px-3 py-3"><RegionGradeBadge grade={item.region_grade} /></td>
            <td className="px-3 py-3"><ComplexGradeCell item={item} /></td>
            <td className="px-3 py-3"><PriceCell item={item} /></td>
            <td className="px-3 py-3">
              <ChangeCell pct={item.change_6m_pct} matchedTypeCount={item.matched_type_count_6m} />
            </td>
            <td className="px-3 py-3">
              <ChangeCell pct={item.change_12m_pct} matchedTypeCount={item.matched_type_count_12m} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MobileCards({ items, onSelect }: { items: RisingItem[]; onSelect: SelectHandler }) {
  return (
    <ul className="divide-y divide-gray-100 md:hidden">
      {items.map((item) => (
        <li
          key={item.pnu}
          className={`px-3 py-3 text-sm ${ROW_INTERACTION_CLASS}`}
          {...selectableProps(item, onSelect)}
        >
          <div className="flex items-start justify-between gap-2">
            <NameCell item={item} />
            <PriceCell item={item} />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <RegionGradeBadge grade={item.region_grade} />
            <ComplexGradeCell item={item} />
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div>
              <span className="block text-[11px] text-gray-400">6개월</span>
              <ChangeCell pct={item.change_6m_pct} matchedTypeCount={item.matched_type_count_6m} />
            </div>
            <div>
              <span className="block text-[11px] text-gray-400">12개월</span>
              <ChangeCell pct={item.change_12m_pct} matchedTypeCount={item.matched_type_count_12m} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** 단지 목록 — 데스크톱 표 / 모바일 카드 + 페이지네이션. 데이터는 props 로만 받는다. */
export default function ComplexTable({
  items,
  page,
  pageSize,
  totalCount,
  loading,
  onPageChange,
  onSelect,
}: ComplexTableProps) {
  if (items.length === 0) {
    return (
      <p className="rounded-lg bg-white p-6 text-center text-sm text-gray-500">
        {loading ? "불러오는 중..." : EMPTY_RESULT_TEXT}
      </p>
    );
  }
  return (
    <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <DesktopTable items={items} onSelect={onSelect} />
        <MobileCards items={items} onSelect={onSelect} />
      </div>
      <Pagination
        page={page}
        pageSize={pageSize}
        totalCount={totalCount}
        onPageChange={onPageChange}
      />
    </div>
  );
}
