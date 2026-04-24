"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-4 text-center">
      <div className="text-5xl">⚠️</div>
      <h1 className="mt-4 text-xl font-bold text-gray-900">
        문제가 발생했습니다
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        일시적인 오류일 수 있습니다. 잠시 후 다시 시도해주세요.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        다시 시도
      </button>
    </main>
  );
}
