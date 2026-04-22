/**
 * 섹션 래퍼 — 제목 + 본문. Server/Client 경계 중립.
 *
 * 빈 본문 여부는 호출부 책임(섹션 자체 생략은 호출부에서 판단).
 */

export function Section({
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
