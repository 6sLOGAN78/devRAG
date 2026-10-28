FROM devrag-app-runtime-p6-08:local
COPY *.whl /tmp/phase6-wheels/
RUN /usr/local/bin/python -m pip install --no-index --no-deps --no-compile --target /ragflow/.venv/lib/python3.13/site-packages /tmp/phase6-wheels/*.whl && rm -rf /tmp/phase6-wheels
COPY pyproject.toml uv.lock /ragflow/
