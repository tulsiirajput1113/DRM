from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, DigitalContent, License, AccessLog


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['role', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=UserProfile.ROLE_CHOICES, default='NORMAL_USER')

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role', 'NORMAL_USER')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        if hasattr(user, 'profile'):
            user.profile.role = role
            user.profile.save()
        else:
            UserProfile.objects.create(user=user, role=role)
        return user


class DigitalContentSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = DigitalContent
        fields = ['id', 'title', 'description', 'content_body', 'file', 'owner', 'owner_name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['owner', 'created_at', 'updated_at']


class LicenseSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    content_title = serializers.ReadOnlyField(source='content.title')
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = License
        fields = ['id', 'user', 'username', 'content', 'content_title', 'start_date', 'expiry_date', 'status', 'is_valid', 'created_at']
        read_only_fields = ['created_at']

    def get_is_valid(self, obj):
        return obj.is_currently_valid()


class AccessLogSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    content_title = serializers.SerializerMethodField()

    class Meta:
        model = AccessLog
        fields = ['id', 'user', 'username', 'content', 'content_title', 'access_time', 'access_status', 'reason', 'ip_address']
        read_only_fields = ['id', 'access_time']

    def get_username(self, obj):
        return obj.user.username if obj.user else "Anonymous"

    def get_content_title(self, obj):
        return obj.content.title if obj.content else "Deleted Content"
