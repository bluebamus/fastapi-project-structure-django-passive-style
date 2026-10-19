"""
애플리케이션 설정 모듈

환경변수 기반의 설정을 Pydantic Settings로 관리합니다.

사용 방법:
    from config import app_settings, db_settings

    print(app_settings.DEBUG)
    print(db_settings.MYSQL_URL)

환경변수 우선순위:
    1. 시스템 환경변수
    2. .env 파일
    3. Field의 default 값
"""

import os
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

# =============================================================================
# 설치된 앱 (INSTALLED_APPS)
# =============================================================================
# 이 목록이 **설치 앱의 유일한 진실 공급원**이다(FR-01). `app/features/` 아래에
# 디렉터리를 만드는 것만으로는 앱이 설치되지 않는다 — 여기에 추가해야 Router·Model·
# Admin·ready() 가 활성화된다. 자동 디렉터리 스캔은 의도적으로 하지 않는다: 설치
# 범위와 순서가 파일 시스템 상태에 암묵적으로 끌려다니면, 실험용 디렉터리 하나가
# 배포에 섞이는 것을 아무도 못 막는다.
#
# 항목 형식은 Django 와 같다.
#   * config class 경로 — "app.features.blog.apps.BlogConfig" (권장, 명시적)
#   * package 경로     — "app.features.blog" (이 경우 registry 가 blog.apps 에서
#                        기본 config 를 고른다)
#
# **순서가 계약이다.** registry population(config → models → ready), Router 등록,
# Admin view 등록이 모두 이 순서를 따른다. 같은 method+path 를 여러 앱이 선언하면
# 기동이 ImproperlyConfigured 로 실패한다(app/core/apps/wiring.py).
#
# 환경변수로 덮어쓰지 않는다 — 설치 앱 구성은 코드 리뷰 대상이어야 한다.
INSTALLED_APPS: list[str] = [
    "app.features.home.apps.HomeConfig",
    "app.features.blog.apps.BlogConfig",
    "app.features.reply.apps.ReplyConfig",
    "app.features.sns.apps.SnsConfig",
    "app.features.user.apps.UserConfig",
    "app.features.auth.apps.AuthConfig",
    # ORM/Raw 데이터 접근을 나란히 비교하는 예제 두 개. 순서가 계약이므로 기존
    # 앱 뒤에 둔다 — 앞에 끼우면 라우터 등록 순서가 바뀐다.
    "app.features.catalog.apps.CatalogConfig",
    "app.features.reports.apps.ReportsConfig",
]


# =============================================================================
# 타임존 설정
# =============================================================================
class TimezoneSettings(BaseSettings):
    """
    타임존 설정

    애플리케이션 전역 타임존을 관리합니다.
    로그 시간, 데이터 생성 시간 등에 적용됩니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 타임존 문자열 (예: Asia/Seoul, UTC, America/New_York)
    TIME_ZONE: str = Field(
        default="Asia/Seoul",
        description="애플리케이션 전역 타임존",
    )

    @property
    def tz(self) -> ZoneInfo:
        """ZoneInfo 객체 반환"""
        return ZoneInfo(self.TIME_ZONE)

    def now(self) -> datetime:
        """현재 시간을 설정된 타임존으로 반환 — 로그 파일명처럼 **표시용** 지역 시각."""
        return datetime.now(self.tz)

    def utc_now(self) -> datetime:
        """현재 시각(aware UTC) — DB 에 저장하는 시각의 **단일 출처**.

        모델 default/onupdate 가 이것을 쓴다. DB 는 UTC 로 저장하고(service-hardening
        ADR-010), 지역 시각은 표시·집계 경계에서만 계산한다.
        """
        return datetime.now(UTC)

    def local_midnight_utc(self, day: date) -> datetime:
        """설정 타임존의 ``day`` 0시를 aware UTC 순간으로 — 지역 영업일 경계를 DB 조건으로 바꾼다.

        예: Asia/Seoul 의 2026-01-02 → 2026-01-01T15:00:00+00:00.
        """
        return datetime.combine(day, time(), tzinfo=self.tz).astimezone(UTC)

    def localize(self, dt: datetime) -> datetime:
        """naive datetime을 설정된 타임존으로 변환"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)


# =============================================================================
# API 설명 (Scalar 문서에 표시)
# =============================================================================
API_DESCRIPTION = """
## FastAPI Project Structure — Django Passive Style

Django 식 **수동 앱 설치**를 따르는 FastAPI 프로젝트 골격입니다.
설치 앱은 `config.INSTALLED_APPS` 한 곳에서 정하고, 설치된 앱의 Router·Models·Admin 결선은
App Registry(`AppConfig`)가 컨벤션대로 처리합니다. URL 은 각 기능의 라우터 파일이 정합니다.

### 주요 기능

- **CRUD 예제**: blog · reply · sns · user
- **인증**: OAuth2 password flow + JWT access/refresh (`/api/v1/auth/*`)
- **데이터 접근 두 계열**: catalog(ORM, `BaseRepository`) · reports(Raw SQL, `RawRepositoryBase`)
- **접속 로그**: 요청마다 수집해 별도 풀에서 저장, home 앱이 조회·통계 제공

### 아키텍처

```
Router → Dependency → Service → Repository → Database
  ↑ 쓰기 핸들러가 응답 전에 await service.commit() (별도 UnitOfWork 계층 없음)
```

### 기술 스택

- **FastAPI**: 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM (aiomysql) + Alembic
- **Pydantic v2**: 데이터 검증 및 설정 관리
- **Redis**: 기동 시 연결 검증 + Celery broker/backend
- **Scalar**: API 문서 UI

### 환경 설정

| 설정 | 설명 |
|------|------|
| `DEBUG=true` | 개발 모드 (DEBUG 로그, 개발용 테이블 자동 생성, `/docs` 노출) |
| `DEBUG=false` | 운영 모드 (INFO 로그, 스키마는 Alembic, `/docs` 비활성) |
"""


