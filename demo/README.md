# drf-contenttype-contracts demo

Small Django project showing a generic ContentType API for Django's active
`AUTH_USER_MODEL`.

Install and prepare the database:

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py runserver
```

List users through the generic endpoint:

```bash
curl -u admin:password \
  -X POST http://localhost:8000/api/content-types/list/ \
  -H "Content-Type: application/json" \
  -d '{
    "app_label": "auth",
    "model": "user",
    "start_index": 0,
    "stop_index": 10,
    "filters": {},
    "excludes": {}
  }'
```

Example response:

```json
{
  "start_index": 0,
  "stop_index": 10,
  "total": 1,
  "elements": [
    {
      "id": 1,
      "username": "admin",
      "first_name": "",
      "last_name": "",
      "email": "admin@example.com",
      "is_active": true
    }
  ],
  "order": "",
  "search": "",
  "filter_fields": [
    {"name": "id", "verbose_name": "ID"},
    {"name": "username", "verbose_name": "username"},
    {"name": "email", "verbose_name": "email address"}
  ]
}
```

OpenAPI schema:

```text
http://localhost:8000/api/schema/
http://localhost:8000/api/docs/
```
