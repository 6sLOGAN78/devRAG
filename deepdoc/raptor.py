"""Seeded native UMAP/GMM grouping for RAPTOR corpora above eight leaves."""
from __future__ import annotations

import math

from deepdoc.model_runtime import NativeError


def cluster_vectors(vectors: list[list[float]], seed: int) -> list[list[int]]:
    """Fit UMAP then GMM, pack each ordered component into bounded groups."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1 or not isinstance(vectors, list) or not 9 <= len(vectors) <= 256:
        raise NativeError("invalid_request", 400)
    dimension = len(vectors[0]) if isinstance(vectors[0], list) else 0
    if not 2 <= dimension <= 4096 or any(not isinstance(row, list) or len(row) != dimension or any(type(value) not in (int, float) or not math.isfinite(value) for value in row) for row in vectors):
        raise NativeError("invalid_request", 400)
    try:
        import numpy as np
        import umap
        from sklearn.mixture import GaussianMixture

        matrix = np.asarray(vectors, dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1)
        if not np.all(np.isfinite(norms)) or np.any(norms <= 0):
            raise ValueError("zero vector")
        matrix /= norms[:, None]
        projection = umap.UMAP(n_components=2, n_neighbors=min(10, len(matrix) - 1), min_dist=0.0,
                               random_state=seed, transform_seed=seed, n_jobs=1).fit_transform(matrix)
        count = max(2, min(8, math.ceil(len(matrix) / 6)))
        model = GaussianMixture(n_components=count, covariance_type="full", random_state=seed, n_init=1, reg_covar=1e-5)
        labels = model.fit_predict(projection)
        ordered = []
        for label in sorted(set(int(value) for value in labels)):
            members = [int(i) for i in np.where(labels == label)[0]]
            members.sort(key=lambda i: (float(np.linalg.norm(projection[i] - model.means_[label])), i))
            ordered.extend(members)
        groups = [ordered[i:i + 8] for i in range(0, len(ordered), 8)]
        if len(groups[-1]) == 1:
            groups[-1].insert(0, groups[-2].pop())
        if any(not 2 <= len(group) <= 8 for group in groups):
            raise ValueError("invalid group size")
        return [sorted(group) for group in groups]
    except NativeError:
        raise
    except Exception:
        raise NativeError("native_failure", 502) from None
