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
    # 1. tts(speak) 주소를 promptId 변수가 없는 경로로 따로 등록
    path('api/prompt/speak/', prompt_views.tts_view, name='tts_view'),
    

    # /api/ai-person/... → apps.prompt (AI 인물)
    # api/ 지우고 apps.prompt 로 이동 필요
     path('api/', include('apps.prompt.urls')),
    
    # /api/ai/chat → apps.knowledge (일반 AI 채팅)
    path('chat', include('apps.knowledge.urls')),
    
    # /api/debate/topics/recommend → apps.debate (토픽 추천 전용)
    path('api/debate/topics/recommend', include('apps.debate.urls')),
    
    # /api/ai-person/{promptId}/chat → apps.prompt (캐릭터 채팅)
    re_path(r'^api/ai-person/(?P<promptId>[^/]+)/chat$', include('apps.prompt.urls')),
    
    
    # 스웨거 파일 생성 (YAML/JSON)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # 스웨거 UI 화면
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # 아까 만든 chat 앱의 URL도 포함되어 있는지 확인하세요
    path('api/chat/', include('apps.chat.urls')),
    # /debate/topics/recommend → apps.debate (토픽 추천 전용)
    path('debate/topics/recommend', include('apps.debate.urls')),
]