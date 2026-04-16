import { useState } from "react";

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
}

interface DataTableProps {
  columns: Column[];
  data: Record<string, unknown>[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onSort?: (column: string, dir: "asc" | "desc") => void;
  onSearch?: (column: string, value: string) => void;
  searchColumns?: string[];
  loading?: boolean;
  /** 행 클릭 시 콜백. 설정되면 행에 cursor-pointer + 클릭 이벤트 바인딩. */
  onRowClick?: (row: Record<string, unknown>) => void;
  /** 셀 커스텀 렌더러. 컬럼 key → ReactNode. 미지정 컬럼은 String(row[key]) 사용. */
  renderCell?: (row: Record<string, unknown>, columnKey: string) => React.ReactNode;
}

export function DataTable({
  columns,
  data,
  total,
  page,
  totalPages,
  onPageChange,
  onSort,
  onSearch,
  searchColumns,
  loading,
  onRowClick,
  renderCell,
}: DataTableProps) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [searchCol, setSearchCol] = useState(searchColumns?.[0] ?? "");
  const [searchVal, setSearchVal] = useState("");

  const handleSort = (col: string) => {
    const newDir = sortCol === col && sortDir === "asc" ? "desc" : "asc";
    setSortCol(col);
    setSortDir(newDir);
    onSort?.(col, newDir);
  };

  const handleSearch = () => {
    if (searchCol && searchVal.trim()) {
      onSearch?.(searchCol, searchVal.trim());
    }
  };

  return (
    <div>
      {/* Search */}
      {onSearch && searchColumns && searchColumns.length > 0 && (
        <div className="flex gap-2 mb-3">
          <select
            value={searchCol}
            onChange={(e) => setSearchCol(e.target.value)}
            className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs bg-white"
          >
            {searchColumns.map((col) => (
              <option key={col} value={col}>
                {col}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="검색..."
            className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-xs"
          />
          <button
            onClick={handleSearch}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
          >
            검색
          </button>
          {searchVal && (
            <button
              onClick={() => {
                setSearchVal("");
                onSearch?.("", "");
              }}
              className="px-2 py-1.5 text-gray-500 text-xs hover:text-red-500"
            >
              초기화
            </button>
          )}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-3 py-2 text-left font-semibold text-gray-600 ${col.sortable ? "cursor-pointer hover:text-blue-600" : ""}`}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  {col.label}
                  {sortCol === col.key && (
                    <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-8 text-center text-gray-400"
                >
                  로딩 중...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-8 text-center text-gray-400"
                >
                  데이터 없음
                </td>
              </tr>
            ) : (
              data.map((row, i) => (
                <tr
                  key={i}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={`border-b border-gray-100 hover:bg-gray-50 ${
                    onRowClick ? "cursor-pointer" : ""
                  }`}
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-3 py-2 text-gray-700">
                      {renderCell
                        ? (renderCell(row, col.key) ?? String(row[col.key] ?? "-"))
                        : String(row[col.key] ?? "-")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
        <span>
          총 {total.toLocaleString()}건 (페이지 {page}/{totalPages})
        </span>
        <div className="flex gap-1">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100"
          >
            이전
          </button>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100"
          >
            다음
          </button>
        </div>
      </div>
    </div>
  );
}
