import type { Narrative } from "@/types/instagramContent";

export function NarrativeSection({ narrative }: { narrative: Narrative }) {
  if (narrative.why.length === 0 && !narrative.fit_for) return null;
  return (
    <section className="mt-8">
      {narrative.why.length > 0 && (
        <>
          <h2 className="text-lg font-bold text-gray-900">왜 이런 결과일까</h2>
          <ul className="mt-3 space-y-2 text-gray-700">
            {narrative.why.map((w) => (
              <li key={w}>· {w}</li>
            ))}
          </ul>
        </>
      )}
      {narrative.fit_for && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-gray-50 p-3 text-sm text-gray-800">
            {narrative.fit_for.a}
          </div>
          <div className="rounded-xl bg-gray-50 p-3 text-sm text-gray-800">
            {narrative.fit_for.b}
          </div>
        </div>
      )}
    </section>
  );
}
