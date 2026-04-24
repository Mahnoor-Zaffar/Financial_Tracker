from __future__ import annotations

import pytest

from finance_tracker import create_app
from finance_tracker.config import ProductionConfig


def test_production_startup_rejects_documented_example_secret(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "change-this-in-production")

    with pytest.raises(RuntimeError, match="strong random value"):
        create_app("production")


def test_production_startup_accepts_high_entropy_secret(monkeypatch):
    secret = "V7x!2kQ9$Lm4#Np8@Rs6%Tw1&Yz3*Bc5!Df7^Gh9"
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", secret)

    app = create_app("production")

    assert app.config["SECRET_KEY"] == secret
