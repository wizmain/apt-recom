import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { TokenInput } from "./components/TokenInput";
import { useAuth } from "./hooks/useAuth";
import { Dashboard } from "./pages/Dashboard";
import { DataManagement } from "./pages/DataManagement";
import { BatchMonitor } from "./pages/BatchMonitor";
import { Feedback } from "./pages/Feedback";
import { Scoring } from "./pages/Scoring";
import { Knowledge } from "./pages/Knowledge";
import { CommonCode } from "./pages/CommonCode";
import { MgmtCost } from "./pages/MgmtCost";

function App() {
  const { setToken, clearToken, isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <TokenInput onSubmit={setToken} />;
  }

  return (
    <BrowserRouter>
      <div className="flex min-h-dvh">
        <Sidebar />
        <main className="flex-1 p-5 bg-slate-100 overflow-y-auto">
          <Routes>
            <Route path="/admin" element={<Dashboard />} />
            <Route path="/admin/data" element={<DataManagement />} />
            <Route path="/admin/batch" element={<BatchMonitor />} />
            <Route path="/admin/feedback" element={<Feedback />} />
            <Route path="/admin/scoring" element={<Scoring />} />
            <Route path="/admin/knowledge" element={<Knowledge />} />
            <Route path="/admin/codes" element={<CommonCode />} />
            <Route path="/admin/mgmt-cost" element={<MgmtCost />} />
          </Routes>
        </main>
        <button
          onClick={clearToken}
          className="fixed top-3 right-3 text-xs text-gray-400 hover:text-red-500 transition-colors"
          title="로그아웃"
        >
          로그아웃
        </button>
      </div>
    </BrowserRouter>
  );
}

export default App;
