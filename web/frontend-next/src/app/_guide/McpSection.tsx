import Section from "./Section";
import CodeBlock from "./CodeBlock";

/**
 * /guide — MCP (Model Context Protocol) 서버 연결 안내.
 *
 * docs/mcp-server.md 와 1:1 대응한다. 엔드포인트·도구 이름·예시 코드 중 하나라도
 * 변경될 때는 해당 문서와 이 파일을 동시에 수정한다.
 */

const MCP_ENDPOINT_PROD = "https://api.apt-recom.kr/mcp/";
const MCP_ENDPOINT_LOCAL = "http://localhost:8000/mcp/";

interface McpTool {
  name: string;
  description: string;
}

const TOOLS: McpTool[] = [
  { name: "search_apartments", description: "지역·단지명 키워드 + 라이프스타일 항목으로 NUDGE 스코어 순 추천" },
  { name: "get_apartment_detail", description: "단일 아파트 전체 프로필 (기본정보·점수·시설·학군·최근 거래)" },
  { name: "compare_apartments", description: "2~5개 단지 매트릭스 비교" },
  { name: "get_similar_apartments", description: "위치/가격/라이프스타일/종합 기준 유사 단지 추천" },
  { name: "get_market_trend", description: "시군구 월별 거래량·평균가 추이" },
  { name: "get_school_info", description: "아파트의 초·중·고 학군 배정 정보" },
  { name: "get_dashboard_info", description: "시군구 거래 동향 대시보드 요약" },
];

const CLAUDE_DESKTOP_CONFIG = `{
  "mcpServers": {
    "apt-recom": {
      "url": "https://api.apt-recom.kr/mcp/"
    }
  }
}`;

const CURSOR_CONFIG = CLAUDE_DESKTOP_CONFIG;

const CLAUDE_CODE_CLI = `claude mcp add --transport http apt-recom https://api.apt-recom.kr/mcp/`;

const PYTHON_SDK = `from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

async with streamablehttp_client("https://api.apt-recom.kr/mcp/") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(
            "search_apartments",
            arguments={"keyword": "자양동", "nudges": ["commute", "education"], "top_n": 5},
        )`;

const MCP_INSPECTOR = `npx @modelcontextprotocol/inspector
# 접속 URL: http://localhost:8000/mcp/  (Transport: Streamable HTTP)`;

export default function McpSection() {
  return (
    <Section
      id="mcp"
      title="MCP 서버 연결 안내"
      description="집토리는 Model Context Protocol (MCP) 표준을 구현해 Claude Desktop·Cursor·Claude Code 같은 AI 에이전트가 아파트 데이터를 직접 조회할 수 있습니다."
    >
      <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50/60 p-4 text-sm text-gray-800">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="font-semibold text-gray-700">엔드포인트</dt>
          <dd>
            <code className="rounded bg-white px-1.5 py-0.5 text-xs">{MCP_ENDPOINT_PROD}</code>
          </dd>
          <dt className="font-semibold text-gray-700">Transport</dt>
          <dd>Streamable HTTP (MCP 2025-11-25 spec)</dd>
          <dt className="font-semibold text-gray-700">Auth</dt>
          <dd>없음 (공개, stateless)</dd>
          <dt className="font-semibold text-gray-700">로컬 개발</dt>
          <dd>
            <code className="rounded bg-white px-1.5 py-0.5 text-xs">{MCP_ENDPOINT_LOCAL}</code>
          </dd>
        </dl>
      </div>

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">제공 도구 (7종)</h3>
      <div className="mb-6 overflow-hidden rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-3 py-2 w-56">이름</th>
              <th className="px-3 py-2">설명</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 text-gray-700">
            {TOOLS.map((tool) => (
              <tr key={tool.name}>
                <td className="px-3 py-2 font-mono text-xs text-blue-700">{tool.name}</td>
                <td className="px-3 py-2 text-sm">{tool.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">Claude Desktop</h3>
      <p className="mb-2 text-sm text-gray-700">
        macOS: <code className="text-xs">~/Library/Application Support/Claude/claude_desktop_config.json</code>
        {" "}· Windows: <code className="text-xs">%APPDATA%\Claude\claude_desktop_config.json</code>
      </p>
      <CodeBlock label="claude_desktop_config.json" code={CLAUDE_DESKTOP_CONFIG} />
      <p className="mb-6 text-xs text-gray-500">
        저장 후 Claude Desktop 재시작. 대화 창 상단 도구 아이콘에서 apt-recom 도구 7개가 보이면 연결 완료.
      </p>

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">Cursor</h3>
      <p className="mb-2 text-sm text-gray-700">
        <code className="text-xs">~/.cursor/mcp.json</code> 또는 프로젝트 루트 <code className="text-xs">.cursor/mcp.json</code>
      </p>
      <CodeBlock label=".cursor/mcp.json" code={CURSOR_CONFIG} />

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">Claude Code (CLI)</h3>
      <CodeBlock label="shell" code={CLAUDE_CODE_CLI} />

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">Python SDK (프로그래매틱 호출)</h3>
      <CodeBlock label="python" code={PYTHON_SDK} />

      <h3 className="mt-6 mb-3 text-base font-semibold text-gray-900">MCP Inspector 로 로컬 검증</h3>
      <p className="mb-2 text-sm text-gray-700">
        백엔드를 로컬에서 기동한 뒤, 공식 MCP Inspector GUI 로 엔드포인트와 도구 응답을 확인할 수 있습니다.
      </p>
      <CodeBlock label="shell" code={MCP_INSPECTOR} />

      <p className="mt-6 text-xs text-gray-500">
        상세 사양은 프로젝트 저장소의 <code className="text-xs">docs/mcp-server.md</code> 를 참고하세요.
      </p>
    </Section>
  );
}
