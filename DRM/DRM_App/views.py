from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.http import HttpResponseForbidden, FileResponse, Http404

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile, DigitalContent, License, AccessLog
from .forms import UserRegistrationForm, DigitalContentForm, LicenseForm, UserRoleUpdateForm
from .drm_services import verify_and_log_drm_access, get_client_ip
from .serializers import (
    UserSerializer, UserRegisterSerializer, DigitalContentSerializer,
    LicenseSerializer, AccessLogSerializer
)


# ==========================================
# HELPER DECORATORS
# ==========================================

def admin_required(view_func):
    """Decorator to restrict view to Admin users only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.profile.is_admin:
            messages.error(request, "Access Restricted: Administrator privileges required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def content_manager_required(view_func):
    """Decorator to restrict view to Admin & Content Managers."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.profile.is_content_manager:
            messages.error(request, "Access Restricted: Content Manager or Admin privileges required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==========================================
# AUTHENTICATION VIEWS
# ==========================================

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()

            role = form.cleaned_data.get('role', 'NORMAL_USER')
            # Update the cached profile directly to avoid the post_save signal overwriting it during login()
            user.profile.role = role
            user.profile.save()

            login(request, user)
            messages.success(request, f"Welcome to DRM System, {user.username}! Account created as {user.profile.get_role_display()}.")
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()

    return render(request, 'DRM_App/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'DRM_App/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out safely.")
    return redirect('login')


# ==========================================
# DASHBOARD & CORE HTML VIEWS
# ==========================================

@login_required
def dashboard_view(request):
    user = request.user
    profile = user.profile

    total_users = User.objects.count()
    total_content = DigitalContent.objects.count()

    # Update expired licenses in real-time
    now = timezone.now()
    License.objects.filter(status='ACTIVE', expiry_date__lt=now).update(status='EXPIRED')

    active_licenses = License.objects.filter(status='ACTIVE', expiry_date__gte=now).count()
    expired_licenses = License.objects.filter(status='EXPIRED').count()

    # User specific counts
    if profile.is_admin:
        recent_logs = AccessLog.objects.all()[:10]
        user_active_licenses = active_licenses
    elif profile.is_content_manager:
        my_contents = DigitalContent.objects.filter(owner=user)
        recent_logs = AccessLog.objects.filter(content__in=my_contents)[:10]
        user_active_licenses = License.objects.filter(content__in=my_contents, status='ACTIVE', expiry_date__gte=now).count()
    else:
        recent_logs = AccessLog.objects.filter(user=user)[:10]
        user_active_licenses = License.objects.filter(user=user, status='ACTIVE', expiry_date__gte=now).count()

    context = {
        'total_users': total_users,
        'total_content': total_content,
        'active_licenses': active_licenses,
        'expired_licenses': expired_licenses,
        'recent_logs': recent_logs,
        'user_active_licenses': user_active_licenses,
    }
    return render(request, 'DRM_App/dashboard.html', context)


@login_required
def content_list_view(request):
    contents = DigitalContent.objects.filter(status='ACTIVE')
    user = request.user

    # Attach license access status to each content object for UI display
    content_status_map = []
    now = timezone.now()

    for item in contents:
        has_access = False
        badge_text = "Access Denied"
        badge_class = "bg-danger"

        if user.profile.is_admin or item.owner == user:
            has_access = True
            badge_text = "Authorized (Owner/Admin)"
            badge_class = "bg-success"
        else:
            lic = License.objects.filter(user=user, content=item).order_by('-created_at').first()
            if lic:
                lic.check_and_update_status()
                if lic.status == 'ACTIVE' and lic.start_date <= now <= lic.expiry_date:
                    has_access = True
                    time_left = lic.expiry_date - now
                    if time_left.days < 2:
                        badge_text = f"Expiring Soon (Exp: {lic.expiry_date.strftime('%b %d')})"
                        badge_class = "bg-warning text-dark"
                    else:
                        badge_text = f"Licensed / Access Available"
                        badge_class = "bg-success"
                elif lic.status == 'EXPIRED' or now > lic.expiry_date:
                    badge_text = "Expired"
                    badge_class = "bg-danger"
                else:
                    badge_text = "License Inactive"
                    badge_class = "bg-secondary"

        content_status_map.append({
            'object': item,
            'has_access': has_access,
            'badge_text': badge_text,
            'badge_class': badge_class
        })

    return render(request, 'DRM_App/content_list.html', {'content_items': content_status_map})


@login_required
def content_detail_view(request, content_id):
    content = get_object_or_404(DigitalContent, id=content_id)
    has_access, access_status, reason, license_obj = verify_and_log_drm_access(request.user, content, request)

    if not has_access:
        return render(request, 'DRM_App/access_denied.html', {
            'content': content,
            'access_status': access_status,
            'reason': reason,
            'license_obj': license_obj
        }, status=403)

    return render(request, 'DRM_App/content_detail.html', {
        'content': content,
        'access_status': access_status,
        'reason': reason,
        'license_obj': license_obj
    })


@login_required
def download_content_file_view(request, content_id):
    content = get_object_or_404(DigitalContent, id=content_id)
    has_access, access_status, reason, _ = verify_and_log_drm_access(request.user, content, request)

    if not has_access:
        messages.error(request, f"File Download Denied: {reason}")
        return redirect('content_detail', content_id=content.id)

    if not content.file:
        raise Http404("No file attached to this content item.")

    return FileResponse(content.file.open(), as_attachment=True, filename=content.file.name.split('/')[-1])


# ==========================================
# CONTENT MANAGEMENT (Admin / Content Manager)
# ==========================================

@login_required
@content_manager_required
def content_manage_view(request):
    if request.user.profile.is_admin:
        contents = DigitalContent.objects.all().order_by('-created_at')
    else:
        contents = DigitalContent.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'DRM_App/content_manage.html', {'contents': contents})


@login_required
@content_manager_required
def content_create_view(request):
    if request.method == 'POST':
        form = DigitalContentForm(request.POST, request.FILES)
        if form.is_valid():
            content = form.save(commit=False)
            content.owner = request.user
            content.save()
            messages.success(request, f"Digital content '{content.title}' published successfully!")
            return redirect('content_manage')
    else:
        form = DigitalContentForm()

    return render(request, 'DRM_App/content_form.html', {'form': form, 'title': 'Create Digital Content'})


@login_required
@content_manager_required
def content_edit_view(request, content_id):
    content = get_object_or_404(DigitalContent, id=content_id)

    if not request.user.profile.is_admin and content.owner != request.user:
        messages.error(request, "Permission Denied: You can only edit your own content.")
        return redirect('content_manage')

    if request.method == 'POST':
        form = DigitalContentForm(request.POST, request.FILES, instance=content)
        if form.is_valid():
            form.save()
            messages.success(request, f"Digital content '{content.title}' updated successfully!")
            return redirect('content_manage')
    else:
        form = DigitalContentForm(instance=content)

    return render(request, 'DRM_App/content_form.html', {'form': form, 'title': f'Edit Content: {content.title}'})


@login_required
@content_manager_required
def content_delete_view(request, content_id):
    content = get_object_or_404(DigitalContent, id=content_id)

    if not request.user.profile.is_admin and content.owner != request.user:
        messages.error(request, "Permission Denied: You can only delete your own content.")
        return redirect('content_manage')

    if request.method == 'POST':
        title = content.title
        content.delete()
        messages.success(request, f"Content '{title}' deleted successfully.")
        return redirect('content_manage')

    return render(request, 'DRM_App/content_confirm_delete.html', {'content': content})


# ==========================================
# LICENSE MANAGEMENT
# ==========================================

@login_required
@content_manager_required
def license_manage_view(request):
    if request.user.profile.is_admin:
        licenses = License.objects.all().order_by('-created_at')
    else:
        my_contents = DigitalContent.objects.filter(owner=request.user)
        licenses = License.objects.filter(content__in=my_contents).order_by('-created_at')

    # Update statuses
    now = timezone.now()
    for lic in licenses:
        lic.check_and_update_status()

    return render(request, 'DRM_App/license_manage.html', {'licenses': licenses})


@login_required
@content_manager_required
def license_create_view(request):
    if request.method == 'POST':
        form = LicenseForm(request.POST)
        if form.is_valid():
            lic = form.save()
            messages.success(request, f"License granted to '{lic.user.username}' for content '{lic.content.title}'.")
            return redirect('license_manage')
    else:
        form = LicenseForm()

    return render(request, 'DRM_App/license_form.html', {'form': form, 'title': 'Issue New DRM License'})


@login_required
@content_manager_required
def license_edit_view(request, license_id):
    license_obj = get_object_or_404(License, id=license_id)

    if not request.user.profile.is_admin and license_obj.content.owner != request.user:
        messages.error(request, "Permission Denied: Cannot modify licenses for content owned by others.")
        return redirect('license_manage')

    if request.method == 'POST':
        form = LicenseForm(request.POST, instance=license_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "License updated successfully.")
            return redirect('license_manage')
    else:
        form = LicenseForm(instance=license_obj)

    return render(request, 'DRM_App/license_form.html', {'form': form, 'title': f'Edit License #{license_obj.id}'})


@login_required
@content_manager_required
def license_revoke_view(request, license_id):
    license_obj = get_object_or_404(License, id=license_id)

    if not request.user.profile.is_admin and license_obj.content.owner != request.user:
        messages.error(request, "Permission Denied: Cannot revoke licenses for content owned by others.")
        return redirect('license_manage')

    license_obj.status = 'REVOKED'
    license_obj.save()
    messages.warning(request, f"License #{license_obj.id} for user '{license_obj.user.username}' has been REVOKED.")
    return redirect('license_manage')


@login_required
def my_licenses_view(request):
    licenses = License.objects.filter(user=request.user).order_by('-created_at')
    now = timezone.now()

    for lic in licenses:
        lic.check_and_update_status()

    return render(request, 'DRM_App/my_licenses.html', {'licenses': licenses, 'now': now})


# ==========================================
# ACCESS LOGS & USER MANAGEMENT
# ==========================================

@login_required
def access_logs_view(request):
    status_filter = request.GET.get('status', '')
    user = request.user

    if user.profile.is_admin:
        logs = AccessLog.objects.all()
    elif user.profile.is_content_manager:
        my_contents = DigitalContent.objects.filter(owner=user)
        logs = AccessLog.objects.filter(Q(user=user) | Q(content__in=my_contents))
    else:
        logs = AccessLog.objects.filter(user=user)

    if status_filter:
        logs = logs.filter(access_status=status_filter)

    logs = logs.order_by('-access_time')[:100]

    return render(request, 'DRM_App/access_logs.html', {
        'logs': logs,
        'current_status': status_filter,
        'status_choices': AccessLog.STATUS_CHOICES
    })


@login_required
@admin_required
def user_manage_view(request):
    users = User.objects.all().select_related('profile').order_by('-date_joined')
    return render(request, 'DRM_App/user_manage.html', {'users_list': users})


@login_required
@admin_required
def user_update_role_view(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    profile, created = UserProfile.objects.get_or_create(user=target_user)

    if request.method == 'POST':
        form = UserRoleUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, f"Role for '{target_user.username}' updated to {profile.get_role_display()}.")
            return redirect('user_manage')
    else:
        form = UserRoleUpdateForm(instance=profile)

    return render(request, 'DRM_App/user_role_form.html', {'form': form, 'target_user': target_user})


# ==========================================
# REST API ENDPOINTS (Django REST Framework)
# ==========================================

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_register(request):
    serializer = UserRegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        user_serializer = UserSerializer(user)
        return Response({'message': 'User registered successfully', 'user': user_serializer.data}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        serializer = UserSerializer(user)
        return Response({'message': 'Login successful', 'user': serializer.data}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class ContentViewSet(viewsets.ModelViewSet):
    queryset = DigitalContent.objects.all()
    serializer_class = DigitalContentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.profile.is_admin:
            return DigitalContent.objects.all()
        return DigitalContent.objects.filter(status='ACTIVE')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        has_access, access_status, reason, license_obj = verify_and_log_drm_access(request.user, instance, request)

        serializer = self.get_serializer(instance)
        data = serializer.data
        data['drm_authorization'] = {
            'has_access': has_access,
            'access_status': access_status,
            'reason': reason
        }

        if not has_access:
            # Hide sensitive payload data if denied
            data['content_body'] = "[PROTECTED CONTENT - ACCESS DENIED]"
            data['file'] = None
            return Response(data, status=status.HTTP_403_FORBIDDEN)

        return Response(data)


class LicenseViewSet(viewsets.ModelViewSet):
    queryset = License.objects.all()
    serializer_class = LicenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.profile.is_admin:
            return License.objects.all()
        elif user.profile.is_content_manager:
            my_contents = DigitalContent.objects.filter(owner=user)
            return License.objects.filter(Q(user=user) | Q(content__in=my_contents))
        return License.objects.filter(user=user)


class AccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.profile.is_admin:
            return AccessLog.objects.all()
        elif user.profile.is_content_manager:
            my_contents = DigitalContent.objects.filter(owner=user)
            return AccessLog.objects.filter(Q(user=user) | Q(content__in=my_contents))
        return AccessLog.objects.filter(user=user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_access_check(request, content_id):
    try:
        content = DigitalContent.objects.get(id=content_id)
    except DigitalContent.DoesNotExist:
        return Response({'error': 'Content not found'}, status=status.HTTP_404_NOT_FOUND)

    has_access, access_status, reason, license_obj = verify_and_log_drm_access(request.user, content, request)

    license_id = license_obj.id if license_obj else None
    expiry = license_obj.expiry_date if license_obj else None

    return Response({
        'content_id': content.id,
        'content_title': content.title,
        'user': request.user.username,
        'has_access': has_access,
        'access_status': access_status,
        'reason': reason,
        'license_id': license_id,
        'expiry_date': expiry
    })
