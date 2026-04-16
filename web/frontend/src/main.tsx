import './sentry'  // ← 반드시 가장 먼저 import (부수효과로 Sentry init)
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Sentry } from './sentry'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<div style={{ padding: 20 }}>오류가 발생했습니다. 새로고침해 주세요.</div>}>
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
