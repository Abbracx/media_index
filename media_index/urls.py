"""
URL configuration for media_index project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import structlog
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from typing import cast
from django.urls import URLResolver
from typing import Iterable

from media_index.api import api

log: structlog.BoundLogger = structlog.get_logger(__name__)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("django-rq/", include("django_rq.urls")),
]

if settings.DEBUG:
    urlpatterns += cast(
        Iterable[URLResolver],
        static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    )
    urlpatterns += cast(
        Iterable[URLResolver],
        static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
    )
