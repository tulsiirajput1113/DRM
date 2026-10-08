from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from DRM_App.models import UserProfile, DigitalContent, License, AccessLog


class Command(BaseCommand):
    help = "Seeds initial demo users, digital assets, licenses, and access logs for testing DRM system."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting DRM Demo Seeding..."))

        # 1. Create Superuser / Admin
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@drm.com", "first_name": "Admin", "last_name": "User", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
        admin_profile, _ = UserProfile.objects.get_or_create(user=admin_user)
        admin_profile.role = 'ADMIN'
        admin_profile.save()

        # 2. Create Content Manager
        cm_user, created = User.objects.get_or_create(
            username="manager",
            defaults={"email": "manager@drm.com", "first_name": "Content", "last_name": "Manager"}
        )
        if created:
            cm_user.set_password("manager123")
            cm_user.save()
        cm_profile, _ = UserProfile.objects.get_or_create(user=cm_user)
        cm_profile.role = 'CONTENT_MANAGER'
        cm_profile.save()

        # 3. Create Normal Users
        user1, created = User.objects.get_or_create(
            username="user1",
            defaults={"email": "user1@drm.com", "first_name": "Alice", "last_name": "Smith"}
        )
        if created:
            user1.set_password("user123")
            user1.save()
        u1_profile, _ = UserProfile.objects.get_or_create(user=user1)
        u1_profile.role = 'NORMAL_USER'
        u1_profile.save()

        user2, created = User.objects.get_or_create(
            username="user2",
            defaults={"email": "user2@drm.com", "first_name": "Bob", "last_name": "Jones"}
        )
        if created:
            user2.set_password("user123")
            user2.save()
        u2_profile, _ = UserProfile.objects.get_or_create(user=user2)
        u2_profile.role = 'NORMAL_USER'
        u2_profile.save()

        # 4. Create Digital Assets
        asset1, _ = DigitalContent.objects.get_or_create(
            title="Enterprise Cloud Security Blueprint 2026",
            defaults={
                "description": "Comprehensive architectural guide covering Zero-Trust access control, identity federation, and automated compliance management.",
                "content_body": "CONFIDENTIAL PAYLOAD: Section 4.2 - Key rotation protocols must occur every 90 days across all secure enclaves. Access strictly logged via DRM audit pipeline.",
                "owner": cm_user,
                "status": "ACTIVE"
            }
        )

        asset2, _ = DigitalContent.objects.get_or_create(
            title="Advanced Cryptography & DRM Engineering",
            defaults={
                "description": "In-depth guide on digital signatures, symmetric/asymmetric encryption, and robust license validation patterns.",
                "content_body": "CONFIDENTIAL PAYLOAD: Section 1.8 - License validation must inspect start timestamp, expiration timestamp, user role authorization, and revocation flags.",
                "owner": cm_user,
                "status": "ACTIVE"
            }
        )

        asset3, _ = DigitalContent.objects.get_or_create(
            title="Internal Admin Operations Handbook",
            defaults={
                "description": "Restricted administrative operating manual for system administrators.",
                "content_body": "CONFIDENTIAL PAYLOAD: Admin root escalation credentials and backup site recovery protocols.",
                "owner": admin_user,
                "status": "ACTIVE"
            }
        )

        # 5. Create Licenses
        now = timezone.now()

        # Active License for user1 on asset1 (Valid for 30 days)
        License.objects.get_or_create(
            user=user1,
            content=asset1,
            defaults={
                "start_date": now - timedelta(days=1),
                "expiry_date": now + timedelta(days=30),
                "status": "ACTIVE"
            }
        )

        # Expired License for user1 on asset2 (Expired 2 days ago)
        License.objects.get_or_create(
            user=user1,
            content=asset2,
            defaults={
                "start_date": now - timedelta(days=30),
                "expiry_date": now - timedelta(days=2),
                "status": "EXPIRED"
            }
        )

        # 6. Create Initial Seed Access Logs
        AccessLog.objects.get_or_create(
            user=user1,
            content=asset1,
            access_status="ACCESS_GRANTED",
            defaults={
                "reason": "Access Granted: Valid active license (Expires in 30 days).",
                "ip_address": "127.0.0.1"
            }
        )

        AccessLog.objects.get_or_create(
            user=user1,
            content=asset2,
            access_status="LICENSE_EXPIRED",
            defaults={
                "reason": "Access Denied: License expired on " + (now - timedelta(days=2)).strftime('%b %d, %Y %H:%M') + ".",
                "ip_address": "127.0.0.1"
            }
        )

        AccessLog.objects.get_or_create(
            user=user2,
            content=asset1,
            access_status="NO_LICENSE",
            defaults={
                "reason": "Access Denied: No license found for this digital content.",
                "ip_address": "127.0.0.1"
            }
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded DRM Demo database!"))
        self.stdout.write(self.style.SUCCESS("Credentials created:"))
        self.stdout.write(" - Admin: username 'admin', password 'admin123'")
        self.stdout.write(" - Content Manager: username 'manager', password 'manager123'")
        self.stdout.write(" - User 1 (Has Active License for Asset 1): username 'user1', password 'user123'")
        self.stdout.write(" - User 2 (No License): username 'user2', password 'user123'")
