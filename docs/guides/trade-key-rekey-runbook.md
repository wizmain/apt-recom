# 거래 키 고유번호 전환 — 운영(Railway) 런북 (ADR-015 2단계)

- 설계서: `docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md` (4-4 운영 반영 순서, 4-5 검증·롤백)
- ADR: `docs/adr/015-trade-key-official-id.md`
- 대상 코드: `batch/remap_official_keys.py`(기존 고유번호 키 매핑 재판정), `batch/rekey_trades.py`(과거 거래 키 변경)
- **운영 DB 작업은 단계마다 사용자 허락이 필요하다** (CLAUDE.md 금지 사항 — 허락은 그 작업 한 건에만 유효).

## 0. 사전 조건

| 항목 | 확인 방법 | 기준 |
|---|---|---|
| 1단계(적재·매핑 전환) 운영 반영 | `railway deployment list --service apt-recom` + 거래 배치 로그 `고유번호 키 매핑 N건` | PR #315 이후 배포 SUCCESS |
| 매핑 검증 강화 반영 | main 에 PR #319·#320 포함 | GitHub Actions 거래 배치가 최신 main 으로 실행 중 |
| legacy 부분 인덱스 | `SELECT indexname, indisvalid … WHERE indexname LIKE 'idx_%legacy_seq'` | 2개, valid (2026-10-14 생성 완료) |
| 로컬 리허설 | `common_code` group `rekey_trades_checkpoint` (로컬) | 252/253 done (2026-10-15) |
| 실행 시간대 | 거래 배치 12:00·00:00 KST(약 15분), 인스타 데일리 동기화 시간과 겹치지 않게 | 배치 사이 + 트래픽 적은 시간 |

## 1. 로컬 리허설 실측 (2026-10-15)

| 항목 | 값 |
|---|---|
| rekey 253개 구 전체 | 약 16분 (로컬, 네트워크 왕복 없음) |
| 결과 | done 252 / failed 1 (50130 — 아래 6장) |
| 고유번호 키로 바뀐 행 | 매매 약 85%, 전월세 약 83% (dry-run 계획 95% 중 매핑 불가 키는 되돌림) |
| 매핑 없는 행 | 0 (rekey 불변식이 보장) |
| 테이블 크기 | trade_history 976MB → 1,684MB, rent_history 1,970MB → 3,546MB (UPDATE 로 dead tuple 증가, VACUUM(ANALYZE) 로는 줄지 않음) |
| 기준 사례 | 대방대림(1159010800005010000) = 1993년 600건, 상도1동대림(1159010200004110000) = 1995년 130건 |

**운영 소요는 로컬보다 훨씬 길다** — 구마다 조회·UPDATE·감사가 네트워크를 왕복한다. `--limit` 으로 나눠 실행하고 첫 묶음의 소요로 전체를 추정한다.

## 2. 백업 (재판정 직전)

재판정·rekey 는 `trade_apt_mapping`·`common_code` 를 바꾼다. 거래 행은 `legacy_apt_seq` 로 되돌릴 수 있지만 매핑 삭제·교체는 자동 롤백이 없으므로 두 테이블을 먼저 떠 둔다(약 20MB).

```bash
PGD=/opt/homebrew/opt/postgresql@18/bin/pg_dump
$PGD "$RAILWAY_DATABASE_URL" --format=custom --no-owner --no-acl \
  -t trade_apt_mapping -t common_code \
  --file="$HOME/apt-recom-backups/railway_mapping_before_rekey_$(date +%Y%m%d).dump"
```

## 3. 재판정 (remap)

```bash
.venv/bin/python -m batch.remap_official_keys --target railway --dry-run \
  --report reports/rekey/remap_railway_dryrun_$(date +%Y%m%d).tsv
```

**검토 (apply 전 필수)**
- 로그의 유지/교체/삭제/`blocked_delete` 건수, **'보이던 행 손실'** 합계. 손실이 수십 행을 넘으면 TSV 의 `old_pnu_exists=1` 행을 하나씩 확인하고 멈춘다.
- 교체 목록(old→new PNU)이 같은 단지로 보이는지 몇 건 표본 확인.
- `blocked_delete` 는 rekey 가 이미 끝난 구 — 운영 첫 실행이면 0 이어야 정상.
- 재판정 조회는 거래 테이블 전체 스캔 약 4회(1회성).

```bash
.venv/bin/python -m batch.remap_official_keys --target railway --apply \
  --report reports/rekey/remap_railway_apply_$(date +%Y%m%d).tsv
```
`common_code` group `remap_official_keys_checkpoint` 에 새 체크포인트가 생겨야 rekey `--apply` 가 실행된다(순서 강제).

## 4. 과거 거래 키 변경 (rekey)

