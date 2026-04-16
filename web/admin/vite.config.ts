import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 별도 Cloudflare Pages 도메인(예: admin.zibtori.pages.dev)에서 루트로 호스팅됨.
  // 같은 도메인의 /admin 경로로 옮기게 되면 base를 "/admin"으로 되돌릴 것.
  base: "/",
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
