#!/usr/bin/env bash
# 머지 후 main CI 를 완료까지 폴링 — 머지 커밋이 실제로 트리거한 워크플로 전부.
#
# PostToolUse async 훅(asyncRewake)으로 백그라운드 실행되며, 결과를 stdout 으로
# 출력하고 exit 2 로 모델을 깨운다(CI 완료 시 1회만).
#
# 감시 대상은 워크플로 이름 하드코딩이 아니라 "머지 커밋 SHA 로 등록된 push
# run 전부"다 — 과거에는 ci-frontend-next.yml 을 고정 감시해서, 해당 경로를
# 건드리지 않은 머지(path 필터 미트리거)마다 15분 타임아웃 오탐이 났다.
# path 필터로 아무 워크플로도 트리거되지 않으면 무음 종료(exit 0)한다.
set -uo pipefail

# [가드 1] 발동 명령 확인 — stdin 훅 JSON 의 command 에 'gh pr merge' 가 있을 때만 진행.
# matcher=Bash + if 필터가 다른 Bash 명령(git/gh run list 등)에도 발동하는 경우를 방어:
# 머지 명령이 아니면 즉시 무음 종료(exit 0 → rewake 없음)해 중복 보고를 막는다.
payload=$(cat 2>/dev/null || true)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
case "$cmd" in
  *"gh pr merge"*) ;;
  *) exit 0 ;;
esac

# [가드 2] 중복 실행 방지 — 여러 감시가 동시에 떠도 하나만 보고하도록 atomic lock.
# 정상/비정상 종료 모두 trap 으로 해제. 이미 감시 중이면 무음 종료.
LOCKDIR="${TMPDIR:-/tmp}/aptrecom_ci_watch.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT
# TERM/INT 로 죽어도 EXIT trap 이 돌아 lock 을 해제하도록 명시적으로 exit 경유.
# (stale lock 이 남으면 이후 모든 머지 감시가 무음 스킵된다.)
trap 'exit 143' TERM INT

REGISTER_WAIT=15       # 머지 push 후 run 등록 대기(초)
REGISTER_DEADLINE=120  # run 등록을 기다리는 최대 시간(초) — 이후에도 0건이면 미트리거로 판정
POLL_INTERVAL=20       # 폴링 간격(초)
DEADLINE=$((SECONDS + 900))   # 최대 15분

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 0

# 감시 기준 SHA — 머지 명령의 PR 번호에서 merge commit 을 얻는다.
# fallback 발동 조건: 명령에 PR 번호가 없거나(브랜치/URL 지정 머지) API 조회
# 실패 시에만 main HEAD SHA 를 쓴다 — 이 경우 머지 직후이므로 사실상 동일 커밋.
pr_num=$(printf '%s' "$cmd" | grep -oE 'gh pr merge[[:space:]]+[0-9]+' | grep -oE '[0-9]+' || true)
sha=""
if [ -n "$pr_num" ]; then
  sha=$(gh pr view "$pr_num" --json mergeCommit --jq '.mergeCommit.oid // empty' 2>/dev/null || true)
fi
if [ -z "$sha" ]; then
  sha=$(gh api "repos/{owner}/{repo}/branches/main" --jq '.commit.sha' 2>/dev/null || true)
fi
[ -z "$sha" ] && exit 0

# 해당 SHA 로 등록된 main push run 목록 (구버전 gh 호환을 위해 --commit 플래그
# 대신 headSha 클라이언트 필터 사용). gh 일시 실패(rate limit 등) 시에도
# 항상 유효한 JSON 배열을 출력한다 — 빈 문자열이 새어 나가면 후속 jq 판정이
# 깨져 폴링 루프가 오판한다.
_runs() {
  local out
  out=$(gh run list --branch main --event push --limit 20 \
    --json databaseId,status,conclusion,workflowName,url,headSha 2>/dev/null \
    | jq --arg sha "$sha" '[.[] | select(.headSha == $sha)]' 2>/dev/null) || out=""
  printf '%s' "${out:-[]}"
}

sleep "$REGISTER_WAIT"

# [1단계] run 등록 대기 — path 필터로 트리거된 워크플로가 하나도 없으면 무음 종료.
runs="[]"
count=0
while [ "$SECONDS" -lt "$REGISTER_DEADLINE" ]; do
  runs=$(_runs)
  count=$(printf '%s' "$runs" | jq 'length' 2>/dev/null) || count=0
  [ "${count:-0}" -gt 0 ] && break
  sleep "$POLL_INTERVAL"
done
if [ "${count:-0}" -eq 0 ]; then
  exit 0  # 머지 커밋이 어떤 워크플로도 트리거하지 않음 (path 필터) — 보고할 것 없음
fi

# [2단계] 전체 완료 대기 — 매 폴링마다 재조회해 늦게 등록된 run 도 포함한다.
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  runs=$(_runs)
  # gh 일시 실패로 빈 배열이 오면 완료 오판 방지 — 다음 폴링까지 보류.
  if [ "$(printf '%s' "$runs" | jq 'length' 2>/dev/null || echo 0)" -eq 0 ]; then
    sleep "$POLL_INTERVAL"; continue
  fi
  pending=$(printf '%s' "$runs" | jq '[.[] | select(.status != "completed")] | length' 2>/dev/null) || pending=1
  if [ "${pending:-1}" -eq 0 ]; then
    failed=$(printf '%s' "$runs" | jq '[.[] | select(.conclusion != "success" and .conclusion != "skipped")]' 2>/dev/null) || failed="[]"
    if [ "$(printf '%s' "$failed" | jq 'length' 2>/dev/null || echo 0)" -eq 0 ]; then
      echo "✅ 머지 후 main CI 성공 (${sha:0:7}):"
      printf '%s' "$runs" | jq -r '.[] | "  - \(.workflowName): \(.conclusion) — \(.url)"'
    else
      echo "❌ 머지 후 main CI 실패 (${sha:0:7}):"
      printf '%s' "$runs" | jq -r '.[] | "  - \(.workflowName): \(.conclusion) — \(.url)"'
      echo "--- 실패 로그(요약) ---"
      printf '%s' "$failed" | jq -r '.[].databaseId' | while read -r id; do
        gh run view "$id" --log-failed 2>/dev/null \
          | grep -iE "error|fail|✖|⨯|not found|cannot" | head -15
      done
    fi
    exit 2
  fi
  sleep "$POLL_INTERVAL"
done

pending_names=$(printf '%s' "$runs" | jq -r '[.[] | select(.status != "completed") | .workflowName] | join(", ")')
echo "⏱ 머지 후 main CI 가 15분 내 완료되지 않음 — 수동 확인 필요: ${pending_names}"
exit 2
