import { useState, useCallback } from "react";
import axios, { type AxiosRequestConfig } from "axios";
import { API_BASE } from "../config";

interface UseAdminApiOptions {
  token: string | null;
  onUnauthorized?: () => void;
}

export function useAdminApi({ token, onUnauthorized }: UseAdminApiOptions) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback(
    async <T = unknown>(
      method: "get" | "post" | "put" | "delete",
      path: string,
      data?: unknown,
      params?: Record<string, unknown>,
    ): Promise<T | null> => {
      setLoading(true);
      setError(null);
      try {
        const config: AxiosRequestConfig = {
          method,
          url: `${API_BASE}/api/admin${path}`,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          params,
          data,
        };
        const res = await axios(config);
        return res.data as T;
      } catch (err) {
        if (axios.isAxiosError(err)) {
          if (err.response?.status === 401) {
            onUnauthorized?.();
          }
          const detail = err.response?.data?.detail || err.message;
          setError(detail);
        } else {
          setError("요청 실패");
        }
        return null;
      } finally {
        setLoading(false);
      }
    },
    [token, onUnauthorized],
  );

  const get = useCallback(
    <T = unknown>(path: string, params?: Record<string, unknown>) =>
      request<T>("get", path, undefined, params),
    [request],
  );

  return { get, request, loading, error };
}
