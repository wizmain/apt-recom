#!/bin/bash
# kakao_poi_coord_pipeline 사이클 자동 반복 (D안: Local generate → Railway 복제).
# Kakao API 호출은 Local 한 번만, Railway candidates는 Local 결과 그대로 복제.
# 양쪽 dry-run이 다르면 중단. 양쪽 0이면 정상 종료.
#
# 사용:
#   bash batch/run_kakao_coord_loop.sh                # 기본 sources=vworld
#   bash batch/run_kakao_coord_loop.sh kakao_address  # 특정 출처만 보정
#   bash batch/run_kakao_coord_loop.sh vworld,kakao_address  # 콤마 구분 다중

set -u
PY=".venv/bin/python"
PIPE="batch.kakao_poi_coord_pipeline"
SOURCES="${1:-vworld}"
NO_PROGRESS_LIMIT="${NO_PROGRESS_LIMIT:-3}"
export SOURCES_FILTER="$SOURCES"
echo "## Sources to correct: $SOURCES"
echo "## Auto-stop after $NO_PROGRESS_LIMIT consecutive cycles with 0 auto_approved"

no_progress=0

cycle=0
while true; do
  cycle=$((cycle + 1))
  echo ""
  echo "########## Cycle $cycle start $(date '+%Y-%m-%d %H:%M:%S') ##########"

  echo "[1/5] local generate (sources=$SOURCES)"
  if ! $PY -m $PIPE generate --target local --limit 1000 --sources "$SOURCES" 2>&1 | tail -3; then
    echo "ABORT: local generate failed"; exit 1
  fi

  echo "[2/5] replicate local pending candidates -> railway"
  if ! $PY - <<'PYEOF'
import os, psycopg2, psycopg2.extras
from dotenv import load_dotenv
load_dotenv('.env')
sources = [s.strip() for s in os.environ.get('SOURCES_FILTER', 'vworld').split(',') if s.strip()]
local = psycopg2.connect(os.getenv('DATABASE_URL'))
rail = psycopg2.connect(os.getenv('RAILWAY_DATABASE_URL'))
lcur = local.cursor()
rcur = rail.cursor()
lcur.execute("""
    SELECT c.pnu, c.rank, c.query, c.kakao_place_id, c.place_name, c.category_name,
           c.address_name, c.road_address_name, c.lat, c.lng, c.distance_m,
           c.name_score, c.address_score, c.total_score, c.match_status, c.reason, c.coord_source
    FROM apt_coord_candidates c
    JOIN apartments a ON a.pnu = c.pnu
    WHERE a.coord_source = ANY(%s)
""", (sources,))
rows = lcur.fetchall()
print(f"  rows from local (pending in {sources}): {len(rows)}")
if rows:
    psycopg2.extras.execute_values(rcur, """
        INSERT INTO apt_coord_candidates (
            pnu, rank, query, kakao_place_id, place_name, category_name,
            address_name, road_address_name, lat, lng, distance_m,
            name_score, address_score, total_score, match_status, reason, coord_source
        ) VALUES %s
        ON CONFLICT (pnu, kakao_place_id) DO UPDATE SET
            rank=EXCLUDED.rank, query=EXCLUDED.query,
            place_name=EXCLUDED.place_name, category_name=EXCLUDED.category_name,
            address_name=EXCLUDED.address_name, road_address_name=EXCLUDED.road_address_name,
            lat=EXCLUDED.lat, lng=EXCLUDED.lng, distance_m=EXCLUDED.distance_m,
            name_score=EXCLUDED.name_score, address_score=EXCLUDED.address_score,
            total_score=EXCLUDED.total_score, match_status=EXCLUDED.match_status,
            reason=EXCLUDED.reason, coord_source=EXCLUDED.coord_source,
            generated_at=now()
    """, rows, page_size=500)
    rail.commit()
    print("  upserted to railway")
