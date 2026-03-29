# ADR-010: Railway + Cloudflare Pages 배포

- **상태**: Accepted
- **날짜**: 2026-03-21

## 맥락

개인 프로젝트로 월 운영 비용을 최소화하면서도 안정적인 배포가 필요했다.

## 결정

- **백엔드 + DB**: Railway (FastAPI + PostgreSQL 관리형)
- **프론트엔드**: Cloudflare Pages (정적 호스팅)

## 근거

- **비용**: 월 ~$8로 풀스택 서비스 운영 가능.
  - Railway: 백엔드 서버 + PostgreSQL (13개 테이블, 4,900만+ 행) — ~$8/월
  - Cloudflare Pages: React 정적 빌드 호스팅 — 무료
- **관리 편의**: Railway가 PostgreSQL 프로비저닝/백업을 자동 처리.
- **성능**: Cloudflare CDN으로 프론트엔드 글로벌 배포.
- **GitHub 통합**: 두 서비스 모두 GitHub push 시 자동 배포 지원.

## 트레이드오프

- Railway 무료 티어 제한으로 트래픽이 많아지면 비용 증가.
- 백엔드와 프론트엔드가 다른 도메인이므로 CORS 설정 필요.
- Railway의 PostgreSQL은 단일 리전이라 글로벌 지연이 있을 수 있다.

## 결과

- CORS: FastAPI에서 `allow_origins=["*"]` 설정 (프론트엔드 도메인 제한 가능).
- 환경변수: Railway에서 `DATABASE_URL` 자동 주입, 프론트엔드는 `VITE_API_BASE_URL`로 백엔드 URL 지정.
- ChromaDB 벡터 데이터는 Railway 볼륨에 persist.
