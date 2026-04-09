import { NavLink } from "react-router-dom";

interface MenuItem {
  path: string;
  icon: string;
  label: string;
}

const MENU_ITEMS: MenuItem[] = [
  { path: "/admin", icon: "📊", label: "대시보드" },
  { path: "/admin/data", icon: "🗄", label: "데이터" },
  { path: "/admin/batch", icon: "⚙", label: "배치" },
  { path: "/admin/feedback", icon: "💬", label: "피드백" },
  { path: "/admin/scoring", icon: "🎯", label: "스코어링" },
  { path: "/admin/knowledge", icon: "📚", label: "지식베이스" },
  { path: "/admin/codes", icon: "🏷", label: "공통코드" },
  { path: "/admin/mgmt-cost", icon: "💰", label: "관리비 등록" },
];

export function Sidebar() {
  return (
    <nav className="flex flex-col bg-[#0f172a] text-white flex-shrink-0 w-48">
      <div className="py-3 px-4 font-extrabold text-amber-400 text-sm tracking-tight">
        집토리 Admin
      </div>

      <div className="flex flex-col gap-1 w-full px-2">
        {MENU_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/admin"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-blue-800 text-white"
                  : "text-gray-400 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            <span className="text-base flex-shrink-0 w-6 text-center">
              {item.icon}
            </span>
            <span className="whitespace-nowrap">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
