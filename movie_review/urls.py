from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.views.generic import RedirectView
from django.templatetags.static import static

urlpatterns = [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    path('favicon.ico', RedirectView.as_view(url=static('favicon.svg'), permanent=True)),
    path('django-admin/', admin.site.urls),
    path('', include('critix.urls')),
    path('admin/', include('critix.admin_urls')),
]