from django.urls import path
from . import views

urlpatterns = [
    path('', views.knowledge_base_view, name='knowledge_chat'),
    path('knowledge/speak/', views.chatbot_tts_view, name='chatbot_tts')
]