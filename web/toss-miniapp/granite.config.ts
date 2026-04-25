import { router } from '@granite-js/plugin-router';
import { hermes } from '@granite-js/plugin-hermes';
import { defineConfig } from '@granite-js/react-native/config';
import { appsInToss } from '@apps-in-toss/framework/plugins';

// Toss 콘솔 등록명: jiptori (Phase 0 에서 확정)
// scheme: intoss://jiptori/<page>
// icon: '' 은 개발 단계 임시값 — 출시 전 업로드 후 URL 로 교체
//
// shared 코드: src/shared/ 에 inline 복사 (packages/shared 와 동기화 유지).
// Metro/watchman 의 symlink 미지원 회피 — 자세한 사유는 src/shared/README.md.
export default defineConfig({
  appName: 'jiptori',
  scheme: 'jiptori',
  plugins: [
    router(),
    hermes(),
    ...appsInToss({
      target: '0.84.0',
      brand: {
        displayName: '집토리',
        primaryColor: '#3182F6',
        icon: '',
      },
      permissions: [],
    }),
  ],
});
