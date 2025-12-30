from django.urls import path
# from . import aws_views
from . import views

urlpatterns = [
    # path('', aws_views.stt_view, name='stt'),
    path("presign", views.presign_voice_upload),
    path("from-s3", views.stt_from_s3_key),
]