# =============================================================================
# 기본 설정
# =============================================================================
class AppSettings(BaseSettings):
    """
    애플리케이션 기본 설정

    프로젝트 메타데이터와 전역 동작 모드를 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 프로젝트 이름 (Scalar 문서 제목, 관리자 페이지 제목)
    PROJECT_NAME: str = Field(
        default="FastAPI Project",
        description="프로젝트 이름",
    )

    # 애플리케이션 버전 (헬스체크 응답에 포함)
    VERSION: str = Field(
        default="0.1.0",
        description="애플리케이션 버전",
    )

    # API 문서 설명 (Scalar에 표시)
    DESCRIPTION: str = Field(
        default=API_DESCRIPTION,
        description="API 문서 설명",
    )

    # 디버그 모드
    # True: DEBUG 로그, 개발용 테이블 자동 생성, /docs 활성화,
    #       `python main.py` 직접 실행 시 reload (uvicorn CLI 는 CLI 옵션을 따른다)
    # False: INFO 로그, 스키마는 Alembic, /docs 비활성화
    DEBUG: bool = Field(
        default=True,
        description="디버그 모드 활성화",
    )

    # 관리 화면(SQLAdmin) 끄기 (DEBUG 와 독립적으로 동작) — 예전 `ADMIN` 설정을 대체한다.
    # False(기본): /admin 마운트 — **활성 슈퍼유저 로그인**이 필요하다(admin-login ADR-001).
    #   계정은 `scripts/create_superuser.py` 로 만들고, 세션 쿠키(`admin_session`, path=/admin,
    #   SameSite=Strict, HttpOnly, 8시간)는 SESSION_SECRET_KEY 로 서명한다. 권한은 매 요청
    #   DB 로 다시 확인하므로 강등·비활성화가 바로 반영된다.
    # True: 관리 화면이 아예 없다 — 마운트·sqladmin import·세션 미들웨어·인증 백엔드가 모두
    #   생기지 않고, 앱의 어떤 응답(OpenAPI·/docs·오류 본문·헤더)에도 관리 화면 경로가 나오지
    #   않는다(admin-login ADR-005). 관리 화면을 쓰지 않는 배포는 true 로 둔다.
    #
    # 기본이 "켜짐" 인 것은 의도다 — 이 저장소는 개발을 우선 고려한 레퍼런스 구조라,
    # 받자마자 /admin 으로 DB 를 들여다볼 수 있어야 한다(결정: 2026-08-12).
    #
    # 예전 이름 `ADMIN` 이 환경 변수나 `.env` 에 남아 있으면 기동이 멈춘다
    # (`validate_removed_settings` — 뜻이 뒤집혔으므로 조용히 무시하지 않는다).
    ADMIN_DISABLED: bool = Field(
        default=False,
        description="관리 화면(/admin) 끄기 — true 면 마운트·링크 자체가 없다. false 면 슈퍼유저 로그인 필요",
    )

    # 실행 환경 — 로그 핸들러·타임존 선택, 운영 안전 검증(SQL echo·debug 금지), /admin 세션 쿠키의
    # Secure 속성(staging/production 에서만)에 쓰인다.
    # /health 응답에는 포함되지 않는다(status·version 만).
    ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="실행 환경",
    )

    # 개발용 `python main.py` 직접 실행 시 바인딩 호스트/포트.
    # 컨테이너·배포 환경에서 외부 접근을 허용하려면 0.0.0.0 이 기본이지만, 민감한
    # 환경에서는 SERVER_HOST=127.0.0.1 로 지정하고 리버스 프록시를 두는 것을 권장한다.
    SERVER_HOST: str = Field(
        default="0.0.0.0",  # nosec B104 - 컨테이너 실행 전제의 의도된 기본값(운영은 env 로 제한)
        description="개발 서버 바인딩 호스트",
    )

    # 개발 서버 바인딩 포트
    SERVER_PORT: int = Field(
        default=8000,
        description="개발 서버 바인딩 포트",
    )


# =============================================================================
# 데이터베이스 설정
# =============================================================================
def bare_host(host: str) -> str:
    """``URL.create()`` 에 넘길 호스트 — IPv6 의 대괄호를 벗긴다.

    DSN 은 문자열로 잇지 않고 ``sqlalchemy.engine.URL`` 로 만든다(service-hardening ADR-002).
    ``URL`` 이 렌더링할 때 IPv6 를 스스로 대괄호로 감싸므로, 여기서는 ``[::1]`` 과 ``::1``
    두 표기를 같은 맨 주소로 맞추기만 한다.
    """
    host = host.strip()
    return host[1:-1] if host.startswith("[") and host.endswith("]") else host


def split_host_port(entry: str, default_port: int) -> tuple[str, int]:
    """``"host"`` / ``"host:port"`` 항목을 (맨 호스트, 포트)로 분해한다.

    허용 형식:
        - IPv4      : ``10.0.0.11``            / ``10.0.0.11:3307``
        - 도메인    : ``replica.example.com``  / ``replica.example.com:3307``
        - IPv6      : ``[::1]``                / ``[2001:db8::10]:3307``

    IPv6 는 반드시 대괄호로 감싸야 한다. 감싸지 않으면 어디까지가 주소이고 어디부터가
    포트인지 구분할 수 없다 — 그래서 여기서 명시적으로 거부한다. 돌려주는 호스트는 대괄호를
    벗긴 맨 주소다(``URL`` 이 렌더링 시 다시 감싼다).
    """
    entry = entry.strip()

    if entry.startswith("["):
        host, closing, rest = entry.partition("]")
        if not closing:
            raise ValueError(f"replica 호스트 '{entry}' 의 대괄호가 닫히지 않았습니다.")
        host = host[1:]
        if rest and not rest.startswith(":"):
            raise ValueError(f"replica 호스트 '{entry}' 형식이 잘못되었습니다 (기대: [주소]:포트).")
        port = rest[1:]
    else:
        if entry.count(":") > 1:
            raise ValueError(
                f"IPv6 주소 '{entry}' 는 대괄호로 감싸야 합니다 (예: [2001:db8::10]:3307)."
            )
        host, _, port = entry.partition(":")

    if not host:
        raise ValueError(f"replica 호스트가 비어 있습니다: '{entry}'")
    if port and not port.isdigit():
        raise ValueError(f"replica 호스트 '{entry}' 의 포트가 숫자가 아닙니다.")

    return host, int(port) if port else default_port


class DatabaseSettings(BaseSettings):
    """
    데이터베이스 연결 설정

    MySQL 비동기 연결을 위한 aiomysql 드라이버를 사용합니다.

    읽기/쓰기 분리(DB 라우터):
        DB_ROUTER_ENABLED=false  → 단일 서버. 모든 쿼리가 primary 로 간다(기본값).
        DB_ROUTER_ENABLED=true   → 라우터 활성. replica 가 없으면 여전히 primary 로 간다.
        + DB_REPLICATION_ENABLED=true
                                 → SELECT 는 replica, 쓰기는 primary 로 분리된다.

    라우팅 구현은 ``app/core/db/router.py`` 를 참고하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === primary(쓰기) 서버 ===
    # MySQL 서버 호스트 (IP 또는 도메인)
    MYSQL_HOST: str = Field(
        default="localhost",
        description="MySQL 서버 호스트",
    )

    # MySQL 서버 포트
    MYSQL_PORT: int = Field(
        default=3306,
        description="MySQL 서버 포트",
    )

    # MySQL 접속 사용자명
    MYSQL_USER: str = Field(
        default="root",
        description="MySQL 사용자명",
    )

    # MySQL 접속 비밀번호
    MYSQL_PASSWORD: str = Field(
        default="",
        description="MySQL 비밀번호",
    )

    # 사용할 데이터베이스 이름
    MYSQL_DATABASE: str = Field(
        default="fastapi_db",
        description="데이터베이스 이름",
    )

    # === DB 라우터 (읽기/쓰기 분리) ===
    # 라우터 사용 여부. false 면 세션이 단일 엔진에 직접 바인딩된다(기존 동작).
    DB_ROUTER_ENABLED: bool = Field(
        default=False,
        description="DB 읽기/쓰기 라우터 활성화",
    )

    # 복제(replication) 사용 여부. true 면 SELECT 를 replica 로 보낸다.
    # DB_ROUTER_ENABLED=true 와 MYSQL_REPLICA_HOSTS 지정이 함께 필요하다.
    DB_REPLICATION_ENABLED: bool = Field(
        default=False,
        description="읽기 복제본(replica) 사용",
    )

    # 쓰기가 일어난 세션의 이후 SELECT 를 primary 로 고정할지 여부.
    # 복제 지연으로 방금 쓴 데이터가 replica 에서 안 보이는 것을 막는다(권장: true).
    DB_READ_STICKY_AFTER_WRITE: bool = Field(
        default=True,
        description="쓰기 이후 읽기를 primary 에 고정(read-after-write 일관성)",
    )

    # === replica(읽기) 서버 ===
    # replica 호스트 목록. "host" 또는 "host:port" 형식.
    # 예: ["replica-a", "replica-b:3307"]
    MYSQL_REPLICA_HOSTS: list[str] = Field(
        default=[],
        description="replica 호스트 목록 (host 또는 host:port)",
    )

    # 포트를 명시하지 않은 replica 에 적용할 기본 포트
    MYSQL_REPLICA_PORT: int = Field(
        default=3306,
        description="replica 기본 포트",
    )

    # replica 전용 자격증명. 미설정(None) 시 primary 값을 재사용한다.
    # 읽기 전용 계정을 분리해 두면 실수로 replica 에 쓰는 사고를 DB 권한 수준에서 막는다.
    MYSQL_REPLICA_USER: str | None = Field(
        default=None,
        description="replica 사용자명 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_PASSWORD: str | None = Field(
        default=None,
        description="replica 비밀번호 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_DATABASE: str | None = Field(
        default=None,
        description="replica 데이터베이스 이름 (미설정 시 primary 재사용)",
    )

    # === 마이그레이션 ===
    # Alembic 이 사용할 DSN 을 직접 지정한다 (로컬·CI 에서 SQLite 로 갈아끼울 때 유용).
    # 미설정 시 primary DSN 의 비동기 드라이버를 동기 드라이버로 바꿔 쓴다.
    ALEMBIC_DATABASE_URL: str | None = Field(
        default=None,
        description="Alembic 전용 DSN (미설정 시 primary DSN 에서 자동 유도)",
    )

    @property
    def ALEMBIC_URL(self) -> URL:
        """Alembic 마이그레이션이 사용할 동기 DSN.

        Alembic 은 동기로 실행되므로 aiomysql(비동기 드라이버)을 쓸 수 없다.
        primary DSN 의 드라이버만 pymysql 로 바꿔서 같은 서버를 가리킨다.
        마이그레이션은 항상 primary 에서 실행한다 — replica 는 읽기 전용이다.
        """
        if self.ALEMBIC_DATABASE_URL:
            return make_url(self.ALEMBIC_DATABASE_URL)
        return self.MYSQL_WRITER_URL.set(drivername="mysql+pymysql")

    @property
    def MYSQL_URL(self) -> URL:
        """SQLAlchemy 비동기 연결 URL (aiomysql 드라이버) — primary(쓰기) 서버

        호스트는 IP·도메인·IPv6(대괄호 유무 무관) 모두 가능하다. 문자열로 잇지 않고
        ``URL.create()`` 로 만든다 — 비밀번호의 ``@ : / # ? %`` 가 구분자로 읽히지 않는다.
        """
        return URL.create(
            "mysql+aiomysql",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=bare_host(self.MYSQL_HOST),
            port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE,
        )

    @property
    def MYSQL_WRITER_URL(self) -> URL:
        """primary(쓰기) 서버 URL — ``MYSQL_URL`` 의 의미를 드러낸 별칭"""
        return self.MYSQL_URL

    @property
    def _replica_entries(self) -> list[str]:
        """공백을 정리한 유효 replica 항목만 추린다."""
        return [entry.strip() for entry in self.MYSQL_REPLICA_HOSTS if entry.strip()]

    @property
    def MYSQL_REPLICA_URLS(self) -> list[URL]:
        """replica(읽기) 서버 URL 목록. 복제가 비활성이면 빈 목록."""
        if not self.replication_active:
            return []

        user = self.MYSQL_REPLICA_USER or self.MYSQL_USER
        password = self.MYSQL_REPLICA_PASSWORD or self.MYSQL_PASSWORD
        database = self.MYSQL_REPLICA_DATABASE or self.MYSQL_DATABASE

        urls = []
        for entry in self._replica_entries:
            host, port = split_host_port(entry, self.MYSQL_REPLICA_PORT)
            urls.append(
                URL.create(
                    "mysql+aiomysql",
                    username=user,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                )
            )
        return urls

    @property
    def replication_active(self) -> bool:
        """읽기/쓰기를 실제로 다른 서버로 보내는 상태인가."""
        return self.DB_ROUTER_ENABLED and self.DB_REPLICATION_ENABLED

    @property
    def routing_mode(self) -> Literal["single", "router-single", "router-replicated"]:
        """현재 라우팅 모드 (로그·헬스체크 표시용).

        - single:            라우터 미사용. 모든 쿼리 → primary
        - router-single:     라우터 사용, replica 없음. 모든 쿼리 → primary
        - router-replicated: 라우터 사용 + 복제. SELECT → replica / 쓰기 → primary
        """
        if not self.DB_ROUTER_ENABLED:
            return "single"
        return "router-replicated" if self.replication_active else "router-single"

    def describe_routing(self) -> dict[str, object]:
        """기동 시 로그로 남길 라우팅 구성 요약 (비밀번호는 마스킹)."""
        return {
            "mode": self.routing_mode,
            "router_enabled": self.DB_ROUTER_ENABLED,
            "replication_enabled": self.DB_REPLICATION_ENABLED,
            "sticky_after_write": self.DB_READ_STICKY_AFTER_WRITE,
            "writer": self.MYSQL_WRITER_URL.render_as_string(hide_password=True),
            "readers": [
                url.render_as_string(hide_password=True) for url in self.MYSQL_REPLICA_URLS
            ],
        }

    # =========================================================================
    # 커넥션 풀
    #
    # 하드코딩돼 있던 값을 설정으로 올린다. 풀 크기는 배포 형태(worker 프로세스 수,
    # replica 대수)에 따라 달라지는데, 코드에 박아두면 그때마다 이미지를 다시 만들어야
    # 한다. 더 중요한 건 **총 연결 수를 계산할 수 있게 된다**는 점이다 — 아래
    # ``max_total_connections`` 가 그것을 DB 의 max_connections 와 대조한다.
    # =========================================================================
    DB_POOL_SIZE: int = Field(
        default=20,
        ge=1,
        description="요청 처리 엔진의 기본 유지 연결 수",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=20,
        ge=0,
        description="요청 처리 엔진의 추가 허용 연결 수",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        ge=1,
        description="풀에서 연결을 기다리는 시간(초)",
    )
    # MySQL 기본 wait_timeout 은 28800초지만 클라우드 프록시는 보통 300초 안팎에서
    # 끊는다. 그보다 짧게 잡아야 죽은 연결을 잡고 있다가 실패하지 않는다.
    DB_POOL_RECYCLE: int = Field(
        default=280,
        ge=1,
        description="연결 재활용 주기(초). DB/프록시의 wait_timeout 보다 짧아야 한다",
    )
    DB_BACKGROUND_POOL_SIZE: int = Field(
        default=10,
        ge=1,
        description="백그라운드 태스크 엔진의 기본 유지 연결 수",
    )
    DB_BACKGROUND_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
        description="백그라운드 태스크 엔진의 추가 허용 연결 수",
    )
    DB_BACKGROUND_POOL_TIMEOUT: int = Field(
        default=60,
        ge=1,
        description="백그라운드 엔진이 연결을 기다리는 시간(초)",
    )

    # 이 앱을 몇 개 프로세스로 띄우는지. 풀은 **프로세스마다** 만들어지므로 총
    # 연결 수는 여기 곱해진다. 기본 1은 "모르면 최소로 본다"는 뜻이고, 실제
    # 배포 값을 넣어야 아래 검증이 의미를 갖는다.
    DB_WORKER_PROCESSES: int = Field(
        default=1,
        ge=1,
        description="이 앱을 실행하는 프로세스 수(uvicorn worker + celery worker)",
    )
    # DB 서버의 max_connections. 0이면 검증하지 않는다(모르는 값을 지어내지 않는다).
    DB_MAX_SERVER_CONNECTIONS: int = Field(
        default=0,
        ge=0,
        description="DB 서버의 max_connections. 0이면 총 연결 수 검증을 건너뛴다",
    )

    @property
    def max_total_connections(self) -> int:
        """이 배포가 DB 에 열 수 있는 **최대** 연결 수.

        프로세스마다 writer 풀 1개 + replica 대수만큼의 reader 풀 + background 풀
        1개가 생긴다. 이 값을 모르면 "왜 갑자기 Too many connections 가 나지"를
        장애 중에 계산하게 된다.
        """
        per_engine = self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW
        background = self.DB_BACKGROUND_POOL_SIZE + self.DB_BACKGROUND_MAX_OVERFLOW
        reader_engines = len(self._replica_entries) if self.DB_REPLICATION_ENABLED else 0
        per_process = per_engine * (1 + reader_engines) + background
        return per_process * self.DB_WORKER_PROCESSES

    @model_validator(mode="after")
    def _validate_routing(self) -> "DatabaseSettings":
        """모순된 라우팅 설정을 기동 시점에 차단한다(fail-fast).

        조용히 무시하면 '복제를 켰다고 믿는데 실제로는 primary 만 쓰는' 상태가
        운영에서 성능 문제로만 드러난다. 설정 단계에서 실패시키는 편이 안전하다.
        """
        if self.DB_REPLICATION_ENABLED and not self.DB_ROUTER_ENABLED:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 는 DB_ROUTER_ENABLED=true 를 필요로 합니다. "
                "라우터를 켜지 않으면 읽기/쓰기를 분리할 수 없습니다."
            )
        if self.DB_REPLICATION_ENABLED and not self._replica_entries:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 인데 MYSQL_REPLICA_HOSTS 가 비어 있습니다. "
                '읽기 복제본을 최소 1대 지정하세요 (예: MYSQL_REPLICA_HOSTS=["replica-a"]).'
            )

        # 호스트 표기 오류는 엔진 생성 시점의 난해한 예외가 아니라 여기서 잡는다.
        for entry in self._replica_entries:
            split_host_port(entry, self.MYSQL_REPLICA_PORT)

        # 총 연결 수가 DB 서버 상한을 넘으면 기동 시점에 막는다. 이 초과는 평소엔
        # 안 보이다가 **트래픽이 몰릴 때만** "Too many connections" 로 터진다 —
        # 가장 나쁜 시점에 드러나는 종류의 설정 오류다.
        if self.DB_MAX_SERVER_CONNECTIONS:
            total = self.max_total_connections
            if total > self.DB_MAX_SERVER_CONNECTIONS:
                raise ValueError(
                    f"풀 설정이 DB 상한을 넘습니다: 최대 {total} 연결 > "
                    f"DB_MAX_SERVER_CONNECTIONS={self.DB_MAX_SERVER_CONNECTIONS}. "
                    "DB_POOL_SIZE·DB_MAX_OVERFLOW·DB_WORKER_PROCESSES 를 줄이거나 "
                    "서버의 max_connections 를 올리세요."
                )

        return self


