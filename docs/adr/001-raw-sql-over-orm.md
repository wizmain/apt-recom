# ADR-001: ORM 대신 Raw SQL (psycopg2) 사용

- **상태**: Accepted
- **날짜**: 2026-03-21

## 맥락

백엔드 데이터 접근 계층을 설계할 때 SQLAlchemy 같은 ORM을 쓸지, raw SQL을 직접 작성할지 결정이 필요했다. 프로젝트의 주요 쿼리는 공간 데이터 집계(4,900만 행 매핑 테이블), 복합 JOIN, 통계 쿼리가 대부분이다.

## 결정

psycopg2로 raw SQL을 직접 작성한다. ORM(SQLAlchemy), 마이그레이션 도구(Alembic)를 사용하지 않는다.

## 근거

- **쿼리 투명성**: 4,900만 행의 `apt_facility_mapping` 테이블 등 대용량 집계 쿼리에서 ORM이 생성하는 SQL을 예측하기 어렵다. Raw SQL로 직접 제어하면 성능 최적화가 용이하다.
- **복잡한 쿼리**: 넛지 스코어링, 거래 통계, 학군 조인 등 복합 쿼리가 많아 ORM으로 표현하면 오히려 복잡해진다.
- **의존성 최소화**: 추가 라이브러리 없이 psycopg2만으로 충분하다.
- **DictConnection 래퍼**: `autocommit=True` + `RealDictCursor`로 간편한 읽기 패턴을 제공한다.

## 트레이드오프

- 스키마 변경 시 수동 ALTER TABLE SQL을 작성해야 한다 (Alembic 자동 마이그레이션 불가).
- SQL injection 방지를 위해 반드시 `%s` 파라미터 바인딩을 사용해야 한다.
- 테이블 생성/변경은 `database.py`의 `create_tables()` 함수에서 관리한다.

## 결과

- 모든 DB 접근은 `DictConnection()` 또는 `get_connection()` 패턴을 따른다.
- 쿼리 결과는 `dict` 형태 (`row['column_name']`)로 접근한다.
- 새 테이블 추가 시 `create_tables()`에 CREATE TABLE 문을 추가하고, 기존 DB에는 ALTER TABLE을 별도 실행한다.
