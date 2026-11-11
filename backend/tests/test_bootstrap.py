"""Start-up bootstrap: roles and feature flags exist without the demo seed, and existing choices are never disturbed."""

from sqlalchemy import select

from app.db import bootstrap
from app.models.feature import Feature
from app.services.feature_service import _DEFAULTS


def test_a_missing_flag_is_created_without_running_the_seed(db):
    db.query(Feature).filter(Feature.key == "tips").delete()
    db.commit()
    assert db.scalar(select(Feature).where(Feature.key == "tips")) is None
    bootstrap.run(db)
    assert db.scalar(select(Feature).where(Feature.key == "tips")) is not None


def test_every_built_in_flag_exists_after_bootstrap(db):
    bootstrap.run(db)
    keys = {f.key for f in db.scalars(select(Feature))}
    assert set(_DEFAULTS) <= keys


def test_running_it_again_changes_nothing(db):
    bootstrap.run(db)
    before = {f.key: (f.description, f.default_enabled) for f in db.scalars(select(Feature))}
    bootstrap.run(db)
    after = {f.key: (f.description, f.default_enabled) for f in db.scalars(select(Feature))}
    assert before == after
