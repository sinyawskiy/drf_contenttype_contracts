SECRET_KEY = 'tests-only-secret-key'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'drf_contenttype_contracts.tests.testapp',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
