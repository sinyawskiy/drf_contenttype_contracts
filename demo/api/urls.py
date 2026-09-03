from django.urls import path

from api.views import DemoContentTypeContractsView


urlpatterns = [
    path(
        'content-types/list/',
        DemoContentTypeContractsView.as_view({'post': 'list'}),
        name='content-type-list',
    ),
    path(
        'content-types/retrieve/',
        DemoContentTypeContractsView.as_view({'post': 'retrieve'}),
        name='content-type-retrieve',
    ),
]
