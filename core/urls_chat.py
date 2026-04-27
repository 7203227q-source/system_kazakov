from django.urls import path
from . import views_chat

urlpatterns = [
    path('', views_chat.chat_index, name='chat_index'),
    path('<int:user_id>/', views_chat.chat_dialog, name='chat_dialog'),
    
    # AJAX API
    path('api/messages/<int:user_id>/', views_chat.api_get_messages, name='api_get_messages'),
    path('api/send/<int:user_id>/', views_chat.api_send_message, name='api_send_message'),
    path('api/unread_count/', views_chat.api_unread_count, name='api_unread_count'),
]