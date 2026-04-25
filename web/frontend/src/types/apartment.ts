// 모든 도메인 타입은 packages/shared 로 이동했다.
// 이 파일은 기존 import 경로 ('../types/apartment') 호환을 위한 re-export shim.
// 신규 코드는 '@apt-recom/shared/types/apartment' 를 직접 import 한다.
export type {
  Apartment,
  TopContributor,
  ScoredApartment,
  NudgeWeights,
  MapBounds,
  SelectedRegion,
  RegionCandidate,
} from '@apt-recom/shared/types/apartment';
