import importlib.util


def test_replay_module_exists():
    assert importlib.util.find_spec("darknetra.agent.replay") is not None


def test_replay_question_normalization():
    from darknetra.agent.replay import normalize_question

    assert normalize_question(" What WALLETS?  ") == "what wallets"
