/**
 * /guide 페이지 내부 공용 섹션 래퍼.
 *
 * about/page.tsx 의 Section 과 형태는 비슷하지만, 가이드는 id 앵커(해시 네비용) 와
 * 선택적 설명(description) 을 추가로 받는다.
 */

export default function Section({
  id,
  title,
  description,
  children,
}: {
  id?: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mt-10 scroll-mt-20">
      <h2 className="mb-3 text-xl font-semibold text-gray-800">{title}</h2>
      {description && (
        <p className="mb-4 text-sm leading-relaxed text-gray-600">{description}</p>
      )}
      {children}
    </section>
  );
}
