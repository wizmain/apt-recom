import { useEffect, useState, useCallback } from "react";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import { ConfirmDialog } from "../components/ConfirmDialog";

interface CodeGroup {
  group_id: string;
  cnt: number;
}

interface CodeItem {
  code: string;
  name: string;
  extra: string;
  sort_order: number;
}

export function CommonCode() {
  const { token, clearToken } = useAuth();
  const { request, loading } = useAdminApi({ token, onUnauthorized: clearToken });

  const [groups, setGroups] = useState<CodeGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [codes, setCodes] = useState<CodeItem[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // 추가 폼
  const [showAdd, setShowAdd] = useState(false);
  const [newCode, setNewCode] = useState({ code: "", name: "", extra: "", sort_order: 0 });

  // 수정 중인 코드
  const [editCode, setEditCode] = useState<string | null>(null);
  const [editData, setEditData] = useState({ name: "", extra: "", sort_order: 0 });

  useEffect(() => {
    fetch("/api/codes")
      .then((r) => r.json())
      .then((d) => setGroups(d))
      .catch(() => {});
  }, []);

  const fetchCodes = useCallback(() => {
    if (!selectedGroup) return;
    fetch(`/api/codes/${selectedGroup}`)
      .then((r) => r.json())
      .then((d) => setCodes(d))
      .catch(() => {});
  }, [selectedGroup]);

  useEffect(() => {
    fetchCodes();
  }, [fetchCodes]);

  const handleAdd = async () => {
    if (!selectedGroup || !newCode.code) return;
    await request("post", `/codes/${selectedGroup}`, newCode);
    setShowAdd(false);
    setNewCode({ code: "", name: "", extra: "", sort_order: 0 });
    fetchCodes();
  };

  const handleUpdate = async (code: string) => {
    if (!selectedGroup) return;
    await request("put", `/codes/${selectedGroup}/${code}`, editData);
    setEditCode(null);
    fetchCodes();
  };

  const handleDelete = async () => {
    if (!selectedGroup || !deleteTarget) return;
    await request("delete", `/codes/${selectedGroup}/${deleteTarget}`);
    setDeleteTarget(null);
    fetchCodes();
  };

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">공통코드 관리</h1>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
        {/* Groups */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">그룹</h2>
          <div className="flex flex-col gap-1">
            {groups.map((g) => (
              <button
                key={g.group_id}
                onClick={() => setSelectedGroup(g.group_id)}
                className={`text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                  selectedGroup === g.group_id
                    ? "bg-blue-600 text-white"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                {g.group_id}
                <span className="opacity-70 ml-1">({g.cnt})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Codes */}
        <div className="lg:col-span-3 bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-[13px] font-semibold text-slate-900">
              {selectedGroup ?? "그룹을 선택하세요"}
            </h2>
            {selectedGroup && (
              <button
                onClick={() => setShowAdd(true)}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
              >
                추가
              </button>
            )}
          </div>

          {/* Add form */}
          {showAdd && (
            <div className="border border-blue-200 bg-blue-50 rounded-lg p-3 mb-3">
              <div className="grid grid-cols-4 gap-2 text-xs">
                <input
                  value={newCode.code}
                  onChange={(e) => setNewCode({ ...newCode, code: e.target.value })}
                  placeholder="code"
                  className="px-2 py-1.5 border border-gray-200 rounded"
                />
                <input
                  value={newCode.name}
                  onChange={(e) => setNewCode({ ...newCode, name: e.target.value })}
                  placeholder="name"
                  className="px-2 py-1.5 border border-gray-200 rounded"
                />
                <input
                  value={newCode.extra}
                  onChange={(e) => setNewCode({ ...newCode, extra: e.target.value })}
                  placeholder="extra"
                  className="px-2 py-1.5 border border-gray-200 rounded"
                />
                <div className="flex gap-1">
                  <button
                    onClick={handleAdd}
                    className="px-2 py-1.5 bg-blue-600 text-white rounded text-xs"
                  >
                    저장
                  </button>
                  <button
                    onClick={() => setShowAdd(false)}
                    className="px-2 py-1.5 text-gray-500 text-xs"
                  >
                    취소
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Table */}
          {selectedGroup && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">code</th>
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">name</th>
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">extra</th>
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">순서</th>
                    <th className="px-3 py-2 text-right font-semibold text-gray-600">작업</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-gray-400">로딩 중...</td>
                    </tr>
                  ) : codes.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-gray-400">코드 없음</td>
                    </tr>
                  ) : (
                    codes.map((c) => (
                      <tr key={c.code} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-3 py-2 font-mono text-slate-700">{c.code}</td>
                        <td className="px-3 py-2">
                          {editCode === c.code ? (
                            <input
                              value={editData.name}
                              onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                              className="px-1.5 py-0.5 border border-gray-300 rounded w-full"
                            />
                          ) : (
                            c.name
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-500">
                          {editCode === c.code ? (
                            <input
                              value={editData.extra}
                              onChange={(e) => setEditData({ ...editData, extra: e.target.value })}
                              className="px-1.5 py-0.5 border border-gray-300 rounded w-full"
                            />
                          ) : (
                            c.extra
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-400">{c.sort_order}</td>
                        <td className="px-3 py-2 text-right">
                          {editCode === c.code ? (
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => handleUpdate(c.code)}
                                className="text-blue-600 hover:underline"
                              >
                                저장
                              </button>
                              <button
                                onClick={() => setEditCode(null)}
                                className="text-gray-400 hover:underline"
                              >
                                취소
                              </button>
                            </div>
                          ) : (
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => {
                                  setEditCode(c.code);
                                  setEditData({ name: c.name, extra: c.extra, sort_order: c.sort_order });
                                }}
                                className="text-blue-600 hover:underline"
                              >
                                수정
                              </button>
                              <button
                                onClick={() => setDeleteTarget(c.code)}
                                className="text-red-500 hover:underline"
                              >
                                삭제
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="코드 삭제"
        message={`${selectedGroup}/${deleteTarget} 코드를 삭제하시겠습니까?`}
        confirmLabel="삭제"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
