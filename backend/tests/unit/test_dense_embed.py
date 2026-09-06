from types import SimpleNamespace

import pytest

from darknetra.errors import Unavailable
from darknetra.rag.embed import get_embedder, validate_vectors


def test_vectors_reject_wrong_shape_nonfinite_and_zero():
    for values in ([[1.0]], [[float("nan")] * 1024], [[0.0] * 1024]):
        with pytest.raises(Unavailable):
            validate_vectors(values, 1)
    with pytest.raises(Unavailable):
        validate_vectors([], 1)
    result = validate_vectors([[2.0] + [0.0] * 1023], 1)
    assert result[0][0] == 1.0


def test_absent_local_model_never_downloads(tmp_path):
    settings = SimpleNamespace(
        embedding_backend="sentence_transformers",
        embedding_model_path=tmp_path / "absent",
        embedding_model="SYNTHETIC",
        embedding_batch_size=2,
    )
    assert not get_embedder(settings).available
