import { useState, useCallback, useEffect } from "react";
import { ConfirmDialog } from "./ConfirmDialog";
import { API_BASE } from "../config";
import type {
  MgmtCostPreviewRow,
  MgmtCostPreviewResponse,
  RegisterStatusResponse,
} from "../types/admin";

interface MgmtCostUploadProps {
  token: string | null;
}

interface DropZoneProps {
  label: string;
  hint: string;
  file: File | null;
  onFile: (file: File) => void;
  onClear: () => void;
  required?: boolean;
}

function DropZone({ label, hint, file, onFile, onClear, required }: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f && f.name.toLowerCase().endsWith(".xlsx")) onFile(f);
    },
    [onFile],
  );

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`relative border-2 border-dashed rounded-xl p-4 text-center transition-colors ${
        dragOver ? "border-blue-500 bg-blue-50"
          : file ? "border-green-300 bg-green-50"
          : "border-gray-300 bg-gray-50 hover:border-blue-400"
      }`}
    >
      {file ? (
        <div className="flex items-center justify-center gap-2">
          <span className="text-green-600">&#10003;</span>
          <span className="text-xs text-slate-700 font-medium truncate max-w-40">{file.name}</span>
          <span className="text-[10px] text-gray-400">({(file.size / 1024).toFixed(0)} KB)</span>
          <button onClick={(e) => { e.stopPropagation(); onClear(); }} className="ml-1 text-gray-400 hover:text-red-500 text-xs">&#10005;</button>
        </div>
      ) : (
        <>
          <div className="text-xl text-gray-400 mb-1">&#128194;</div>
          <p className="text-xs font-medium text-slate-700">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</p>
          <p className="text-[10px] text-gray-400">{hint}</p>
          <p className="text-[10px] text-blue-500 mt-1">드래그 또는 클릭</p>
        </>
      )}
      <input type="file" accept=".xlsx" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} className="absolute inset-0 opacity-0 cursor-pointer" />
    </div>
  );
}