# =============================================================================
# CORS 설정
# =============================================================================
class CORSSettings(BaseSettings):
    """
    CORS (Cross-Origin Resource Sharing) 설정

    프론트엔드와 백엔드가 다른 도메인에서 실행될 때 필요합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 허용할 Origin 목록 (["*"]는 모든 Origin 허용)
    CORS_ALLOW_ORIGINS: list[str] = Field(
        default=["*"],
        description="허용할 Origin 목록",
    )

    # 자격 증명 허용 여부 (쿠키, Authorization 헤더)
    # 주의: allow_origins=["*"]와 allow_credentials=True는 CORS 스펙상
    #       유효하지 않은 조합이다. credentials를 사용하려면 구체적인 Origin을 지정해야 한다.
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
        description="자격 증명 허용 여부",
    )

    # 허용할 HTTP 메서드
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 메서드",
    )

    # 허용할 HTTP 헤더
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 헤더",
    )

    # 브라우저에 노출할 응답 헤더
    CORS_EXPOSE_HEADERS: list[str] = Field(
        default=[],
        description="노출할 응답 헤더",
    )

    # Preflight 요청 캐시 시간 (초)
    CORS_MAX_AGE: int = Field(
        default=600,
        description="Preflight 캐시 시간(초)",
    )

    @model_validator(mode="after")
    def _reject_wildcard_with_credentials(self) -> "CORSSettings":
        """`allow_origins=["*"]` 와 `allow_credentials=True` 조합을 거부한다.

        이 조합은 CORS 스펙상 무효일 뿐 아니라, Starlette 은 이때 요청 Origin 을 그대로
        반영해 '자격증명 포함 임의 출처 허용'이라는 취약 상태가 된다. 잘못된 운영 설정을
        기동 시점에 차단한다(fail-fast).
        """
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ALLOW_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=True 와 CORS_ALLOW_ORIGINS=['*'] 는 함께 쓸 수 없습니다. "
                "자격증명을 허용하려면 구체적인 Origin 을 지정하세요."
            )
        return self


# =============================================================================
# 로깅 설정
# =============================================================================
class LogSettings(BaseSettings):
    """
    로깅 설정

    소비처는 ``app/utils/logs/config.py`` 의 ``build_dictconfig()`` 다. 콘솔 핸들러는 항상 붙고,
    파일 핸들러는 ENV 가 staging/production 이고 ``LOG_FILE_ENABLED`` 일 때만 붙는다.
    레벨을 명시하지 않으면 DEBUG 모드에 따라 자동 결정됩니다.

    ``LOG_CONSOLE_ENABLED``·``LOG_CONSOLE_FORMAT``·``LOG_FILE_FORMAT``·``LOG_DATE_FORMAT`` 는
    선언만 있고 현재 로깅 구성에서 읽지 않는다(포맷은 ``app/utils/logs/config.py`` 의 상수).

    로그 레벨:
        - DEBUG: 디버깅용 상세 정보
        - INFO: 일반 정보 메시지
        - WARNING: 경고 (작은 문제)
        - ERROR: 오류 (큰 문제)
        - CRITICAL: 심각한 문제
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 출력 대상 설정 ===
    # 콘솔(stdout) 로그 출력 스위치 — 현재 build_dictconfig 가 읽지 않는다(콘솔 핸들러는 항상 붙는다).
    LOG_CONSOLE_ENABLED: bool = Field(
        default=True,
        description="콘솔 로그 활성화 (현재 미사용 — 콘솔 핸들러는 항상 붙는다)",
    )

    # 파일 로그 출력 활성화 (ENV 가 staging/production 일 때만 효과가 있다)
    LOG_FILE_ENABLED: bool = Field(
        default=True,
        description="파일 로그 활성화",
    )

    # === 로그 레벨 설정 ===
    # None이면 DEBUG 설정에 따라 자동 결정
    LOG_LEVEL: str | None = Field(
        default=None,
        description="전역 로그 레벨 (미설정 시 DEBUG 따라 자동 결정)",
    )

    # 콘솔 로그 레벨 (None이면 DEBUG 설정에 따라 자동 결정)
    LOG_CONSOLE_LEVEL: str | None = Field(
        default=None,
        description="콘솔 로그 레벨",
    )

    # 파일 로그 레벨
    LOG_FILE_LEVEL: str = Field(
        default="INFO",
        description="파일 로그 레벨",
    )

    # SQL 본문·바인딩 파라미터 로그 노출 스위치.
    #
    # 기본값이 false 인 이유: 이 프로젝트의 기본 DEBUG=true 는 유효 로그 레벨을 DEBUG 로
    # 만들고, 그 상태에서 SQLAlchemy·드라이버는 실행한 SQL 과 **바인딩된 값**을 그대로
    # 찍는다. 값에는 비밀번호 해시·토큰·개인정보가 들어가고 로그는 보통 외부 collector 로
    # 흘러간다. SQL 을 봐야 하는 개발자만 명시적으로 연다.
    LOG_SQL_ECHO_ENABLED: bool = Field(
        default=False,
        description="SQL 본문·바인딩 파라미터를 로그에 남길지 여부 (기본 false — 비밀 유출 방지)",
    )

    # === 파일 설정 ===
    # 로그 파일 저장 디렉토리
    LOG_DIR: str = Field(
        default="logs",
        description="로그 디렉토리 경로",
    )

    # 앱 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_APP_FILENAME: str = Field(
        default="{date}_app.log",
        description="앱 로그 파일명 패턴",
    )

    # 에러 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_ERROR_FILENAME: str = Field(
        default="{date}_error.log",
        description="에러 로그 파일명 패턴",
    )

    # 단일 로그 파일 최대 크기 (MB)
    LOG_MAX_SIZE_MB: int = Field(
        default=10,
        description="로그 파일 최대 크기(MB)",
    )

    # 보관할 백업 로그 파일 개수
    LOG_BACKUP_COUNT: int = Field(
        default=5,
        description="백업 로그 파일 개수",
    )

    # === 포맷 설정 ===
    # 아래 세 필드는 선언만 있고 현재 로깅 구성에서 읽지 않는다. 실제 포맷은
    # app/utils/logs/config.py 의 LOG_FORMAT 상수다.
    LOG_CONSOLE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="콘솔 로그 포맷 (현재 미사용)",
    )

    LOG_FILE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="파일 로그 포맷 (현재 미사용)",
    )

    LOG_DATE_FORMAT: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="날짜 포맷 (현재 미사용)",
    )

    def get_log_dir(self) -> Path:
        """로그 디렉토리 경로 반환 (없으면 생성)"""
        log_dir = Path(self.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def get_effective_log_level(self, debug: bool) -> str:
        """
        실제 적용할 로그 레벨 반환

        LOG_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_LEVEL is not None:
            return self.LOG_LEVEL
        return "DEBUG" if debug else "INFO"

    def get_effective_console_level(self, debug: bool) -> str:
        """
        실제 적용할 콘솔 로그 레벨 반환

        LOG_CONSOLE_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_CONSOLE_LEVEL is not None:
            return self.LOG_CONSOLE_LEVEL
        return "DEBUG" if debug else "INFO"


# =============================================================================
# 미들웨어 설정
# =============================================================================
class MiddlewareSettings(BaseSettings):
    """
    미들웨어 설정

    접속 로그 수집 등 미들웨어 관련 설정을 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 접속 로그 수집 활성화
    ACCESS_LOG_ENABLED: bool = Field(
        default=True,
        description="접속 로그 수집 활성화",
    )

    # 접속 로그 수집 제외 경로
    ACCESS_LOG_EXCLUDE_PATHS: list[str] = Field(
        default=["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"],
        description="로그 수집 제외 경로",
    )

    # 접속 로그 수집 제외 확장자
    ACCESS_LOG_EXCLUDE_EXTENSIONS: list[str] = Field(
        default=[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"],
        description="로그 수집 제외 확장자",
    )

    # 접속 로그 보존 기간(일). 매일 03:30(TIME_ZONE) Celery beat 가 이보다 오래된 행을 지운다
    # (app/features/home/tasks.py). 0 = 지우지 않는다. 음수는 기동 시 검증 오류다.
    ACCESS_LOG_RETENTION_DAYS: int = Field(
        default=365,
        ge=0,
        description="접속 로그 보존 일수 (0 = 삭제하지 않음). 이보다 오래된 행을 매일 삭제한다",
    )

    # 신뢰 프록시 홉 수 — 0 이면 X-Forwarded-For·X-Real-IP 를 보지 않는다(ClientIPResolver).
    # **배포 전 확인:** 프록시(로드밸런서·nginx) 뒤에 배포하면 앞단 프록시 단 수로 설정한다.
    # 0 으로 두면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋
    # (API·/admin)이 전체 사용자를 한 사람으로 취급한다. 실제보다 크게 잡으면 클라이언트가
    # 보낸 X-Forwarded-For 를 믿게 되어 IP 를 위조할 수 있다.
    TRUSTED_PROXY_HOPS: int = Field(
        default=0,
        ge=0,
        description=(
            "앞단 신뢰 프록시 수 (0 = 프록시 헤더 무시, 직접 피어 주소 사용). 프록시 뒤 배포면 "
            "프록시 단 수로 설정 — 0 이면 접속 로그·로그인 레이트 리밋이 모든 사용자를 프록시 IP "
            "하나로 본다. 실제보다 크면 IP 위조가 가능하다"
        ),
    )

    # 접속 로그 query_string 에서 값을 *** 로 가릴 키(대소문자 무시)
    ACCESS_LOG_SENSITIVE_QUERY_KEYS: list[str] = Field(
        default=[
            "password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "code",
        ],
        description="접속 로그 query_string 에서 값을 가릴 키",
    )


# =============================================================================
# Redis 설정
# =============================================================================
class RedisSettings(BaseSettings):
    """
    Redis 연결 설정

    소비처는 두 곳이다 — 기동 시 연결 검증(``app/core/resources.py`` 의 ``ping()``)과
    Celery broker/result backend(``app/celery/app.py``). 캐시·세션 구현은 없다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis 서버 호스트
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis 서버 호스트",
    )

    # Redis 서버 포트
    REDIS_PORT: int = Field(
        default=6379,
        description="Redis 서버 포트",
    )

    # Redis 데이터베이스 번호 (0-15)
    REDIS_DB: int = Field(
        default=0,
        description="Redis 데이터베이스 번호",
    )

    # Redis 비밀번호 (None이면 인증 없이 접속)
    REDIS_PASSWORD: str | None = Field(
        default=None,
        description="Redis 비밀번호",
    )

    @property
    def REDIS_URL(self) -> str:
        """Redis 연결 URL.

        비밀번호는 퍼센트 인코딩한다 — ``@ : / # ?`` 가 든 비밀번호가 호스트·포트로 읽히지
        않게 한다(service-hardening ADR-002). redis-py·Celery 가 파싱할 때 되돌린다.
        """
        if self.REDIS_PASSWORD:
            password = quote(self.REDIS_PASSWORD, safe="")
            return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# =============================================================================
