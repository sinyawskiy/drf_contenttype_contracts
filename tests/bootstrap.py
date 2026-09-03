def setup_django():
    from django.apps import apps
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            SECRET_KEY='tests-only-secret-key',
            USE_TZ=True,
            DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
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
        )

    if not apps.ready:
        import django

        django.setup()
