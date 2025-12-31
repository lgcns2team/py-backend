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
    
    # TTS 엔드포인트
    path('api/prompt/speak/', prompt_views.tts_view, name='tts_view'),
    
    # /api/debate/... → apps.debate (토론 관련 API)
    path('api/debate/', include('apps.debate.urls')),

    # /api/agent-chat → apps.router (에이전트 채팅)
    path('api/agent-chat', include('apps.router.urls')),
    
    # /api/debate/topics/recommend → apps.debate (토픽 추천 전용)
    path('api/debate/topics/recommend', include('apps.debate.urls')),
    
    # /api/ai-person/{promptId}/chat → apps.prompt (캐릭터 채팅)
    re_path(r'^api/ai-person/(?P<promptId>[^/]+)/chat$', include('apps.prompt.urls')),
    
    # 스웨거 파일 생성 (YAML/JSON)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # 스웨거 UI 화면
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui')
     
]