# JWT 인증 설정
# =============================================================================
class JWTSettings(BaseSettings):
    """JWT 토큰(access/refresh)·인증 레이트 리밋 설정.

    OAuth2 password flow 기반 인증에 사용됩니다. 소비처는 ``app/core/security``
    (``TokenService``·``RefreshTokenStore``·``RateLimiter``)와 auth 기능의 provider 다.
    비밀 키는 운영 환경에서 반드시 안전한 값으로 교체하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Access Token 서명 키
    ACCESS_TOKEN_SECRET_KEY: str = Field(
        default="change-this-access-token-secret-key",
        description="Access Token 서명 키",
    )
    # Refresh Token 서명 키 (access 와 다른 키 권장)
    REFRESH_TOKEN_SECRET_KEY: str = Field(
        default="change-this-refresh-token-secret-key",
        description="Refresh Token 서명 키",
    )
    # Access Token 만료 (분) — access 는 즉시 폐기 수단이 없으므로 짧게 둔다(service-hardening ADR-014)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=1,
        description="Access Token 만료 시간(분)",
    )
    # Refresh Token 만료 (일) — Redis 의 refresh 기록·family 폐기 표시 TTL 도 이 값이다
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        ge=1,
        description="Refresh Token 만료 시간(일)",
    )
    # JWT 서명 알고리즘 — 대칭키(HMAC)만 허용한다. 검증은 이 값 하나만 받는다(`alg` 혼동 차단)
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        description="JWT 서명 알고리즘",
    )
    # 발급자(iss)·대상(aud) — 다른 서비스가 같은 키로 만든 토큰을 받지 않는다
    JWT_ISSUER: str = Field(
        default="fastapi-project",
        min_length=1,
        description="JWT 발급자(iss)",
    )
    JWT_AUDIENCE: str = Field(
        default="fastapi-project-api",
        min_length=1,
        description="JWT 대상(aud)",
    )
    # 서버 간 시계 차이 허용(초) — exp·nbf·iat 판정에 더한다
    JWT_LEEWAY_SECONDS: int = Field(
        default=5,
        ge=0,
        description="JWT 시각 검증 허용 오차(초)",
    )
    # 로그인 레이트 리밋(Redis 고정 창) — ip+username 과 ip 두 기준을 함께 센다
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(
        default=5,
        ge=1,
        description="창마다 같은 ip+username 의 로그인 시도 상한",
    )
    AUTH_LOGIN_IP_MAX_ATTEMPTS: int = Field(
        default=20,
        ge=1,
        description="창마다 같은 ip 의 로그인 시도 상한",
    )
    AUTH_LOGIN_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        description="로그인 레이트 리밋 창(초)",
    )
    # 회원가입 레이트 리밋(ip 기준)
    AUTH_REGISTER_MAX_ATTEMPTS: int = Field(
        default=5,
        ge=1,
        description="창마다 같은 ip 의 회원가입 시도 상한",
    )
    AUTH_REGISTER_WINDOW_SECONDS: int = Field(
        default=3600,
        ge=1,
        description="회원가입 레이트 리밋 창(초)",
    )


# =============================================================================
# API 설정
# =============================================================================
class ApiSettings(BaseSettings):
    """REST API 관련 설정.

    Note:
        선언만 있고 소비처가 없다. 버전 prefix(``/v1``)는 각 기능의
        ``api/routers/router.py`` 가 직접 정한다 — 이 값을 바꿔도 URL 은 바뀌지 않는다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # REST API 버전 (현재 미사용 — URL prefix 는 라우터 파일이 정한다)
    API_VERSION: str = Field(
        default="v1",
        description="REST API 버전 (현재 미사용)",
    )


