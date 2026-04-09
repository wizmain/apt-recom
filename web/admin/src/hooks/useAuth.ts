import { useState, useCallback } from "react";

const STORAGE_KEY = "admin_token";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  );

  const setToken = useCallback((newToken: string) => {
    localStorage.setItem(STORAGE_KEY, newToken);
    setTokenState(newToken);
  }, []);

  const clearToken = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setTokenState(null);
  }, []);

  return { token, setToken, clearToken, isAuthenticated: !!token };
}
