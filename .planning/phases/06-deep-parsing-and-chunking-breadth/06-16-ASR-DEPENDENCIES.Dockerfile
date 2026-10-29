# Plan16 adds only the approved hash-locked ASR closure to the verified native cache.
# Cache image id: sha256:329b88176cef2dca6651ab25891e7ff10c00f5624fc0712387ca8cd2ca832d9d
# Both source images must exist locally; --pull=false. No package/model acquisition.
ARG DEVRAG_BASE_IMAGE=devrag-app:local
FROM devrag-deepdoc:local AS native-dependencies
USER 0:0
COPY deepdoc/asr-requirements.lock /tmp/asr-requirements.lock
RUN --mount=type=bind,from=asr_wheels,source=.,target=/wheels,ro \
    /usr/local/bin/python -m pip install --no-index --find-links=/wheels --require-hashes --only-binary=:all: --no-deps --upgrade --no-compile --target=/opt/deepdoc/vendor -r /tmp/asr-requirements.lock

FROM ${DEVRAG_BASE_IMAGE} AS native-runtime
ENV PYTHONPATH=/opt/deepdoc/vendor:/ragflow \
    DEEPDOC_MODEL_DIR=/models \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2
WORKDIR /ragflow
COPY --from=native-dependencies /opt/deepdoc/vendor /opt/deepdoc/vendor
COPY deepdoc ./deepdoc
COPY rag/parsers ./rag/parsers
LABEL org.opencontainers.image.source="https://github.com/6sLOGAN78/devrag-mvp"
USER 10001:10001
EXPOSE 9390
ENTRYPOINT ["tini", "--", "/ragflow/.venv/bin/python", "-m", "deepdoc.server"]
