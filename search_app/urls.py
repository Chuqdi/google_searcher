from django.urls import path
from . import views

app_name = 'search_app'


urlpatterns = [
    path('', views.index, name='index'),
    path('history/', views.search_history, name='history'),
    path('ajax-search/', views.ajax_search, name='ajax_search'),
    path('download/<str:filename>/', views.download_search_file, name='download_search_file'),
    path('delete/<str:filename>/', views.delete_search_file, name='delete_search_file'),
]