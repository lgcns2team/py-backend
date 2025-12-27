from django.urls import path
from . import views

urlpatterns = [
    path('ai-person/<str:promptId>/chat', views.prompt_view, name='prompt_chat'),
]