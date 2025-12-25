from django.urls import path, include, re_path
from django.http import JsonResponse
from datetime import datetime

def root_view(request):
    return JsonResponse({
        "service": "Bedrock Gateway API",
        "version": "3.0.0",
        "status": "operational"
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
    
    # /agent-chat → apps.router (Tool Calling + KB 라우터)
    path('agent-chat', include('apps.router.urls')),
    
    # /debate/topics/recommend → apps.debate (토픽 추천 전용)
    path('debate/topics/recommend', include('apps.debate.urls')),
    
    # /ai-person/{promptId}/chat → apps.prompt (캐릭터 채팅)
    re_path(r'^ai-person/(?P<promptId>[^/]+)/chat$', include('apps.prompt.urls')),
]