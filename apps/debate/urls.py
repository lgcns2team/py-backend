from django.urls import path
from . import views

urlpatterns = [
    path('topics/recommend', views.recommend_debate_topics, name='recommend_debate_topics'),
    path('<str:room_id>/summary', views.debate_summary, name='debate_summary'),
]