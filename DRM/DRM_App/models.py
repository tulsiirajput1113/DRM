from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('CONTENT_MANAGER', 'Content Manager'),
        ('NORMAL_USER', 'Normal User'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='NORMAL_USER')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'ADMIN' or self.user.is_superuser

    @property
    def is_content_manager(self):
        return self.role in ['ADMIN', 'CONTENT_MANAGER'] or self.user.is_superuser

    @property
    def is_normal_user(self):
        return self.role == 'NORMAL_USER'


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        role = 'ADMIN' if instance.is_superuser else 'NORMAL_USER'
        UserProfile.objects.create(user=instance, role=role)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()


class DigitalContent(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('DRAFT', 'Draft'),
        ('INACTIVE', 'Inactive'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    content_body = models.TextField(help_text="Protected text or document data", blank=True, null=True)
    file = models.FileField(upload_to='digital_contents/', blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contents')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class License(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('REVOKED', 'Revoked'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='licenses')
    content = models.ForeignKey(DigitalContent, on_delete=models.CASCADE, related_name='licenses')
    start_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"License: {self.user.username} -> {self.content.title} [{self.status}]"

    def check_and_update_status(self):
        """
        Dynamically validates the license status based on the current timestamp.
        """
        now = timezone.now()
        if self.status == 'ACTIVE' and now > self.expiry_date:
            self.status = 'EXPIRED'
            self.save(update_fields=['status'])
        return self.status

    def is_currently_valid(self):
        current_status = self.check_and_update_status()
        now = timezone.now()
        return current_status == 'ACTIVE' and self.start_date <= now <= self.expiry_date


class AccessLog(models.Model):
    STATUS_CHOICES = (
        ('ACCESS_GRANTED', 'Access Granted'),
        ('ACCESS_DENIED', 'Access Denied'),
        ('LICENSE_EXPIRED', 'License Expired'),
        ('NO_LICENSE', 'No License Found'),
    )

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_logs')
    content = models.ForeignKey(DigitalContent, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_logs')
    access_time = models.DateTimeField(auto_now_add=True)
    access_status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    reason = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-access_time']

    def __str__(self):
        username = self.user.username if self.user else "Anonymous"
        content_title = self.content.title if self.content else "Unknown Content"
        return f"[{self.access_status}] {username} -> {content_title} at {self.access_time.strftime('%Y-%m-%d %H:%M:%S')}"
