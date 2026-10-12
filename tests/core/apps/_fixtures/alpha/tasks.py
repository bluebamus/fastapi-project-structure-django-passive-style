"""alpha fixture 앱의 태스크 module — import 되면 기록한다.

태스크 발견은 이 module 을 import 하지 않아야 한다(순환 import 방지). 이벤트가 남으면
발견 단계가 import 한 것이다.
"""

from tests.core.apps._fixtures.eventlog import record

record("tasks", "alpha")
