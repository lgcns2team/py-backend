from django.urls import path
from . import views

urlpatterns = [
    path('character/<str:promptId>/chat', views.prompt_view, name='character-chat'),
    path('ai-person/<str:promptId>/chat', views.prompt_view, name='prompt_chat'),
]