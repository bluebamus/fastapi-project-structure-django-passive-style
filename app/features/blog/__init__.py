"""Blog 기능 패키지.

**가벼운 package marker 다.** Router 도 Model 도 여기서 import 하지 않는다 —
registry 의 3단계 초기화(config → models → ready)를 지키려면 root package import
단계에서 하위 모듈이 딸려오면 안 된다. 결선은 ``apps.py`` 의 ``BlogConfig`` 가
선언하고 ``app/core/apps/wiring.py`` 가 수행한다.

* Router: ``app/features/blog/api/routers/router.py`` 의 ``blog_router``
* Models: ``app/features/blog/models/``
* Admin:  ``app/features/blog/admin.py`` 의 ``admin_views``
"""
