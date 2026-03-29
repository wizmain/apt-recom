# ADR-002: SQLite에서 PostgreSQL로 마이그레이션

- **상태**: Accepted
- **날짜**: 2026-03-21

## 맥락

초기 설계는 SQLite(`apt_web.db`)를 사용했다. 로컬 개발에는 편리했으나, Railway 배포와 동시 접속 지원을 위해 RDBMS 전환이 필요했다.

## 결정

PostgreSQL로 마이그레이션한다. 드라이버는 psycopg2를 사용하고, `DATABASE_URL` 환경변수로 연결 문자열을 관리한다.

## 근거

- **동시성**: SQLite는 단일 writer 제한이 있어 멀티 유저 환경에 부적합하다.
- **배포 호환**: Railway에서 PostgreSQL을 관리형 서비스로 제공하여 운영 부담이 적다.
- **확장성**: 4,900만 행의 매핑 테이블, 787만 건의 거래 데이터를 안정적으로 처리할 수 있다.
- **공간 쿼리**: 향후 PostGIS 확장 가능성도 열려 있다.

## 트레이드오프

- 로컬 개발 시 PostgreSQL 설치가 필요하다.
- SQLite의 파일 기반 간편함을 잃는다.
- SQL 문법 차이 (`?` → `%s`, `AUTOINCREMENT` → `SERIAL` 등) 변환이 필요했다.

## 결과

- `database.py`에서 `DATABASE_URL` 환경변수로 연결한다.
- 로컬/배포 환경 모두 동일한 PostgreSQL 사용.
- 파라미터 바인딩은 psycopg2 형식 `%s`를 사용한다 (`?` 사용 금지).
