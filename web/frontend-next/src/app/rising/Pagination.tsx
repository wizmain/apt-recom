interface PaginationProps {
  page: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (page: number) => void;
}

/** 이전/다음 + "n / N" 페이지네이션. */
export default function Pagination({ page, pageSize, totalCount, onPageChange }: PaginationProps) {
  const lastPage = Math.max(1, Math.ceil(totalCount / pageSize));
  if (lastPage <= 1) return null;
  const buttonClass =
    "rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 disabled:opacity-40";
  return (
    <nav className="mt-4 flex items-center justify-center gap-3" aria-label="페이지 이동">
      <button
        type="button"
        className={buttonClass}
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        이전
      </button>
      <span className="text-sm tabular-nums text-gray-600">
        {page} / {lastPage}
      </span>
      <button
        type="button"
        className={buttonClass}
        disabled={page >= lastPage}
        onClick={() => onPageChange(page + 1)}
      >
        다음
      </button>
    </nav>
  );
}
