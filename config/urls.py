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

    # /api/ai-person/... → apps.prompt (AI 인물)
    # api/ 지우고 apps.prompt 로 이동 필요
     path('api/', include('apps.prompt.urls')),
    
    # /api/ai/chat → apps.knowledge (일반 AI 채팅)
    path('chat', include('apps.knowledge.urls')),
    
    # /api/debate/... → apps.debate (토론 관련 API)
    path('api/debate/', include('apps.debate.urls')),

    # /api/agent-chat → apps.chat (에이전트 채팅)
    path('api/agent-chat', include('apps.router.urls')),
    
    # debate 관련 전체 라우팅
    path('debate/', include('apps.debate.urls')),
]