export function MgmtCostUpload({ token }: MgmtCostUploadProps) {
  const [costFile, setCostFile] = useState<File | null>(null);
  const [areaFile, setAreaFile] = useState<File | null>(null);
  const [basicFile, setBasicFile] = useState<File | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<MgmtCostPreviewResponse | null>(null);
  const [importing, setImporting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showRegisterConfirm, setShowRegisterConfirm] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // 비동기 등록
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<RegisterStatusResponse | null>(null);

  // 미리보기
  const handlePreview = async () => {
    if (!costFile || !token) return;
    setPreviewing(true);
    setPreview(null);
    setResult(null);
    setTaskId(null);
    setProgress(null);

    const formData = new FormData();
    formData.append("cost_file", costFile);
    if (areaFile) formData.append("area_file", areaFile);
    if (basicFile) formData.append("basic_file", basicFile);

    try {
      const res = await fetch(`${API_BASE}/api/admin/mgmt-cost/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "요청 실패" }));
        setResult({ message: err.detail || `오류: ${res.status}`, type: "error" });
        return;
      }
      setPreview(await res.json());
    } catch (e) {
      setResult({ message: `네트워크 오류: ${e instanceof Error ? e.message : ""}`, type: "error" });
    } finally {
      setPreviewing(false);
    }
  };

  // 신규 등록 시작
  const handleRegisterNew = async () => {
    if (!preview || !token) return;
    setShowRegisterConfirm(false);
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/admin/mgmt-cost/register-new`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ new_apts: preview.new_apts }),
      });
      const data = await res.json();
      if (res.ok) {
        setTaskId(data.task_id);
      } else {
        setResult({ message: data.detail || "등록 시작 실패", type: "error" });
      }
    } catch {
      setResult({ message: "네트워크 오류", type: "error" });
    }
  };

  // 진행률 폴링
  useEffect(() => {
    if (!taskId || !token) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/mgmt-cost/register-status/${taskId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data: RegisterStatusResponse = await res.json();
        setProgress(data);
        if (data.status !== "running") {
          clearInterval(interval);
          if (data.status === "completed") {
            setResult({ message: `신규 ${data.registered}건 등록 완료 (${data.elapsed_seconds}초)`, type: "success" });
          } else {
            setResult({ message: `등록 실패: ${data.errors[0] || "알 수 없는 오류"}`, type: "error" });
          }
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [taskId, token]);

  // 관리비 적재
  const handleImport = async () => {
    if (!costFile || !token) return;
    setShowConfirm(false);
    setImporting(true);
    setResult(null);

    const formData = new FormData();
    formData.append("cost_file", costFile);
    if (areaFile) formData.append("area_file", areaFile);

    try {
      const res = await fetch(`${API_BASE}/api/admin/mgmt-cost/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setResult({ message: data.message, type: "success" });
        setPreview(null);
      } else {
        setResult({ message: data.detail || "적재 실패", type: "error" });
      }
    } catch {
      setResult({ message: "네트워크 오류", type: "error" });
    } finally {
      setImporting(false);
    }
  };

  const formatWon = (v: number) => v >= 10000 ? `${Math.round(v / 10000)}만원` : `${v.toLocaleString()}원`;

  const isRegistering = taskId && progress?.status === "running";

  return (
    <div>
      {/* 파일 업로드 */}
      <div className="bg-white rounded-[10px] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)] mb-4">
        <h2 className="text-[13px] font-semibold text-slate-900 mb-3">K-APT 관리비 엑셀 업로드</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          <DropZone label="관리비 파일" hint="단지_관리비정보_*.xlsx" file={costFile} onFile={setCostFile} onClear={() => setCostFile(null)} required />
          <DropZone label="면적 파일" hint="단지_면적정보*.xlsx (선택)" file={areaFile} onFile={setAreaFile} onClear={() => setAreaFile(null)} />
          <DropZone label="기본정보 파일" hint="단지_기본정보.xlsx (선택, 신규 등록용)" file={basicFile} onFile={setBasicFile} onClear={() => setBasicFile(null)} />
        </div>
        <button onClick={handlePreview} disabled={!costFile || previewing} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 disabled:opacity-50">
          {previewing ? <span className="flex items-center gap-2"><span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />파싱 중...</span> : "미리보기"}
        </button>
      </div>

      {/* 결과 메시지 */}
      {result && (
        <div className={`rounded-lg p-3 mb-4 text-xs flex justify-between items-center ${result.type === "success" ? "bg-green-50 border border-green-200 text-green-800" : "bg-red-50 border border-red-200 text-red-800"}`}>
          <span>{result.message}</span>
          <button onClick={() => setResult(null)} className="text-gray-400 hover:text-gray-600 ml-2">&#10005;</button>
        </div>
      )}

      {/* 진행률 */}
      {isRegistering && progress && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
          <div className="flex justify-between items-center mb-2 text-xs text-blue-800">
            <span className="font-semibold">{progress.message}</span>
            <span>{progress.current} / {progress.total}건 ({progress.elapsed_seconds}초)</span>
          </div>
          <div className="h-2 bg-blue-200 rounded-full">
            <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${progress.total > 0 ? (progress.current / progress.total * 100) : 0}%` }} />
          </div>
        </div>
      )}

      {/* 미리보기 */}
      {preview && (
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          {/* 요약 카드 */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <div className="text-lg font-bold text-green-700">{preview.total.toLocaleString()}</div>
              <div className="text-[10px] text-green-600">매핑 성공</div>
            </div>
            <div className="bg-amber-50 rounded-lg p-3 text-center">
              <div className="text-lg font-bold text-amber-700">{preview.new_apts_count.toLocaleString()}</div>
              <div className="text-[10px] text-amber-600">신규 등록 대상</div>
            </div>
            <div className="bg-red-50 rounded-lg p-3 text-center">
              <div className="text-lg font-bold text-red-700">{preview.errors.length}</div>
              <div className="text-[10px] text-red-600">등록 불가</div>
            </div>
          </div>

          {/* 버튼 영역 */}
          <div className="flex gap-2 mb-4">
            {preview.new_apts_count > 0 && (
              <button
                onClick={() => setShowRegisterConfirm(true)}
                disabled={!!isRegistering}
                className="px-4 py-2 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600 disabled:opacity-50"
              >
                신규 {preview.new_apts_count.toLocaleString()}건 등록
              </button>
            )}
            <button
              onClick={() => setShowConfirm(true)}
              disabled={importing || preview.total === 0}
              className="px-4 py-2 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {importing ? "적재 중..." : `관리비 ${preview.total.toLocaleString()}건 적재`}
            </button>
          </div>

          {/* 오류 목록 */}
          {preview.errors.length > 0 && (
            <details className="mb-3">
              <summary className="text-xs text-red-600 cursor-pointer font-medium">등록 불가 목록 ({preview.errors.length}건)</summary>
              <ul className="list-disc list-inside text-[10px] text-red-700 max-h-24 overflow-auto mt-1 bg-red-50 rounded p-2">
                {preview.errors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </details>
          )}

          {/* 신규 등록 대상 */}
          {preview.new_apts.length > 0 && (
            <details className="mb-3">
              <summary className="text-xs text-amber-600 cursor-pointer font-medium">신규 등록 대상 ({preview.new_apts_count}건)</summary>
              <div className="overflow-x-auto rounded border border-amber-200 mt-1">
                <table className="w-full text-[10px]">
                  <thead><tr className="bg-amber-50"><th className="px-2 py-1 text-left">단지명</th><th className="px-2 py-1 text-left">주소</th><th className="px-2 py-1 text-right">세대수</th></tr></thead>
                  <tbody>
                    {preview.new_apts.map((a) => (
                      <tr key={a.kapt_code} className="border-t border-amber-100">
                        <td className="px-2 py-1">{a.kapt_name}</td>
                        <td className="px-2 py-1 text-gray-500">{a.road_address || a.address}</td>
                        <td className="px-2 py-1 text-right">{a.hhld}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          {/* 매핑 성공 테이블 */}
          {preview.rows.length > 0 && (
            <>
              <h3 className="text-xs font-semibold text-slate-700 mb-2">매핑 성공 미리보기 (상위 {preview.preview_count}건)</h3>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-3 py-2 text-left font-semibold text-gray-600">단지명</th>
                      <th className="px-3 py-2 text-left font-semibold text-gray-600">연월</th>
                      <th className="px-3 py-2 text-right font-semibold text-gray-600">세대당</th>
                      <th className="px-3 py-2 text-right font-semibold text-gray-600">공용</th>
                      <th className="px-3 py-2 text-right font-semibold text-gray-600">개별</th>
                      <th className="px-3 py-2 text-right font-semibold text-gray-600">장충금</th>
                      <th className="px-3 py-2 text-right font-semibold text-gray-600">합계</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((r: MgmtCostPreviewRow, i: number) => (
                      <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-700">{r.kapt_name}</td>
                        <td className="px-3 py-2 text-gray-500">{r.year_month}</td>
                        <td className="px-3 py-2 text-right font-mono text-blue-600">{formatWon(r.cost_per_unit)}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-600">{formatWon(r.common_cost)}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-600">{formatWon(r.individual_cost)}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-600">{formatWon(r.repair_fund)}</td>
                        <td className="px-3 py-2 text-right font-mono font-semibold text-slate-900">{formatWon(r.total_cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      <ConfirmDialog open={showConfirm} title="관리비 DB 적재" message={`${preview?.total.toLocaleString() ?? 0}건의 관리비 데이터를 적재하시겠습니까?`} confirmLabel="적재" onConfirm={handleImport} onCancel={() => setShowConfirm(false)} />
      <ConfirmDialog open={showRegisterConfirm} title="신규 아파트 등록" message={`${preview?.new_apts_count.toLocaleString() ?? 0}건의 신규 아파트를 지오코딩하여 등록합니다. Kakao API 호출이 필요하며 시간이 걸릴 수 있습니다.`} confirmLabel="등록 시작" onConfirm={handleRegisterNew} onCancel={() => setShowRegisterConfirm(false)} />
    </div>
  );
}
