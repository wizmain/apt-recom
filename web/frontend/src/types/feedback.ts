// 모든 도메인 타입은 packages/shared 로 이동했다.
// 이 파일은 기존 import 경로 ('../types/feedback') 호환을 위한 re-export shim.
export type { FeedbackStats } from '@apt-recom/shared/types/feedback';
