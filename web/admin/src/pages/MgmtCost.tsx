import { useAuth } from "../hooks/useAuth";
import { MgmtCostUpload } from "../components/MgmtCostUpload";

export function MgmtCost() {
  const { token } = useAuth();

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">관리비 등록</h1>
      <MgmtCostUpload token={token} />
    </div>
  );
}
