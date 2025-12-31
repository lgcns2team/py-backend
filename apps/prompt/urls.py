from django.urls import path
from . import views

urlpatterns = [
    path('<str:promptId>', views.prompt_view, name='prompt_chat'),
    path('ai-person/<str:promptId>/chat', views.prompt_view, name='prompt_chat'),
]