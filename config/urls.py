from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from datetime import datetime

def root_view(request):
    return JsonResponse({
        "service": "Bedrock Gateway API",
        "version": "3.0.0",
        "status": "operational",
        "endpoints": {
            "/chat": "POST - Knowledge Base 검색 (일반 AI 채팅)",
            "/debate/topics/recommend": "POST - 토픽 추천",
            "/ai-person/{promptId}/chat": "POST - 캐릭터 채팅",
            "/health": "GET - 헬스 체크"
        }
    })

def health_check(request):
    return JsonResponse({
        "status": "healthy",
        "bedrock": "configured",
        "timestamp": datetime.utcnow().isoformat()
    })

urlpatterns = [
    path('', root_view),
    path('health', health_check),
    
    # /chat → apps.knowledge (일반 AI 채팅)
    path('chat', include('apps.knowledge.urls')),
    
    # /debate/topics/recommend → apps.prompt (토픽 추천)
    path('debate/topics/recommend', include('apps.prompt.urls')),
    
    # /ai-person/{promptId}/chat → apps.prompt (캐릭터 채팅)
    re_path(r'^ai-person/(?P<promptId>[^/]+)/chat', include('apps.prompt.urls')),
]