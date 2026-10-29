# Plan17 code rebuild using the verified exact plan16 ASR vendor; no new acquisition.
# Vendor image sha256:125a1211bed8b4ac8ecba49d284aea7a0a4c1183f71385508a3260c7c58d6c7b
ARG DEVRAG_BASE_IMAGE=devrag-app:local
FROM devrag-deepdoc-runtime-p6-16:local AS native-dependencies

FROM ${DEVRAG_BASE_IMAGE} AS native-runtime
ENV PYTHONPATH=/opt/deepdoc/vendor:/ragflow \
    DEEPDOC_MODEL_DIR=/models \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2
WORKDIR /ragflow
COPY --link --from=native-dependencies /opt/deepdoc/vendor /opt/deepdoc/vendor
COPY deepdoc ./deepdoc
COPY rag/parsers ./rag/parsers
LABEL org.opencontainers.image.source="https://github.com/6sLOGAN78/devrag-mvp"
USER 10001:10001
EXPOSE 9390
ENTRYPOINT ["tini", "--", "/ragflow/.venv/bin/python", "-m", "deepdoc.server"]
