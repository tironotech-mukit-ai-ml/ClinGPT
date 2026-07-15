"""
CLIN_GPT URLs
"""
from django.urls import path
from . import views
from . import rule_engine_test_view

urlpatterns = [
    path('clin-gpt/analyze/', views.analyze_patient, name='analyze_patient'),
    path('clin-gpt/emr-analysis/', views.analyze_emr, name='analyze_emr'),

    # TEMPORARY — Postman testing for Validation -> Rule Engine.
    # Remove or replace once this is folded into the real ingestion endpoint.
    path('clin-gpt/rule-engine-check/', rule_engine_test_view.rule_engine_check, name='rule_engine_check'),
]