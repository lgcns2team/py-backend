from django.urls import path
from . import views

urlpatterns = [
    path('', views.recommend_debate_topics, name='recommend_debate_topics'),
]