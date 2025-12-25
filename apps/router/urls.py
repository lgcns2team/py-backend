from django.urls import path
from . import views

urlpatterns = [
    path('', views.agent_chat_view, name='agent_chat'),
]
