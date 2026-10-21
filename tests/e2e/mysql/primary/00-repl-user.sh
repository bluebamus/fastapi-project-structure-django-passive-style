#!/bin/bash
# primary 초기화 — 복제 계정을 만든다(이 트랜잭션은 binlog 에 남기지 않는다: replica 에 필요 없다).
# 공식 이미지의 초기화 단계(소켓 전용 임시 서버)에서 한 번 돈다. 비밀번호는 compose 가 넘긴 환경 변수다.
set -euo pipefail
mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
SET SQL_LOG_BIN=0;
CREATE USER 'repl'@'%' IDENTIFIED BY '${E2E_REPL_PASSWORD}';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
SET SQL_LOG_BIN=1;
SQL
