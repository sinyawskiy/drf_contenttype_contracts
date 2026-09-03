"""Test bootstrap.

``drf_contenttype_contracts`` ships as flat files at the repo root that
``pyproject.toml`` remaps into the ``drf_contenttype_contracts`` package only
at *build* time (see ``[tool.poetry].packages``). A plain ``poetry install``
/ editable install does not reproduce that remapping (its ``.pth`` file just
adds the repo root to ``sys.path``, where no ``drf_contenttype_contracts/``
directory exists), so ``import drf_contenttype_contracts`` fails even in a
dev checkout with dependencies installed.

To run this test suite without depending on a built/published artifact, load
the package straight from source under its installed name before anything
else imports it.
"""
import importlib.util
import pathlib
import sys

import django
from django.conf import settings


def _bootstrap_package():
    try:
        import drf_contenttype_contracts  # noqa: F401
    except ImportError:
        pass
    else:
        return

    root = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        'drf_contenttype_contracts',
        root / '__init__.py',
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules['drf_contenttype_contracts'] = module
    spec.loader.exec_module(module)


def _configure_django():
    if settings.configured:
        return
    settings.configure(
        SECRET_KEY='tests-only-secret-key',
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'drf_contenttype_contracts.tests.testapp',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    )
    django.setup()


_bootstrap_package()
_configure_django()
