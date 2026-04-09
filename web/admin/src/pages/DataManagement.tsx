import { useEffect, useState, useCallback } from "react";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import { DataTable } from "../components/DataTable";
import type { TableStats, DataTableResponse } from "../types/admin";

const TABLES = [
  "apartments",
  "trade_history",
  "rent_history",
  "apt_price_score",
  "apt_safety_score",
  "facilities",
  "school_zones",
  "apt_vectors",
];

export function DataManagement() {
  const { token, clearToken } = useAuth();
  const { get, loading } = useAdminApi({ token, onUnauthorized: clearToken });

  const [stats, setStats] = useState<TableStats[]>([]);
  const [selectedTable, setSelectedTable] = useState(TABLES[0]);
  const [tableData, setTableData] = useState<DataTableResponse | null>(null);
  const [page, setPage] = useState(1);
  const [sortCol, setSortCol] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [searchCol, setSearchCol] = useState<string | undefined>();
  const [searchVal, setSearchVal] = useState<string | undefined>();

  useEffect(() => {
    get<{ stats: TableStats[] }>("/data/stats").then(
      (d) => d && setStats(d.stats),
    );
  }, [get]);

  const fetchTable = useCallback(() => {
    const params: Record<string, unknown> = {
      page,
      page_size: 20,
    };
    if (sortCol) {
      params.order_by = sortCol;
      params.order_dir = sortDir;
    }
    if (searchCol && searchVal) {
      params.search_column = searchCol;
      params.search_value = searchVal;
    }
    get<DataTableResponse>(`/data/${selectedTable}`, params).then(
      (d) => d && setTableData(d),
    );
  }, [get, selectedTable, page, sortCol, sortDir, searchCol, searchVal]);

  useEffect(() => {
    fetchTable();
  }, [fetchTable]);

  const handleTableChange = (table: string) => {
    setSelectedTable(table);
    setPage(1);
    setSortCol(undefined);
    setSearchCol(undefined);
    setSearchVal(undefined);
  };

  const selectedStats = stats.find((s) => s.table === selectedTable);

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">데이터 관리</h1>

      {/* Table selector + stats */}
      <div className="flex flex-wrap gap-2 mb-4">
        {TABLES.map((t) => {
          const s = stats.find((st) => st.table === t);
          return (
            <button
              key={t}
              onClick={() => handleTableChange(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                selectedTable === t
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              {t}{" "}
              {s && (
                <span className="opacity-70">
                  ({s.total_records.toLocaleString()})
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Stats card */}
      {selectedStats && (
        <div className="bg-white rounded-[10px] p-3 shadow-[0_1px_3px_rgba(0,0,0,0.06)] mb-4 text-xs text-gray-600">
          <span className="font-semibold text-slate-900">{selectedTable}</span>
          {" · "}
          {selectedStats.total_records.toLocaleString()}건
          {selectedStats.latest_update && (
            <>
              {" · 최근 갱신: "}
              {new Date(selectedStats.latest_update).toLocaleString("ko-KR")}
            </>
          )}
        </div>
      )}

      {/* Data table */}
      {tableData && (
        <DataTable
          columns={tableData.columns.map((c) => ({
            key: c,
            label: c,
            sortable: true,
          }))}
          data={tableData.data}
          total={tableData.total}
          page={tableData.page}
          pageSize={tableData.page_size}
          totalPages={tableData.total_pages}
          onPageChange={setPage}
          onSort={(col, dir) => {
            setSortCol(col);
            setSortDir(dir);
            setPage(1);
          }}
          onSearch={(col, val) => {
            setSearchCol(col || undefined);
            setSearchVal(val || undefined);
            setPage(1);
          }}
          searchColumns={tableData.columns}
          loading={loading}
        />
      )}
    </div>
  );
}
