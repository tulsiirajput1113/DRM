from django.contrib import admin
from .models import UserProfile, DigitalContent, License, AccessLog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')


@admin.register(DigitalContent)
class DigitalContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description', 'owner__username')


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'start_date', 'expiry_date', 'status', 'created_at')
    list_filter = ('status', 'start_date', 'expiry_date')
    search_fields = ('user__username', 'content__title')


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'access_status', 'access_time', 'ip_address')
    list_filter = ('access_status', 'access_time')
    search_fields = ('user__username', 'content__title', 'reason', 'ip_address')
    readonly_fields = ('access_time',)