local.close(); rail.close()
PYEOF
  then
    echo "ABORT: replication failed"; exit 1
  fi

  echo "[3/5] both dry-run"
  DRY_OUT=$($PY -m $PIPE apply --target both --dry-run 2>&1)
  echo "$DRY_OUT"
  LOCAL_N=$(echo "$DRY_OUT" | grep '\[local\]' | grep -oE '적용: [0-9]+건' | grep -oE '[0-9]+')
  RAIL_N=$(echo "$DRY_OUT" | grep '\[railway\]' | grep -oE '적용: [0-9]+건' | grep -oE '[0-9]+')
  if [ -z "$LOCAL_N" ] || [ -z "$RAIL_N" ]; then
    echo "ABORT: cannot parse dry-run output"; exit 1
  fi
  if [ "$LOCAL_N" != "$RAIL_N" ]; then
    echo "ABORT: dry-run mismatch local=$LOCAL_N railway=$RAIL_N"; exit 1
  fi

  if [ "$LOCAL_N" != "0" ]; then
    echo "[4/5] apply both ($LOCAL_N rows each)"
    if ! $PY -m $PIPE apply --target both 2>&1 | tail -3; then
      echo "ABORT: apply both failed"; exit 1
    fi
    no_progress=0
  else
    no_progress=$((no_progress + 1))
    echo "[4/5] apply skipped (no auto_approved this cycle; consecutive=$no_progress/$NO_PROGRESS_LIMIT)"
    if [ "$no_progress" -ge "$NO_PROGRESS_LIMIT" ]; then
      echo "STOP: $no_progress consecutive cycles produced 0 auto_approved — likely API quota exhausted or remaining targets are unprocessable. Halting to avoid wasted calls."
      break
    fi
  fi

  echo "[5/5] verify + check generate targets remaining"
  REMAINING_TARGETS=$($PY - <<'PYEOF'
import os, psycopg2
from dotenv import load_dotenv
load_dotenv('.env')
sources = [s.strip() for s in os.environ.get('SOURCES_FILTER', 'vworld').split(',') if s.strip()]
remaining_local = 0
for dbname, var in [('local', 'DATABASE_URL'), ('railway', 'RAILWAY_DATABASE_URL')]:
    conn = psycopg2.connect(os.getenv(var))
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM apartments WHERE coord_source = ANY(%s)",
        (sources,),
    )
    pending = cur.fetchone()[0]
    cur.execute(
        "SELECT coord_source, count(*) FROM apartments "
        "WHERE coord_source IN ('kakao_apt_poi_auto','kakao_place_poi_auto') "
        "GROUP BY coord_source ORDER BY coord_source"
    )
    rows = cur.fetchall()
    label = "+".join(sources)
    print(f"  {dbname}: pending({label})={pending}  " + "  ".join(f"{s}={n}" for s, n in rows))
    if dbname == 'local':
        cur.execute("""
            SELECT count(*) FROM apartments a
            WHERE a.coord_source = ANY(%s) AND NOT EXISTS (
                SELECT 1 FROM apt_coord_candidates c WHERE c.pnu = a.pnu
            )
        """, (sources,))
        remaining_local = cur.fetchone()[0]
        print(f"  local generate targets remaining: {remaining_local}")
    conn.close()
print(f"REMAINING={remaining_local}")
PYEOF
)
  echo "$REMAINING_TARGETS"
  REMAINING=$(echo "$REMAINING_TARGETS" | grep -oE 'REMAINING=[0-9]+' | cut -d= -f2)
  if [ -z "$REMAINING" ]; then
    echo "ABORT: cannot read remaining count"; exit 1
  fi
  if [ "$REMAINING" = "0" ]; then
    echo "All target apartments have candidates. Pipeline drained."
    break
  fi

  echo "########## Cycle $cycle end $(date '+%Y-%m-%d %H:%M:%S') (remaining targets: $REMAINING) ##########"
done

echo ""
echo "##########  ALL CYCLES DONE  $(date '+%Y-%m-%d %H:%M:%S')  ##########"
