from datetime import timedelta

from django.utils import timezone

from .models import Watchlist, Movie, Notification


def global_navbar_data(request):
    count = 0
    notifications = []
    unread_notification_count = 0
    if request.user.is_authenticated:
        count = Watchlist.objects.filter(user=request.user).count()
        expires_before = timezone.now() - timedelta(hours=24)
        Notification.objects.filter(
            recipient=request.user,
            created_at__lt=expires_before,
        ).delete()
        notifications = Notification.objects.filter(recipient=request.user)[:8]
        unread_notification_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    raw_genres = Movie.objects.values_list('genre', flat=True).distinct()
    unique_genres = set()

    for raw_g in raw_genres:
        if raw_g:
            split_genres = [g.strip() for g in raw_g.split('/')]
            unique_genres.update(split_genres)

    return {
        'navbar_watchlist_count': count,
        'all_genres': sorted(list(unique_genres)),
        'navbar_notifications': notifications,
        'navbar_unread_notification_count': unread_notification_count,
    }


def admin_sidebar_models(request):

    if not request.path.startswith('/admin/'):
        return {}

    from .admin_views import get_apps_overview
    return {'apps_overview': get_apps_overview(request)}