# =============================================================================
# 세션 설정
# =============================================================================
class SessionSettings(BaseSettings):
    """세션 쿠키 설정.

    Note:
        ``SESSION_COOKIE_NAME`` 의 소비처는 접속 로그 미들웨어다 — 그 쿠키 값을 ``session_id`` 로
        기록한다. API 인증은 JWT(Bearer) 라 API 는 세션 쿠키를 발급하지 않는다.
        ``SESSION_SECRET_KEY`` 는 ``/admin`` 로그인 세션 쿠키(``admin_session``)의 서명 키다
        (admin-login ADR-001). 관리 화면 쿠키 이름·만료(8시간)는 고정이라 ``SESSION_COOKIE_NAME``·
        ``SESSION_EXPIRE_SECONDS`` 를 따르지 않으며, ``SESSION_COOKIE_NAME`` 이 ``admin_session`` 이면
        기동이 멈춘다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 세션 쿠키 이름
    SESSION_COOKIE_NAME: str = Field(
        default="session",
        description="세션 쿠키 이름",
    )

    # 세션 서명 키 — /admin 로그인 세션 쿠키를 서명한다 (운영 환경에서 반드시 교체, 32자 이상)
    SESSION_SECRET_KEY: str = Field(
        default="change-this-session-secret-key",
        description="세션 서명 키 (/admin 로그인 세션 쿠키 서명)",
    )

    # 세션 만료 시간 (초, 기본값 24시간)
    SESSION_EXPIRE_SECONDS: int = Field(
        default=86400,
        description="세션 만료 시간(초)",
    )


# =============================================================================
# SMTP 이메일 설정
# =============================================================================
class SMTPSettings(BaseSettings):
    """이메일 발송(SMTP) 설정.

    Note:
        선언만 있고 소비처가 없다(검증은 TLS·SSL 동시 활성 거부뿐). 이메일 발송 모듈은 아직 없다. 설정만 config 에 로드해 두고, 발송 기능을
        구현할 때 `from config import smtp_settings` 로 가져다 쓴다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SMTP 서버 주소 (로컬 개발: localhost, Gmail: smtp.gmail.com)
    SMTP_SERVER: str = Field(
        default="localhost",
        description="SMTP 서버 주소",
    )

    # SMTP 서버 포트 (25: 비암호화, 587: TLS, 465: SSL)
    SMTP_PORT: int = Field(
        default=25,
        description="SMTP 서버 포트",
    )

    # SMTP 인증 사용자명 (보통 이메일 주소)
    SMTP_USERNAME: str = Field(
        default="",
        description="SMTP 사용자명",
    )

    # SMTP 인증 비밀번호 (Gmail 은 앱 비밀번호 사용)
    SMTP_PASSWORD: str = Field(
        default="",
        description="SMTP 비밀번호",
    )

    # 발신자 이메일 주소 (발송 모듈 구현 시 의도: 미설정이면 SMTP_USERNAME)
    SMTP_FROM_EMAIL: str | None = Field(
        default=None,
        description="발신자 이메일 주소",
    )

    # 발신자 이름 (발송 모듈 구현 시 의도: 미설정이면 PROJECT_NAME)
    SMTP_FROM_NAME: str | None = Field(
        default=None,
        description="발신자 이름",
    )

    # TLS 사용 여부 (포트 587)
    SMTP_TLS: bool = Field(
        default=False,
        description="TLS 사용 여부",
    )

    # SSL 사용 여부 (포트 465)
    SMTP_SSL: bool = Field(
        default=False,
        description="SSL 사용 여부",
    )

    @model_validator(mode="after")
    def _reject_tls_with_ssl(self) -> "SMTPSettings":
        """TLS 와 SSL 을 동시에 켜는 건 의미가 없다(포트별로 하나만 쓴다)."""
        if self.SMTP_TLS and self.SMTP_SSL:
            raise ValueError(
                "SMTP_TLS 와 SMTP_SSL 은 동시에 켤 수 없습니다. "
                "포트 587 이면 TLS, 465 면 SSL 하나만 사용하세요."
            )
        return self


