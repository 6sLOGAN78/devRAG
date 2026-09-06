import asyncio
import os
from hypercorn.config import Config
from hypercorn.asyncio import serve
from api.apps import create_app
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.settings import load_config

app = create_app()

if __name__ == '__main__':
    cfg = load_config('conf/service_conf.yaml')
    config = Config()
    config.bind = [f"0.0.0.0:{cfg.ragflow.python_port}"]
    asyncio.run(serve(app, config))
