"""설정 검증을 통과하는 환경 변수 값 — ``test_deployment_safety``·``admin/test_disabled`` 가 함께 쓴다."""

# 테스트용 강한 값 — 서로 다르고 placeholder 규칙에 걸리지 않는다.
# 비밀번호까지 명시하는 이유: 로컬 `.env` 에 예시값이 남아 있어도 결과가 흔들리지 않게 한다.
STRONG = {
    "ACCESS_TOKEN_SECRET_KEY": "k7Qe2mZ9vX1pL4rT8wY3nB6cH0sD5fGa-access",
    "REFRESH_TOKEN_SECRET_KEY": "Jm3Nq8Rt1Vw6Xy9Za2Bc5De0Fg4Hi7Kl-refresh",
    "SESSION_SECRET_KEY": "Pq9Rs2Tu5Vw8Xy1Za4Bc7De0Fg3Hi6Jk-session",
    "MYSQL_PASSWORD": "Wz4Xa7Bc0De3Fg6Hi9Jk2Lm5No8Pq1Rs-mysql",
    "REDIS_PASSWORD": "Tu6Vw9Xy2Za5Bc8De1Fg4Hi7Jk0Lm3No-redis",
}

# `.env` 가 없는 환경(CI)에서 출처 검증을 통과시키는 나머지 필수 값. 비밀 키·MYSQL_PASSWORD 는
# 각 테스트가 주는 값(대개 STRONG)이 덮어쓴다 — 기본으로 넣어 두지 않으면 `.env` 가 없을 때
# 출처 검증이 먼저 걸려, 내용 검증을 보려는 테스트가 엉뚱한 이유로 실패한다.
SOURCE = {
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_USER": "app",
    "MYSQL_DATABASE": "app",
    "MYSQL_PASSWORD": "Wz4Xa7Bc0De3Fg6Hi9Jk2Lm5No8Pq1Rs-mysql",
}