# =============================================================================
# 이미지 업로드 설정
# =============================================================================
class UploadSettings(BaseSettings):
    """파일·이미지 업로드 설정.

    Note:
        선언만 있고 소비처가 없다. 업로드 핸들러는 아직 없다. 설정만 config 에 로드해 둔다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 업로드 파일 저장 경로 (프로젝트 루트 기준 상대 경로)
    UPLOAD_DIR: str = Field(
        default="uploads",
        description="업로드 파일 저장 경로",
    )

    # 업로드 이미지 최대 크기 (MB)
    UPLOAD_IMAGE_SIZE_LIMIT: int = Field(
        default=20,
        description="업로드 이미지 최대 크기(MB)",
    )

    # 업로드된 이미지 자동 리사이즈 활성화
    UPLOAD_IMAGE_RESIZE: bool = Field(
        default=False,
        description="이미지 자동 리사이즈 활성화",
    )

    # 리사이즈 최대 너비 (px, UPLOAD_IMAGE_RESIZE=true 시 적용)
    UPLOAD_IMAGE_RESIZE_WIDTH: int = Field(
        default=1200,
        description="리사이즈 최대 너비(px)",
    )

    # 리사이즈 최대 높이 (px, UPLOAD_IMAGE_RESIZE=true 시 적용)
    UPLOAD_IMAGE_RESIZE_HEIGHT: int = Field(
        default=2800,
        description="리사이즈 최대 높이(px)",
    )

    # 이미지 압축 품질 (0-100)
    UPLOAD_IMAGE_QUALITY: int = Field(
        default=85,
        ge=0,
        le=100,
        description="이미지 압축 품질(0-100)",
    )

    # 허용되는 이미지 확장자
    UPLOAD_ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".jpg", ".jpeg", ".png", ".gif", ".webp"],
        description="허용 이미지 확장자",
    )


# =============================================================================
# 설정 인스턴스 팩토리 (싱글톤)
# =============================================================================
@lru_cache
def get_timezone_settings() -> TimezoneSettings:
    """타임존 설정 인스턴스 반환 (캐싱)"""
    return TimezoneSettings()


@lru_cache
def get_app_settings() -> AppSettings:
    """앱 설정 인스턴스 반환 (캐싱)"""
    return AppSettings()


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """DB 설정 인스턴스 반환 (캐싱)"""
    return DatabaseSettings()


@lru_cache
def get_cors_settings() -> CORSSettings:
    """CORS 설정 인스턴스 반환 (캐싱)"""
    return CORSSettings()


@lru_cache
def get_log_settings() -> LogSettings:
    """로그 설정 인스턴스 반환 (캐싱)"""
    return LogSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Redis 설정 인스턴스 반환 (캐싱)"""
    return RedisSettings()


