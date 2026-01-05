from django.urls import path
from . import views

urlpatterns = [
    path('ai-person/<str:promptId>/chat', views.prompt_view, name='prompt_chat'),
    # 🆕 TTS 경로 추가
    path('prompt/speak/', views.tts_view, name='tts_speak'),
]