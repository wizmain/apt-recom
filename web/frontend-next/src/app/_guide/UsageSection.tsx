import Section from "./Section";

/**
 * /guide — 사이트 사용 방법 섹션.
 *
 * NudgeBar / HomeShell 에서 실제로 쓰이는 버튼 아이콘(🔍, 🔽, ⚙, 💬) 을 그대로
 * 재사용해 사용자가 화면과 스텝을 1:1 로 매핑할 수 있도록 한다.
 */

interface Step {
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    title: "지역·단지명 검색",
    body: "상단 🔍 검색창에 \"강남구\" 같은 지역이나 \"래미안\" 같은 단지명을 입력하고 Enter. 지역과 아파트 이름을 동시에 지원하며, 동명(同名) 지역이 여러 곳이면 후보 드롭다운에서 선택한다.",
  },
  {
    title: "라이프스타일(넛지) 선택",
    body: "상단 칩에서 출퇴근·가성비·신혼부부·시니어·반려동물·자연친화·안전·교육·투자 중 관심 항목을 조합한다. 여러 개 동시 선택 가능하며, 선택한 조합에 맞춰 NUDGE 점수(0~100) 가 재계산된다.",
  },
  {
    title: "결과 카드·지도에서 확인",
    body: "좌측 결과 카드와 지도 마커에서 NUDGE 점수 순으로 추천 단지를 확인. 마커 클릭 또는 카드 클릭으로 해당 단지로 초점이 이동한다.",
  },
  {
    title: "🔽 필터로 조건 좁히기",
    body: "필터 버튼에서 준공연도·전용면적·가격대(매매·전세·월세) 범위를 설정. 활성 필터 개수는 버튼 옆에 숫자로 표시된다.",
  },
  {
    title: "⚙ 가중치로 스코어링 커스터마이즈",
    body: "가중치 드로어에서 교통·교육·안전·편의·가격 등 항목별 중요도를 직접 조정하면 추천 점수가 실시간으로 재계산된다.",
  },
  {
    title: "상세 보기·비교",
    body: "카드를 클릭하면 기본 정보·NUDGE 점수·학군 배정·시설 접근성·최근 거래이력을 한 화면에서 확인할 수 있고, 여러 단지를 선택하면 비교 모달에서 매트릭스로 대조할 수 있다.",
  },
  {
    title: "💬 AI 챗봇으로 자연어 질의",
    body: "우하단 챗봇 버튼으로 \"강남구에서 출퇴근 좋은 30평대 아파트 추천해줘\" 같은 자연어 요청을 보낼 수 있다. OpenAI·Claude·Gemini 중 백엔드 설정된 모델이 응답한다.",
  },
  {
    title: "실거래 대시보드 모드",
    body: "상단 탭에서 \"실거래대시보드\" 로 전환하면 시군구 월별 거래량·평균가 추이를 차트로 확인할 수 있다. 지도 모드와 독립된 뷰이다.",
  },
];

export default function UsageSection() {
  return (
    <Section
      id="usage"
      title="사이트 사용 방법"
      description="지도 기반 아파트 탐색 → 넛지 점수 확인 → 상세·비교 → 챗봇 질의까지 기본 흐름을 안내합니다."
    >
      <ol className="space-y-4 pl-0">
        {STEPS.map((step, idx) => (
          <li key={step.title} className="flex gap-3">
            <span
              className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full
                         bg-blue-600 text-xs font-semibold text-white"
              aria-hidden
            >
              {idx + 1}
            </span>
            <div>
              <h3 className="text-base font-semibold text-gray-900">{step.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-gray-700">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/** /guide/page.tsx 의 HowTo JSON-LD 에서 재사용. */
export const usageSteps = STEPS;