@lru_cache
def get_middleware_settings() -> MiddlewareSettings:
    """미들웨어 설정 인스턴스 반환 (캐싱)"""
    return MiddlewareSettings()


@lru_cache
def get_jwt_settings() -> JWTSettings:
    """JWT 설정 인스턴스 반환 (캐싱)"""
    return JWTSettings()


@lru_cache
def get_api_settings() -> ApiSettings:
    """API 설정 인스턴스 반환 (캐싱)"""
    return ApiSettings()


@lru_cache
def get_session_settings() -> SessionSettings:
    """세션 설정 인스턴스 반환 (캐싱)"""
    return SessionSettings()


@lru_cache
def get_smtp_settings() -> SMTPSettings:
    """SMTP 설정 인스턴스 반환 (캐싱)"""
    return SMTPSettings()


@lru_cache
def get_upload_settings() -> UploadSettings:
    """업로드 설정 인스턴스 반환 (캐싱)"""
    return UploadSettings()


# =============================================================================
# 편의를 위한 전역 설정 인스턴스
# =============================================================================
# 모듈 import 시 바로 사용 가능한 설정 인스턴스
# 예: from config import app_settings
timezone_settings = get_timezone_settings()
app_settings = get_app_settings()
db_settings = get_db_settings()
cors_settings = get_cors_settings()
log_settings = get_log_settings()
redis_settings = get_redis_settings()
middleware_settings = get_middleware_settings()
jwt_settings = get_jwt_settings()
api_settings = get_api_settings()
session_settings = get_session_settings()
smtp_settings = get_smtp_settings()
upload_settings = get_upload_settings()


# =============================================================================
# 교차 설정 검증 — 한 클래스 안에서는 볼 수 없는 조합을 기동 시점에 막는다
# =============================================================================
def _validate_cross_settings() -> None:
    """설정 클래스 경계를 넘는 위험한 조합을 fail-fast 로 차단한다.

    ``LOG_SQL_ECHO_ENABLED`` 는 SQL 본문과 **바인딩된 값**을 로그로 내보내는
    스위치다. 개발 중 쿼리를 눈으로 보기 위한 것이고, 운영에서 켜지면 비밀번호
    해시·토큰·개인정보가 그대로 로그 수집기로 흘러간다. 그런데 이 값은
    ``LogSettings``, 환경은 ``AppSettings`` 에 있어 어느 한쪽의 validator 로는
    잡히지 않는다 — 그래서 여기서 본다.
    """
    if app_settings.ENV in ("production", "staging") and log_settings.LOG_SQL_ECHO_ENABLED:
        raise ValueError(
            f"ENV={app_settings.ENV} 에서 LOG_SQL_ECHO_ENABLED=true 는 허용되지 않습니다. "
            "SQL 본문과 바인딩된 값(비밀번호 해시·토큰 포함)이 로그로 유출됩니다. "
            "development/test 에서만 켜세요."
        )


_validate_cross_settings()


# =============================================================================
# 설정 검증 — `.env` 출처와 placeholder 비밀키(test 외 모든 ENV), 배포 환경의 debug 모드
# =============================================================================
def is_placeholder_secret(value: str) -> bool:
    """예시·기본값 그대로인 비밀키인지 판정한다(빈 값, ``your-`` 시작, ``change-this`` 포함)."""
    v = value.strip().lower()
    return "change-this" in v or v.startswith("your-") or v == ""


#: 이름이 바뀌어 뜻이 뒤집힌 설정 — 남아 있으면 조용히 무시하지 않고 기동을 멈춘다(admin-login ADR-005).
REMOVED_SETTINGS = {
    "ADMIN": (
        "ADMIN 은 ADMIN_DISABLED 로 바뀌었다 — ADMIN=false 였다면 ADMIN_DISABLED=true 로, "
        "ADMIN=true 였다면 줄을 지우면 된다(기본은 켜짐, 슈퍼유저 로그인 필요)."
    ),
}


