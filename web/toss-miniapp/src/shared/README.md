# shared/ (synced copy of `packages/shared`)

이 디렉토리는 `packages/shared/` 의 파일을 **inline 복사**한 것이다.

## 왜 file: 의존성 대신 복사인가
Metro/watchman 이 monorepo symlink 너머의 파일을 SHA-1 계산할 수 없어
`granite dev` 가 즉시 실패한다 (`SHA-1 ... is not computed`).
공식 해결책인 `metro.watchFolders` + `resolver.nodeModulesPaths` 만으로는 watchman 의 symlink 미지원을 회피할 수 없다.

## 동기화 정책
- 원본: `packages/shared/types/{apartment-list,dashboard}.ts`, `packages/shared/api/paths.ts`
- 미니앱이 사용하는 파일만 복사. 변경 시 양쪽 동기화.
- 향후 Metro 가 안정적으로 symlink 를 처리하면 다시 file: 의존성으로 전환.

원본 변경 시 본 디렉토리 동일 파일을 수동 갱신하거나
`scripts/sync-shared.sh` 같은 동기화 스크립트 추가 검토.
