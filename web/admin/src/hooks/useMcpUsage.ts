import { useEffect, useMemo, useState } from "react";
import { rangeToParams } from "../components/RangeFilterBar";
import type { LogRange, McpUsage } from "../types/admin";
import { useAdminApi } from "./useAdminApi";
import { useAuth } from "./useAuth";

/** 기간(range)이 바뀔 때마다 MCP 사용량 집계를 다시 조회한다. */
export function useMcpUsage(range: LogRange) {
  const { token, clearToken } = useAuth();
  const { get, loading, error } = useAdminApi({ token, onUnauthorized: clearToken });
  const [usage, setUsage] = useState<McpUsage | null>(null);

  const params = useMemo(() => rangeToParams(range), [range]);

  useEffect(() => {
    get<McpUsage>("/mcp-usage", params).then((data) => {
      if (data) setUsage(data);
    });
  }, [get, params]);

  return { usage, loading, error };
}