def validate_removed_settings(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """예전 설정 이름이 환경 변수나 `.env` 에 남아 있으면 기동을 멈춘다.

    설정 클래스는 ``extra="ignore"`` 라 모르는 키를 조용히 버린다. ``ADMIN=false`` 로 관리 화면을
    끄던 배포가 이름 변경 뒤 그대로 올라오면 **관리 화면이 켜진다** — 그래서 이 이름만은 감지한다.
    pydantic-settings 처럼 대소문자를 가리지 않는다. test 는 검사하지 않는다(pytest 가 ENV=test 를
    준다 — ``validate_env_source`` 와 같은 기준). 메시지에는 설정 **이름**만 담는다.
    """
    if env == "test":
        return
    names = {key.upper() for key in environ}
    if env_file.is_file():
        names |= {key.upper() for key in dotenv_values(env_file)}
    found = [message for name, message in REMOVED_SETTINGS.items() if name in names]
    if found:
        raise ValueError(" ".join(found))


# 서명·세션 키의 최소 길이. `secrets.token_urlsafe(48)` 은 64자다.
SECRET_KEY_MIN_LENGTH = 32

# `.env` 파일이 없을 때 환경 변수로 **직접** 들어와야 하는 값. 컨테이너처럼 파일 없이
# 주입하는 배포는 이것들이 모두 있으면 통과한다. 하나라도 없으면 코드 기본값으로 뜨게 되므로
# (예: ENV 가 없으면 development 로 간주돼 배포 검증이 꺼진다) 기동을 멈춘다.
REQUIRED_WITHOUT_ENV_FILE = (
    "ENV",
    "ACCESS_TOKEN_SECRET_KEY",
    "REFRESH_TOKEN_SECRET_KEY",
    "SESSION_SECRET_KEY",
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)


def validate_env_source(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """`.env` 가 없고 필수 값이 환경 변수로도 오지 않았으면 기동을 멈춘다.

    `env_file` 은 Settings 들의 ``env_file=".env"`` 와 같은 기준(작업 디렉터리)이다.
    test 는 검사하지 않는다(pytest 가 ENV=test 를 준다). 메시지에는 빠진 설정 **이름**만 담는다.
    """
    if env == "test" or env_file.is_file():
        return
    missing = [name for name in REQUIRED_WITHOUT_ENV_FILE if name not in environ]
    if missing:
        raise ValueError(
            ".env 파일이 없고, 필수 설정이 환경 변수로도 주어지지 않았습니다: "
            + ", ".join(missing)
            + ". 로컬에서는 `cp .env.example .env` 후 값을 채우고, 배포에서는 환경 변수로 "
            "주입하세요."
        )


def validate_deployment_safety() -> None:
    """비밀키·비밀번호(test 외 모든 ENV)와 debug 모드(staging/production)를 fail-fast 로 검증한다.

    코드 기본값과 `.env.example` 의 키는 누구나 아는 값이라, 그대로 배포하면
    JWT 를 위조할 수 있다. access 와 refresh 키가 같으면 refresh 토큰을 access
    토큰으로 바꿔 쓰는 공격면이 생긴다. 이 판정은 **개발 환경에도** 적용한다 —
    기본값·예시 값 그대로는 `.env` 를 채우라는 신호이고, 잘못된 설정은 처음부터
    오류로 드러나야 한다. 서명·세션 키는 32자 미만도 거부한다.

    debug 모드는 배포 환경에서만 막는다 — 유효 로그 레벨이 DEBUG 가 되면 세션
    롤백 경로가 SQL·바인딩 값·트레이스백 전문을 남긴다(``app/core/db/session.py``).
    개발에서 원하던 그 동작이 운영에서는 그대로 유출 경로다. ``DEBUG`` 는
    ``AppSettings``, ``LOG_LEVEL`` 은 ``LogSettings`` 에 있어 한쪽 validator 로는
    볼 수 없다.

    ``MYSQL_PASSWORD``·``REDIS_PASSWORD``·``SMTP_PASSWORD`` 도 같은 판정을 받는다.
    다만 빈 값의 의미가 갈린다 — MySQL 은 빈 비밀번호 자체가 사고지만, 인증 없는
    Redis 와 미사용 SMTP 는 정당한 배포라 값이 있을 때만 예시값인지 본다.

    위반은 한 번에 모두 모아 알리고, 메시지에는 설정 **이름만** 담는다 — 값은
    로그로 흘러가면 안 된다. test 는 검사하지 않는다(pytest 가 ENV=test 를 준다).
    """
    if app_settings.ENV == "test":
        return
    secrets = {
        "ACCESS_TOKEN_SECRET_KEY": jwt_settings.ACCESS_TOKEN_SECRET_KEY,
        "REFRESH_TOKEN_SECRET_KEY": jwt_settings.REFRESH_TOKEN_SECRET_KEY,
        "SESSION_SECRET_KEY": session_settings.SESSION_SECRET_KEY,
        # 빈 값도 위반이다 — DB 에 비밀번호 없이 붙는 것 자체가 사고다.
        "MYSQL_PASSWORD": db_settings.MYSQL_PASSWORD,
    }
    # Redis·SMTP 는 빈 값이 정당한 구성이다(인증 없는 Redis, SMTP 미사용). 여기서
    # 빈 값을 막으면 멀쩡한 배포가 기동하지 못하므로, 값이 있을 때만 예시값인지 본다.
    for name, optional in (
        ("REDIS_PASSWORD", redis_settings.REDIS_PASSWORD or ""),
        ("SMTP_PASSWORD", smtp_settings.SMTP_PASSWORD),
    ):
        if optional.strip():
            secrets[name] = optional
    problems = [
        f"{name} 가 placeholder 입니다"
        for name, value in secrets.items()
        if is_placeholder_secret(value)
    ]
    for name in SECRET_KEYS:
        value = secrets[name]
        if not is_placeholder_secret(value) and len(value.strip()) < SECRET_KEY_MIN_LENGTH:
            problems.append(f"{name} 가 {SECRET_KEY_MIN_LENGTH}자보다 짧습니다")
    if jwt_settings.ACCESS_TOKEN_SECRET_KEY == jwt_settings.REFRESH_TOKEN_SECRET_KEY:
        problems.append("ACCESS_TOKEN_SECRET_KEY 와 REFRESH_TOKEN_SECRET_KEY 가 같습니다")
    if app_settings.ENV in ("production", "staging"):
        if app_settings.DEBUG:
            problems.append("DEBUG 가 켜져 있습니다")
        if (log_settings.LOG_LEVEL or "").strip().upper() == "DEBUG":
            problems.append("LOG_LEVEL 이 DEBUG 레벨입니다")
    if problems:
        raise ValueError(
            f"ENV={app_settings.ENV} 에서 설정이 안전하지 않습니다: "
            + "; ".join(problems)
            + ". `.env`(또는 환경 변수)를 고치세요. 비밀키는 서로 다른 값으로 — "
            'uv run python -c "import secrets; print(secrets.token_urlsafe(48))", '
            "비밀번호는 실제 값으로(Redis·SMTP 를 쓰지 않으면 비웁니다)."
        )


SECRET_KEYS = ("ACCESS_TOKEN_SECRET_KEY", "REFRESH_TOKEN_SECRET_KEY", "SESSION_SECRET_KEY")

validate_env_source(app_settings.ENV)
validate_removed_settings(app_settings.ENV)
validate_deployment_safety()
