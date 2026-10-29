# Plan16 code rebuild; verified exact ASR vendor image sha256:125a1211bed8b4ac8ecba49d284aea7a0a4c1183f71385508a3260c7c58d6c7b
# One-off plan07 rebuild using the exact plan06 verified native vendor cache.
# Cache image id: sha256:329b88176cef2dca6651ab25891e7ff10c00f5624fc0712387ca8cd2ca832d9d
# Both source images must exist locally; --pull=false. No package/model acquisition.
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
COPY --from=native-dependencies /opt/deepdoc/vendor /opt/deepdoc/vendor
COPY deepdoc ./deepdoc
COPY rag/parsers ./rag/parsers
LABEL org.opencontainers.image.source="https://github.com/6sLOGAN78/devrag-mvp"
USER 10001:10001
EXPOSE 9390
ENTRYPOINT ["tini", "--", "/ragflow/.venv/bin/python", "-m", "deepdoc.server"]
