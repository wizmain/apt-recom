#!/bin/bash
# 집토리 모바일 앱 통합 테스트
# 사용법: ./tests/integration.sh [scope]
# scope: all(기본), api, auto, type, nav, detail

set -euo pipefail

BACKEND="http://localhost:8000"
PYTHON="/Users/wizmain/Documents/workspace/apt-recom/.venv/bin/python3"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

PASS=0
FAIL=0
SCOPE="${1:-all}"

green() { echo -e "\033[32m✓ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m✗ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m━━━ $1 ━━━\033[0m"; }

# ─── 백엔드 헬스 체크 ───
check_backend() {
  header "백엔드 연결 확인"
  if curl -sf "$BACKEND/api/health" > /dev/null 2>&1; then
    green "백엔드 서버 응답 OK ($BACKEND)"
  else
    red "백엔드 서버 미응답 ($BACKEND)"
    echo "  → cd web/backend && ../../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000"
    return 1
  fi
}

# ─── TypeScript 타입 체크 ───
test_typescript() {
  header "TypeScript 타입 체크"
  cd "$APP_DIR"
  if npx tsc --noEmit 2>&1; then
    green "tsc --noEmit 통과"
  else
    red "tsc --noEmit 실패"
  fi
}

# ─── API 통합 테스트 ───
test_api() {
  header "API 통합 테스트"

  # 1. 아파트 검색
  local search_count
  search_count=$(curl -sf "$BACKEND/api/apartments/search" --get --data-urlencode "q=강남" \
    | $PYTHON -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$search_count" -gt 0 ]; then
    green "아파트 검색 API — 강남: ${search_count}건"
  else
    red "아파트 검색 API — 강남: 결과 없음"
  fi

  # 2. 넛지 가중치
  local weight_keys
  weight_keys=$(curl -sf "$BACKEND/api/nudge/weights" \
    | $PYTHON -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$weight_keys" -gt 0 ]; then
    green "넛지 가중치 API — ${weight_keys}개 넛지"
  else
    red "넛지 가중치 API — 응답 없음"
  fi

  # 3. 넛지 스코어링
  local score_count
  score_count=$(curl -sf -X POST "$BACKEND/api/nudge/score" \
    -H "Content-Type: application/json" \
    -d '{"nudges":["cost"],"weights":null,"top_n":5,"keywords":["강남"]}' \
    | $PYTHON -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$score_count" -gt 0 ]; then
    green "넛지 스코어링 API — 가성비+강남: ${score_count}건"
  else
    red "넛지 스코어링 API — 결과 없음"
  fi

  # 4. 넛지 스코어링 + 필터
  local filter_count
  filter_count=$(curl -sf -X POST "$BACKEND/api/nudge/score" \
    -H "Content-Type: application/json" \
    -d '{"nudges":["cost"],"weights":null,"top_n":5,"keywords":["강남"],"min_area":60,"max_area":85}' \
    | $PYTHON -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$filter_count" -gt 0 ]; then
    green "넛지 + 필터 API — 60~85㎡: ${filter_count}건"
  else
    red "넛지 + 필터 API — 결과 없음"
  fi

  # 5. 아파트 상세
  local pnu
  pnu=$(curl -sf "$BACKEND/api/apartments/search" --get --data-urlencode "q=강남" \
    | $PYTHON -c "import sys,json; print(json.load(sys.stdin)[0]['pnu'])" 2>/dev/null || echo "")
  if [ -n "$pnu" ]; then
    local detail_status
    detail_status=$(curl -sf -o /dev/null -w "%{http_code}" "$BACKEND/api/apartment/$pnu")
    if [ "$detail_status" = "200" ]; then
      green "아파트 상세 API — pnu:$pnu → 200"
    else
      red "아파트 상세 API — pnu:$pnu → $detail_status"
    fi

    # 6. 거래 내역
    local trade_status
    trade_status=$(curl -sf -o /dev/null -w "%{http_code}" "$BACKEND/api/apartment/$pnu/trades")
    if [ "$trade_status" = "200" ]; then
      green "거래 내역 API — pnu:$pnu → 200"
    else
      red "거래 내역 API — pnu:$pnu → $trade_status"
    fi
  else
    red "PNU 조회 실패 — 상세/거래 테스트 건너뜀"
  fi

  # 7. 카카오맵 HTML
  local map_status
  map_status=$(curl -sf -o /dev/null -w "%{http_code}" "$BACKEND/api/map")
  if [ "$map_status" = "200" ]; then
    green "카카오맵 HTML API → 200"
  else
    red "카카오맵 HTML API → $map_status"
  fi

  # 8. 채팅 스트림 (연결만 확인)
  local chat_status
  chat_status=$(curl -sf -o /dev/null -w "%{http_code}" -X POST "$BACKEND/api/chat/stream" \
    -H "Content-Type: application/json" \
    -d '{"message":"테스트","conversation":[],"context":{}}' \
    --max-time 5 2>/dev/null || echo "timeout")
  if [ "$chat_status" = "200" ] || [ "$chat_status" = "timeout" ]; then
    green "채팅 스트림 API — 연결 OK"
  else
    red "채팅 스트림 API — $chat_status"
  fi
}

# ─── 네비게이션 구조 확인 ───
test_navigation() {
  header "라우트/네비게이션 구조"

  local routes=("app/_layout.tsx" "app/(tabs)/_layout.tsx" "app/(tabs)/index.tsx"
                "app/(tabs)/search.tsx" "app/(tabs)/chat.tsx" "app/(tabs)/settings.tsx"
                "app/detail/[pnu].tsx")
  for route in "${routes[@]}"; do
    if [ -f "$APP_DIR/$route" ]; then
      green "라우트 파일: $route"
    else
      red "라우트 파일 누락: $route"
    fi
  done

  # _layout.tsx에 detail 등록 확인
  if grep -q "detail" "$APP_DIR/app/_layout.tsx" 2>/dev/null; then
    green "루트 레이아웃에 detail 라우트 등록됨"
  else
    red "루트 레이아웃에 detail 라우트 미등록"
  fi
}

# ─── 상세 화면 데이터 검증 ───
test_detail() {
  header "상세 화면 데이터 검증"

  local pnu
  pnu=$(curl -sf "$BACKEND/api/apartments/search" --get --data-urlencode "q=강남" \
    | $PYTHON -c "import sys,json; print(json.load(sys.stdin)[0]['pnu'])" 2>/dev/null || echo "")

  if [ -z "$pnu" ]; then
    red "PNU 조회 실패 — 상세 테스트 건너뜀"
    return
  fi

  local detail
  detail=$(curl -sf "$BACKEND/api/apartment/$pnu")

  # 기본정보
  local has_basic
  has_basic=$($PYTHON -c "import sys,json; d=json.loads('$detail' if len('$detail')<10000 else sys.stdin.read()); print('yes' if d.get('basic',{}).get('bld_nm') else 'no')" <<< "$detail" 2>/dev/null || echo "no")
  if [ "$has_basic" = "yes" ]; then
    green "상세 — 기본정보 (bld_nm) 존재"
  else
    red "상세 — 기본정보 누락"
  fi

  # 넛지 점수
  local score_count
  score_count=$($PYTHON -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('scores',{})))" <<< "$detail" 2>/dev/null || echo "0")
  if [ "$score_count" -gt 0 ]; then
    green "상세 — 넛지 점수 ${score_count}개"
  else
    red "상세 — 넛지 점수 없음"
  fi

  # 시설 요약
  local facility_count
  facility_count=$($PYTHON -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('facility_summary',{})))" <<< "$detail" 2>/dev/null || echo "0")
  if [ "$facility_count" -gt 0 ]; then
    green "상세 — 시설 요약 ${facility_count}종"
  else
    red "상세 — 시설 요약 없음"
  fi
}

# ─── API 자동 탐지 테스트 ───
test_api_auto() {
  header "API 자동 탐지 (openapi.json)"

  # 샘플 PNU 조회
  local sample_pnu
  sample_pnu=$(curl -sf "$BACKEND/api/apartments/search" --get --data-urlencode "q=강남" \
    | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d[0]['pnu'] if d else '')" 2>/dev/null || echo "")

  # Python 자동 탐지 스크립트 실행
  local output
  output=$($PYTHON "$SCRIPT_DIR/auto_api_test.py" "$BACKEND" "$sample_pnu" 2>/dev/null)

  # 결과 출력 (RESULT 줄 제외)
  echo "$output" | grep -v "^RESULT:"

  # 카운터 추출
  local result_line
  result_line=$(echo "$output" | grep "^RESULT:" || echo "RESULT:0:0")
  local auto_pass auto_fail
  auto_pass=$(echo "$result_line" | cut -d: -f2)
  auto_fail=$(echo "$result_line" | cut -d: -f3)
  PASS=$((PASS + auto_pass))
  FAIL=$((FAIL + auto_fail))
}

# ─── 라우트 자동 탐지 ───
test_nav_auto() {
  header "라우트 자동 탐지"

  # app/ 디렉토리에서 .tsx 파일 자동 수집
  local route_count=0
  while IFS= read -r route; do
    local rel_path="${route#$APP_DIR/}"
    green "[자동] 라우트: $rel_path"
    route_count=$((route_count + 1))
  done < <(find "$APP_DIR/app" -name "*.tsx" -type f | sort)

  if [ "$route_count" -eq 0 ]; then
    red "라우트 파일이 하나도 없음"
  fi

  # _layout.tsx에서 Stack.Screen 등록 확인
  local layout_file="$APP_DIR/app/_layout.tsx"
  if [ -f "$layout_file" ]; then
    # app/ 하위 동적 라우트 디렉토리 탐지 (detail, 등)
    while IFS= read -r dir; do
      local dir_name
      dir_name=$(basename "$dir")
      # (tabs)는 자동 등록이므로 제외, 나머지 확인
      if [ "$dir_name" != "(tabs)" ] && [ "$dir_name" != "app" ]; then
        if grep -q "$dir_name" "$layout_file" 2>/dev/null; then
          green "[자동] 루트 레이아웃에 '$dir_name' 등록 확인"
        else
          red "[자동] 루트 레이아웃에 '$dir_name' 미등록"
        fi
      fi
    done < <(find "$APP_DIR/app" -mindepth 1 -maxdepth 1 -type d | sort)
  fi
}

# ─── 실행 ───
echo "🐿️  집토리 모바일 앱 통합 테스트"
echo "   scope: $SCOPE"

check_backend || exit 1

case "$SCOPE" in
  all)
    test_typescript
    test_api
    test_api_auto
    test_nav_auto
    test_detail
    ;;
  api)    test_api ;;
  auto)
    test_api_auto
    test_nav_auto
    ;;
  type)   test_typescript ;;
  nav)    test_nav_auto ;;
  detail) test_detail ;;
  *)
    echo "사용법: $0 [all|api|auto|type|nav|detail]"
    exit 1
    ;;
esac

# ─── 결과 ───
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
  echo -e "\033[32m전체 통과: ${PASS}건 성공, 0건 실패\033[0m"
else
  echo -e "\033[31m결과: ${PASS}건 성공, ${FAIL}건 실패\033[0m"
  exit 1
fi
