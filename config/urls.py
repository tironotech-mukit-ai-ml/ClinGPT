"""
URL Configuration for InTEAM AI Service
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.clin_gpt.urls')),
    path('health/', include('apps.core.urls')),
]
