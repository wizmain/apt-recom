import { useState } from "react";

interface TokenInputProps {
  onSubmit: (token: string) => void;
}

export function TokenInput({ onSubmit }: TokenInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value.trim());
    }
  };

  return (
    <div className="flex items-center justify-center min-h-dvh bg-slate-100">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl shadow-sm p-8 w-full max-w-sm"
      >
        <div className="text-center mb-6">
          <div className="text-2xl font-bold text-amber-500 mb-1">집토리 Admin</div>
          <p className="text-sm text-gray-500">관리자 토큰을 입력하세요</p>
        </div>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="ADMIN_TOKEN"
          className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent mb-4"
          autoFocus
        />
        <button
          type="submit"
          className="w-full py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          로그인
        </button>
      </form>
    </div>
  );
}
