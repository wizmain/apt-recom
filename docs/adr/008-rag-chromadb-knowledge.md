# ADR-008: ChromaDB 기반 RAG 지식 베이스

- **상태**: Accepted
- **날짜**: 2026-03-25

## 맥락

챗봇이 부동산 정책, 세금, 투자 가이드 등 DB에 없는 지식을 답변하려면 외부 문서를 참조해야 한다. PDF 문서를 업로드하고 자연어 검색할 수 있는 시스템이 필요했다.

## 결정

ChromaDB(로컬 persist) + LangChain TextSplitters + LLM 임베딩으로 RAG 파이프라인을 구축한다.

## 파이프라인

```
PDF 업로드 → PyMuPDF 텍스트 추출 → 500~1000토큰 청킹
           → LLM 임베딩 → ChromaDB 벡터 저장
           → 챗봇 Tool "search_knowledge" → 유사도 검색 → 답변 + 출처 표시
```

## 근거

- **로컬 실행**: ChromaDB는 별도 서버 없이 로컬 파일로 동작하여 인프라 부담이 없다.
- **비용 효율**: Pinecone 등 클라우드 벡터DB 대비 무료.
- **통합 용이**: 기존 LLM 프로바이더의 임베딩 API를 활용한다.

## 트레이드오프

- 대량 문서(수천 개)에서는 ChromaDB 성능이 떨어질 수 있다.
- 로컬 persist이므로 배포 시 볼륨 마운트가 필요하다.
- 임베딩 모델 변경 시 전체 재인덱싱이 필요하다.

## 결과

- 관리 API: `POST /api/knowledge/upload`, `GET /api/knowledge/list`, `DELETE /api/knowledge/{doc_id}`
- 챗봇 Tool 6번(`search_knowledge`)이 RAG 검색을 수행한다.
- 답변 시 출처 PDF를 명시한다.
