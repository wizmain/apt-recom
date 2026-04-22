/**
 * 빈 상태 안내 — 섹션 내 데이터 없을 때 표시.
 * Server/Client 경계 중립.
 */

export function Empty({ text = "정보 없음" }: { text?: string }) {
  return <p className="text-sm text-gray-400">{text}</p>;
}
