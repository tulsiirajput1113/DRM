from django.utils import timezone
from .models import License, AccessLog, DigitalContent


def get_client_ip(request):
    """Utility to extract user IP address from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def verify_and_log_drm_access(user, content, request=None):
    """
    Core DRM Authorization Pipeline:
    1. Authentication check
    2. Role & Ownership check
    3. License validity & expiration check
    4. Access Log persistence

    Returns:
        tuple: (has_access: bool, access_status: str, reason: str, license_obj: License|None)
    """
    ip_address = get_client_ip(request) if request else None

    # 1. Unauthenticated check
    if not user or not user.is_authenticated:
        status = 'ACCESS_DENIED'
        reason = 'Unauthenticated access attempt.'
        AccessLog.objects.create(
            user=None,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return False, status, reason, None

    # Ensure profile exists
    profile = getattr(user, 'profile', None)

    # 2. Content Status check
    if content.status != 'ACTIVE' and not (profile and profile.is_admin) and content.owner != user:
        status = 'ACCESS_DENIED'
        reason = f'Content is currently in {content.status} state and inaccessible.'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return False, status, reason, None

    # 3. Admin bypass
    if profile and profile.is_admin:
        status = 'ACCESS_GRANTED'
        reason = 'Access Granted: Administrative override privileges.'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return True, status, reason, None

    # 4. Owner bypass
    if content.owner == user:
        status = 'ACCESS_GRANTED'
        reason = 'Access Granted: Creator/Owner of digital content.'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return True, status, reason, None

    # 5. License validation
    user_licenses = License.objects.filter(user=user, content=content).order_by('-created_at')

    if not user_licenses.exists():
        status = 'NO_LICENSE'
        reason = 'Access Denied: No license found for this digital content.'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return False, status, reason, None

    # Check for active & valid license
    active_license = None
    expired_license = None

    for lic in user_licenses:
        lic.check_and_update_status()
        if lic.is_currently_valid():
            active_license = lic
            break
        elif lic.status == 'EXPIRED' or timezone.now() > lic.expiry_date:
            expired_license = lic

    if active_license:
        status = 'ACCESS_GRANTED'
        formatted_expiry = active_license.expiry_date.strftime('%b %d, %Y %H:%M')
        reason = f'Access Granted: Valid active license (Expires: {formatted_expiry}).'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return True, status, reason, active_license

    if expired_license:
        status = 'LICENSE_EXPIRED'
        formatted_expiry = expired_license.expiry_date.strftime('%b %d, %Y %H:%M')
        reason = f'Access Denied: License expired on {formatted_expiry}.'
        AccessLog.objects.create(
            user=user,
            content=content,
            access_status=status,
            reason=reason,
            ip_address=ip_address
        )
        return False, status, reason, expired_license

    # Fallback if revoked or inactive
    status = 'ACCESS_DENIED'
    reason = 'Access Denied: License status is revoked or inactive.'
    AccessLog.objects.create(
        user=user,
        content=content,
        access_status=status,
        reason=reason,
        ip_address=ip_address
    )
    return False, status, reason, None
