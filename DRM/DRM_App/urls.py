from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# DRF Router Configuration
router = DefaultRouter()
router.register(r'contents', views.ContentViewSet, basename='api-content')
router.register(r'licenses', views.LicenseViewSet, basename='api-license')
router.register(r'access-logs', views.AccessLogViewSet, basename='api-access-log')

urlpatterns = [
    # Auth URLs
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard & Content URLs
    path('', views.dashboard_view, name='dashboard'),
    path('contents/', views.content_list_view, name='content_list'),
    path('contents/<int:content_id>/', views.content_detail_view, name='content_detail'),
    path('contents/<int:content_id>/download/', views.download_content_file_view, name='content_download'),

    # Content Management
    path('manage/contents/', views.content_manage_view, name='content_manage'),
    path('manage/contents/create/', views.content_create_view, name='content_create'),
    path('manage/contents/<int:content_id>/edit/', views.content_edit_view, name='content_edit'),
    path('manage/contents/<int:content_id>/delete/', views.content_delete_view, name='content_delete'),

    # License Management
    path('manage/licenses/', views.license_manage_view, name='license_manage'),
    path('manage/licenses/create/', views.license_create_view, name='license_create'),
    path('manage/licenses/<int:license_id>/edit/', views.license_edit_view, name='license_edit'),
    path('manage/licenses/<int:license_id>/revoke/', views.license_revoke_view, name='license_revoke'),
    path('my-licenses/', views.my_licenses_view, name='my_licenses'),

    # Access Logs & User Management
    path('access-logs/', views.access_logs_view, name='access_logs'),
    path('users/', views.user_manage_view, name='user_manage'),
    path('users/<int:user_id>/role/', views.user_update_role_view, name='user_update_role'),

    # REST API Routes
    path('api/auth/register/', views.api_register, name='api_register'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/access-check/<int:content_id>/', views.api_access_check, name='api_access_check'),
    path('api/', include(router.urls)),
]
