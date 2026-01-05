from django.urls import path, include, re_path
from django.http import JsonResponse
from datetime import datetime
# config/urls.py 상단에 추가
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from apps.prompt import views as prompt_views

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

    path('api/', include('apps.prompt.urls')),  # /api/character/... 매칭
    path('api/agent-chat', include('apps.router.urls')),
    path('api/debate/', include('apps.debate.urls')),

    # === Knowledge (일반 AI 채팅) ===
    path('chat', include('apps.knowledge.urls')),
    
    # === TTS ===
    path('api/prompt/speak/', prompt_views.tts_view, name='tts_view'),
    
    # === Swagger ===
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]