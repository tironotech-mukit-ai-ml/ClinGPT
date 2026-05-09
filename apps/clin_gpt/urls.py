"""
CLIN_GPT URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    path('clin-gpt/analyze/', views.analyze_patient, name='analyze_patient'),
    path('clin-gpt/emr-analysis/', views.analyze_emr, name='analyze_emr'),
]