```bash
# 계획 (조회만)
.venv/bin/python -m batch.rekey_trades --target railway --dry-run > reports/rekey/rekey_railway_dryrun_$(date +%Y%m%d).log 2>&1

# 작은 구 20개부터 (작은 구부터 처리하도록 정렬돼 있음)
.venv/bin/python -m batch.rekey_trades --target railway --apply --limit 20 \
  > reports/rekey/rekey_railway_apply_1.log 2>&1
```
- 첫 묶음의 소요 시간으로 전체를 추정하고, `--limit` 을 늘려 반복한다(체크포인트로 이어서 실행 — done/failed/rolled_back 구는 건너뜀).
- 실행 중 거래 배치가 시작되면 배치가 "거래 쓰기 잠금 점유"로 **실패 기록**하고 멈춘다(정상 — 다음 회차에 진행). 가능하면 배치 사이에 묶음이 끝나도록 `--limit` 을 조절한다.
- 구마다 커밋 전 불변식(행 수·미매핑·귀속 변화·감사)을 검사하고, 실패한 구는 그 자리에서 롤백되어 `failed` 로 남는다.

## 5. 검증

```sql
-- 진행 현황
SELECT name AS status, COUNT(*) FROM common_code
WHERE group_id = 'rekey_trades_checkpoint' GROUP BY 1;

-- 매핑 없는 거래가 늘지 않았는지 (rekey 전과 비교)
SELECT COUNT(*) FROM trade_history t
WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq);

-- 기준 사례
SELECT m.pnu, t.build_year, COUNT(*) FROM trade_history t
JOIN trade_apt_mapping m ON m.apt_seq = t.apt_seq
WHERE m.pnu IN ('1159010800005010000', '1159010200004110000')
GROUP BY 1, 2 ORDER BY 1, 2;
-- 기대: 1159010800005010000 → 1993 만, 1159010200004110000 → 1995 만
```
- 다음 거래 배치 로그: `고유번호 키 매핑`·`가격 점수 재계산` 성공. 가격 점수는 다음 배치의 `recalc_price` 가 자동 갱신한다.
- 상세 페이지 표본: 대방대림·상도1동대림·마전동아 실거래 이력이 각 단지 것만 보이는지.
- `failed` 구는 체크포인트 detail 의 `errors` 로 원인을 보고 개별 분석(로컬 리허설 문서 `reports/rekey/failed18_analysis.md` 의 유형 참고).

## 6. 알려진 예외

| 항목 | 처리 |
|---|---|
| 50130 (제주 서귀포) | 끊긴 이름 키(리첸시아, 없는 PNU)와 이름 변형 키(루첸시아 → TRADE_)가 같은 고유번호로 상속 합류 → 불변식 실패가 정상. 수동 매핑 후 `--sgg 50130` 재실행 |
| `blocked_delete` 키 | 재판정이 근거 없다고 본 매핑이지만 이미 rekey 된 구라 보류 — 사람이 확인 후 필요 시 `--allow-delete-rekeyed` |
| 재매칭 검토 목록 | rekey 체크포인트 detail 의 rematch review(귀속은 그대로지만 기존 오매핑 의심) — 별도 이슈로 `scripts/rematch_bad_mappings.py` |
| 매핑 못 해 되돌린 키 | 체크포인트 detail 의 되돌림 `{새 키: [이름 키…]}` — 3단계(API 잔여 수집)·단지 등록 후 재처리 근거 |

## 7. 테이블 크기 회수 (VACUUM FULL)

rekey 는 행을 다시 쓰므로 테이블이 약 1.7~1.8배 커진다(로컬 실측). 운영 Postgres 메모리는 1GB 캡이고 디스크 사용량도 늘어난다.

- `VACUUM (FULL, ANALYZE)` 는 테이블을 새로 쓰며 **작업 중 해당 테이블의 읽기·쓰기를 모두 막는다**(ACCESS EXCLUSIVE). 상세·대시보드 조회가 그동안 멈춘다.
- 필요 디스크: 대상 테이블의 회수 후 크기만큼 여유 공간(trade 약 1GB, rent 약 2GB).
- 실행: 트래픽이 가장 적은 시간(예: 새벽), 거래 배치와 겹치지 않게, trade_history → rent_history 순서로 한 테이블씩.

```bash
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('.env')
import logging, os; from batch.db import vacuum_tables
vacuum_tables(os.environ['RAILWAY_DATABASE_URL'], ['trade_history'], logging.getLogger('vacuum'), full=True)"
```
(`batch.purge_old_trades --vacuum-full` 과 같은 함수. rent_history 는 별도 실행.)

## 8. 롤백

| 범위 | 방법 |
|---|---|
| 특정 구 | `.venv/bin/python -m batch.rekey_trades --target railway --rollback --sgg {코드}` — `apt_seq = legacy_apt_seq` 로 되돌리고 남는 고유번호 키 매핑 삭제, 체크포인트 rolled_back(이후 전체 실행에서 건너뜀, 재적용은 `--sgg` 명시) |
| 재판정(매핑) | 2장 백업에서 `trade_apt_mapping`·`common_code` 복원 (`pg_restore --clean -t …`) — 운영 DB 쓰기라 별도 허락 |

## 9. 완료 후

1. 로컬 전체 동기화(`batch.sync_from_railway --mode full`)로 로컬을 운영과 일치시킨다.
2. 3단계: 혼입 키 잔여분 API 수집 모드·워크플로(계획 Task 10).
3. ADR-015 Accepted, 설계서 상태 갱신(계획 Task 11).
