"""Auth 기능 패키지 — OAuth2 password flow + JWT.

**가벼운 package marker 다.** Router 는 ``apps.py`` 의 ``AuthConfig`` 선언에 따라
registry 가 결선한다.

자체 모델이 없으며 user 기능의 ``User`` 에 대해 인증한다(자격증명은
``users.hashed_password``). 모델이 없으므로 ``admin.py`` 도 없다 — 관리 화면 대상이
아니다. registry 는 models·admin 모듈이 없는 앱을 정상으로 처리한다.
"""
