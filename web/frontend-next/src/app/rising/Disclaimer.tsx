const DISCLAIMER_TEXT =
  "국토교통부 아파트 매매 실거래 신고 자료를 바탕으로 한 참고 정보입니다. 등급과 변화율은 집토리가 계산한 값이며, 신고 시점·거래 정정·거래 건수에 따라 달라질 수 있습니다. 실제 매물 조건을 확인한 뒤 매매 여부를 직접 판단해 주세요.";

/** 면책 문구(스펙 §7.3 고정 문구) — 접이식. */
export default function Disclaimer() {
  return (
    <details className="mt-3 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-500">
      <summary className="cursor-pointer font-medium text-gray-600">
        데이터 안내
      </summary>
      <p className="mt-2 leading-relaxed">{DISCLAIMER_TEXT}</p>
    </details>
  );
}
