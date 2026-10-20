#!/bin/bash
# replica 초기화 — primary 의 현재 GTID 집합을 "이미 적용함" 으로 두고 그 뒤부터 복제한다.
#
# 두 서버는 같은 MYSQL_DATABASE·MYSQL_USER 로 각자 초기화돼 시작 상태가 같다. primary 의 초기화
# 트랜잭션(DB·계정 생성)을 replica 가 다시 적용하면 "이미 있다" 로 복제가 멈추므로, primary 의
# gtid_executed 를 replica 의 gtid_purged 로 둔다. 스키마(Alembic)는 그 뒤에 primary 에 만들어지고
# 복제로 내려온다. 복제는 서버가 정식으로 뜰 때 자동 시작한다(초기화 단계는 소켓 전용 임시 서버).
set -euo pipefail
gtid=$(mysql -h mysql-primary -uroot -p"${MYSQL_ROOT_PASSWORD}" -N -s \
  -e "SELECT @@GLOBAL.gtid_executed" | tr -d '\n')
mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
RESET BINARY LOGS AND GTIDS;
SET GLOBAL gtid_purged='${gtid}';
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='mysql-primary', SOURCE_PORT=3306,
  SOURCE_USER='repl', SOURCE_PASSWORD='${E2E_REPL_PASSWORD}',
  SOURCE_AUTO_POSITION=1, GET_SOURCE_PUBLIC_KEY=1, SOURCE_CONNECT_RETRY=2;
SQL
