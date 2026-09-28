

from django.urls import path
from . import admin_views

urlpatterns = [
    # Dashboard
    path('dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),

    # Genres (curated — genres live as a field on Movie, not a separate model)
    path('genres/',         admin_views.admin_genres,       name='admin_genres'),
    path('genres/rename/',  admin_views.admin_genre_rename, name='admin_genre_rename'),
    path('genres/delete/',  admin_views.admin_genre_delete, name='admin_genre_delete'),

    # Generic model CRUD — order matters: specific paths before the catch-all
    path('models/<str:model_name>/add/',              admin_views.admin_model_add,           name='admin_model_add'),
    path('models/<str:model_name>/action/',           admin_views.admin_model_action,        name='admin_model_action'),
    path('models/<str:model_name>/bulk-delete/',      admin_views.admin_bulk_delete_confirm, name='admin_bulk_delete_confirm'),
    path('models/<str:model_name>/<str:pk>/edit/',    admin_views.admin_model_edit,          name='admin_model_edit'),
    path('models/<str:model_name>/<str:pk>/delete/',  admin_views.admin_model_delete,        name='admin_model_delete'),
    path('models/<str:model_name>/',                  admin_views.admin_model_list,          name='admin_model_list'),

    # JSON metadata API
    path('api/meta/<str:model_name>/', admin_views.admin_metadata_api, name='admin_metadata_api'),
]

# Append import/export routes (added after initial file creation)
from django.urls import path as _path
from . import admin_views as _av

urlpatterns += [
    _path('models/<str:model_name>/export/',                _av.admin_model_export,          name='admin_model_export'),
    _path('models/<str:model_name>/import/',                _av.admin_model_import,          name='admin_model_import'),
    _path('models/<str:model_name>/import/preview/',        _av.admin_model_import_preview,  name='admin_model_import_preview'),
]