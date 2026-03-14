"""WSGI entry point."""
import os
import sys

# 3pl 디렉토리를 기준으로 실행되도록 보장
app_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(app_dir)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)
