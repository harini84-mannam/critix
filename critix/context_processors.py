from .models import Watchlist, Movie


def global_navbar_data(request):
    count = 0
    if request.user.is_authenticated:
        count = Watchlist.objects.filter(user=request.user).count()

    raw_genres = Movie.objects.values_list('genre', flat=True).distinct()
    unique_genres = set()

    for raw_g in raw_genres:
        if raw_g:
            split_genres = [g.strip() for g in raw_g.split('/')]
            unique_genres.update(split_genres)

    return {
        'navbar_watchlist_count': count,
        'all_genres': sorted(list(unique_genres)),
    }


def admin_sidebar_models(request):

    if not request.path.startswith('/admin/'):
        return {}

    from .admin_views import get_apps_overview
    return {'apps_overview': get_apps_overview(request)}