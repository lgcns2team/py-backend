from django.urls import path
from . import views

urlpatterns = [
    path('', views.prompt_view, name='prompt_chat'),
]