import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-4 text-center">
      <div className="text-5xl">🗺️</div>
      <h1 className="mt-4 text-xl font-bold text-gray-900">
        지역을 찾을 수 없습니다
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        요청하신 시군구 코드에 해당하는 지역 정보를 찾지 못했습니다.
      </p>
      <Link
        href="/region"
        className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
      >
        전체 지역 목록
      </Link>
    </main>
  );
}
