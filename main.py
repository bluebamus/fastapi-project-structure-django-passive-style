"""FastAPI 진입점.

조립은 전부 ``app.core.bootstrap.create_app()`` 이 한다. 이 파일에 남는 것은
"어떤 앱을 실행할지" 와 로컬 실행뿐이다.

새 기능을 붙일 때 **이 파일은 손대지 않는다** — ``config.INSTALLED_APPS`` 에 앱의
config class 경로를 한 줄 추가하면 Router·Model·Admin·``ready()`` 가 함께 붙는다.
반대로 목록에서 빼면 디렉터리가 남아 있어도 전부 떨어진다.
"""

from app.core.bootstrap import create_app
from config import app_settings

app = create_app()


if __name__ == "__main__":
    import uvicorn

    from app.utils.logs import setup_uvicorn_logging

    uvicorn.run(
        "main:app",
        host=app_settings.SERVER_HOST,
        port=app_settings.SERVER_PORT,
        reload=app_settings.DEBUG,
        log_config=setup_uvicorn_logging(),
    )
