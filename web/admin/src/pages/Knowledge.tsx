import { useEffect, useState, useRef } from "react";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import { ConfirmDialog } from "../components/ConfirmDialog";

interface KnowledgeDoc {
  doc_id: string;
  filename: string;
  category: string;
  chunk_count: number;
  uploaded_at?: string;
}

export function Knowledge() {
  const { token, clearToken } = useAuth();
  const { get, request, loading } = useAdminApi({ token, onUnauthorized: clearToken });
  const fileRef = useRef<HTMLInputElement>(null);

  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fetchDocs = () => {
    get<{ documents: KnowledgeDoc[] }>("/knowledge/list").then(
      (d) => d && setDocs(d.documents),
    );
  };

  useEffect(() => {
    fetchDocs();
  }, [get]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("category", "general");

    try {
      const res = await fetch("/api/admin/knowledge/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        fetchDocs();
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await request("delete", `/knowledge/${deleteTarget}`);
    setDeleteTarget(null);
    fetchDocs();
  };

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">지식베이스 관리</h1>

      {/* Upload */}
      <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)] mb-4">
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUpload(file);
            }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {uploading ? "업로드 중..." : "PDF 업로드"}
          </button>
          <span className="text-[11px] text-gray-400">
            PDF 파일을 선택하면 자동으로 텍스트 추출 및 임베딩됩니다.
          </span>
        </div>
      </div>

      {/* Document list */}
      <div className="bg-white rounded-[10px] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">문서 ID</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">파일명</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">카테고리</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">청크 수</th>
              <th className="px-4 py-2.5 text-right font-semibold text-gray-600">작업</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  로딩 중...
                </td>
              </tr>
            ) : docs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  업로드된 문서가 없습니다.
                </td>
              </tr>
            ) : (
              docs.map((doc) => (
                <tr key={doc.doc_id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono text-gray-500 text-[10px]">
                    {doc.doc_id}
                  </td>
                  <td className="px-4 py-2.5 text-slate-700">{doc.filename}</td>
                  <td className="px-4 py-2.5 text-gray-500">{doc.category}</td>
                  <td className="px-4 py-2.5 text-gray-500">{doc.chunk_count}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => setDeleteTarget(doc.doc_id)}
                      className="text-red-500 hover:underline"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="문서 삭제"
        message="이 문서와 모든 청크를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."
        confirmLabel="삭제"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
