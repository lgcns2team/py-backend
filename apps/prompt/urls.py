from django.urls import path
from . import views

urlpatterns = [
    path('<str:promptId>', views.prompt_view, name='prompt_chat'),
]