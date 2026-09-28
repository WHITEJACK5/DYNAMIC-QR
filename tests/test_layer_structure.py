"""The directive mandates a minimum layer structure for the backend.

A previous report claimed this layout was satisfied while `models.py` and
`utils.py` were still flat modules. These tests are the guard: they fail the
build if a layer is collapsed back into a single file.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# From the directive, verbatim:
#   app/routes/       thin HTTP handlers
#   app/services/     business logic
#   app/repositories/ all DB access
#   app/models/       data models/schemas
#   app/utils/        pure helper functions
REQUIRED_LAYERS = ("routes", "services", "repositories", "models", "utils")


@pytest.mark.parametrize("layer", REQUIRED_LAYERS)
def test_layer_is_a_directory(layer):
    path = os.path.join(APP, layer)
    assert os.path.isdir(path), f"app/{layer}/ must be a directory (directive Phase 2a)"
    assert os.path.isfile(os.path.join(path, "__init__.py")), f"app/{layer}/ needs __init__.py"


@pytest.mark.parametrize("layer", REQUIRED_LAYERS)
def test_layer_is_not_a_flat_module(layer):
    assert not os.path.isfile(os.path.join(APP, f"{layer}.py")), \
        f"app/{layer}.py collapsed the {layer} layer back into one file"


def test_layers_contain_modules():
    for layer in REQUIRED_LAYERS:
        mods = [f for f in os.listdir(os.path.join(APP, layer))
                if f.endswith(".py") and f != "__init__.py"]
        assert mods, f"app/{layer}/ has no modules"


def test_utils_helpers_are_importable_from_the_package():
    from app import utils

    for name in utils.__all__:
        assert callable(getattr(utils, name)), name


def test_models_entities_are_importable_from_the_package():
    from app import models

    assert set(models.__all__) == {"Base", "User", "Folder", "QRCode", "Scan", "Template"}
    for name in models.__all__:
        assert hasattr(models, name), name


def test_every_route_module_defines_a_blueprint():
    """Routes layer: HTTP views live on Blueprints, one module per concern."""
    from flask import Blueprint

    expected = {"auth", "qr", "analytics", "meta", "pages", "redirect"}
    found = set()
    for module in ("auth", "qr", "analytics", "meta", "pages", "redirect"):
        mod = importlib.import_module(f"app.routes.{module}")
        blueprints = [v for v in vars(mod).values() if isinstance(v, Blueprint)]
        assert blueprints, f"app/routes/{module}.py defines no Blueprint"
        found.add(blueprints[0].name)
    assert expected <= found, f"missing route blueprints: {expected - found}"


def test_blueprints_are_registered_on_the_app():
    import server as nare

    registered = {b.name for b in nare.app.blueprints.values()}
    for name in ("auth", "qr", "analytics", "meta", "pages", "redirect"):
        assert name in registered, f"{name} blueprint is not registered on the app"


def test_services_and_repositories_are_separate_layers():
    svc = os.listdir(os.path.join(APP, "services"))
    repo = os.listdir(os.path.join(APP, "repositories"))
    assert any(f.endswith(".py") for f in svc)
    assert any(f.endswith(".py") for f in repo)
    # no repository module should be importable as a service, and vice versa
    assert "qr_repo.py" in repo and "qr_repo.py" not in svc
