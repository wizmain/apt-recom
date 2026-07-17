import type { Comparison } from "@/types/instagramContent";

export function ComparisonTable({ comparison }: { comparison: Comparison }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-bold text-gray-900">한눈에 비교</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="p-2 text-left font-medium text-gray-500">항목</th>
              {comparison.columns.map((col) => (
                <th key={col.name} className="p-2 text-left font-bold text-gray-900">
                  {col.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {comparison.row_labels.map((label, rowIndex) => (
              <tr key={label}>
                <td className="p-2 text-gray-500">{label}</td>
                {comparison.columns.map((col) => (
                  <td key={col.name} className="p-2 font-medium text-gray-900">
                    {col.values[rowIndex]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
