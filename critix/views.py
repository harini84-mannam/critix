import hashlib
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from .models import (
    Movie, MovieMedia, MovieCast, Review, Watchlist, Watched, ReviewLike, ReviewReply,
    ReviewReport, Notification, UpcomingRelease, notify_user,
)

from .forms import SignUpForm, ReviewForm
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Q
from django.db.models.functions import Lower
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from datetime import date, datetime, time as dt_time, timezone as dt_timezone
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from urllib.parse import parse_qs, urlparse
import json
import re

RECENT_MOVIE_VISIT_TTL = 600  # Keep visited movies visible for ten minutes.


def _youtube_video_id(url):
    """Extract a YouTube video ID from common watch, short, or embed URLs using regex."""
    if not url:
        return ''
    # Handle various YouTube URL formats (watch, embed, youtu.be, shorts, mobile)
    regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|youtube\.com\/shorts\/)([^"&?\/\s]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else ''


def _youtube_embed_url(url):
    """Convert common YouTube links into a safe embed URL for the detail page."""
    video_id = _youtube_video_id(url)
    if not video_id:
        if url and 'youtube.com/embed/' in url:
            return url
        return ''
    # Adding enablejsapi=1 helps with origin validation in some browsers
    return f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0'


def _youtube_preview_url(url):
    """Build a muted, looping URL used only after a desktop hover begins."""
    video_id = _youtube_video_id(url)
    if not video_id:
        return ''
    return (
        f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&controls=0&loop=1'
        f'&playlist={video_id}&enablejsapi=1&rel=0'
    )


def _active_movie_visits(request):
    """Return valid session visits and remove entries older than ten minutes."""
    raw_visits = request.session.get('recent_movie_visits', {})
    if not isinstance(raw_visits, dict):
        raw_visits = {}

    now = timezone.now().timestamp()
    active_visits = {}
    for movie_id, visited_at in raw_visits.items():
        try:
            normalized_id = str(int(movie_id))
            timestamp = float(visited_at)
        except (TypeError, ValueError):
            continue
        if now - timestamp <= RECENT_MOVIE_VISIT_TTL:
            active_visits[normalized_id] = timestamp

    active_visits = dict(sorted(active_visits.items(), key=lambda item: item[1], reverse=True)[:12])
    if active_visits != raw_visits:
        request.session['recent_movie_visits'] = active_visits
        request.session.modified = True
    return active_visits


def _record_movie_visit(request, movie):
    """Record a movie detail page visit without creating database rows."""
    if request.method != 'GET':
        return

    visits = _active_movie_visits(request)
    visits[str(movie.pk)] = timezone.now().timestamp()
    request.session['recent_movie_visits'] = dict(
        sorted(visits.items(), key=lambda item: item[1], reverse=True)[:12]
    )
    request.session.modified = True


def _recent_movie_visit_items(request, limit=6):
    """Resolve active session visits into movies for the profile activity panel."""
    visits = _active_movie_visits(request)
    if not visits:
        return []

    movie_ids = [int(movie_id) for movie_id in visits]
    movies = Movie.objects.in_bulk(movie_ids)
    activity = []
    for movie_id, visited_at in visits.items():
        movie = movies.get(int(movie_id))
        if movie:
            activity.append({
                'movie': movie,
                'visited_at': datetime.fromtimestamp(visited_at, tz=dt_timezone.utc),
            })
    return activity[:limit]


# Home page
def _daily_pick(ids, day):
    """Pick one id for ``day``. Same day + same ids always gives the same answer, and adding an
    id only changes the result if that id itself scores highest (rendezvous hashing), unlike
    ``ordinal % len(ids)`` which reshuffles whenever the list length changes."""
    return max(ids, key=lambda i: hashlib.sha256(f"{day.isoformat()}:{i}".encode()).hexdigest())


def _movie_of_the_day_id():
    """One movie per calendar day.

    Only movies that existed when the day began are eligible, so importing or adding movies
    later the same day cannot change today's pick. The result is cached, but the cache is
    only an optimisation: recomputing it (e.g. after a server restart) gives the same movie.
    """
    today = date.today()
    key = f"movie_of_day_v2_{today}"
    cached_id = cache.get(key)
    if cached_id and Movie.objects.filter(pk=cached_id).exists():
        return cached_id

    with_poster = Movie.objects.exclude(poster='').exclude(poster__isnull=True)
    start_of_day = datetime.combine(today, dt_time.min).astimezone()  # local midnight, timezone-aware
    ids = (
        list(with_poster.filter(created_at__lt=start_of_day).values_list('id', flat=True))
        or list(with_poster.values_list('id', flat=True))
        or list(Movie.objects.values_list('id', flat=True))
    )
    if not ids:
        return None
    chosen = _daily_pick(ids, today)
    cache.set(key, chosen, 86400)
    return chosen


def home(request):
    movie_of_day = None

# selects one movie for today's recommendation (same movie all day)
    movie_of_day_id = _movie_of_the_day_id()
    if movie_of_day_id:
        # Fetch with annotation for the hero section
        movie_of_day = Movie.objects.annotate(
            average_rating=Avg('reviews__rating')
        ).filter(id=movie_of_day_id).first()

# helps to get top 4 movies with the highest number of reviews and their average ratings
    top_movies = Movie.objects.annotate(
        review_count=Count('reviews'),
        average_rating=Avg('reviews__rating')
    ).order_by('-review_count')[:4]

# upcoming Telugu releases, kept fresh by `sync_upcoming_releases` (run manually or via a weekly cron job)
    upcoming_releases = UpcomingRelease.objects.filter(release_date__gt=date.today())[:12]    return render(request, 'home.html', {
        'movie_of_day': movie_of_day,
        'top_movies': top_movies,
        'upcoming_releases': upcoming_releases,
    })

# shows all movies with search sort and filtering
def movie_list(request):
# gets search and filter values
    query = request.GET.get('q', '')
    genre = request.GET.get('genre', '')
    decade = request.GET.get('decade', '')
    sort = request.GET.get('sort', '')

# calculates avg rating for every movie
    movies_queryset = Movie.objects.annotate(avg_rating=Avg('reviews__rating'))

# this searches by title OR by a cast member's name, so "Mahesh Babu" finds his films too
    if query:
        movies_queryset = movies_queryset.filter(
            Q(title__icontains=query) | Q(cast_members__name__icontains=query)
        ).distinct()
    if genre:
        movies_queryset = movies_queryset.filter(genre__icontains=genre)
    if decade:
        try:
            decade_start = int(decade)
            movies_queryset = movies_queryset.filter(release_year__gte=decade_start, release_year__lte=decade_start + 9)
        except ValueError:
            pass
# this filters by genres
    if sort == 'newest':
        movies_queryset = movies_queryset.order_by('-release_year')
    elif sort == 'oldest':
        movies_queryset = movies_queryset.order_by('release_year')
    elif sort == 'az':
        movies_queryset = movies_queryset.annotate(lower_title=Lower('title')).order_by('lower_title')
    elif sort == 'za':
        movies_queryset = movies_queryset.annotate(lower_title=Lower('title')).order_by('-lower_title')
    elif sort == 'rating':
        movies_queryset = movies_queryset.order_by('-avg_rating')
    else:
        movies_queryset = movies_queryset.order_by('-id')

# this keeps the search filters while we change the pages too
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_encoded_filters = query_params.urlencode()

# 24 per page (was 8) so ~800 movies is ~34 pages instead of 100
    paginator = Paginator(movies_queryset, 24)
    page_number = request.GET.get('page')

    try:
        movies_page = paginator.page(page_number)
    except PageNotAnInteger:
        movies_page = paginator.page(1)
    except EmptyPage:
        movies_page = paginator.page(paginator.num_pages)

# builds a short page-number window (e.g. 1 … 7 8 [9] 10 11 … 34) instead of one link per page
    current = movies_page.number
    total_pages = paginator.num_pages
    window = 2
    page_numbers = [
        p for p in range(current - window, current + window + 1)
        if 1 <= p <= total_pages
    ]
    show_first_ellipsis = page_numbers and page_numbers[0] > 2
    show_first = page_numbers and page_numbers[0] > 1
    show_last_ellipsis = page_numbers and page_numbers[-1] < total_pages - 1
    show_last = page_numbers and page_numbers[-1] < total_pages

    all_genres_split = sorted({
        g.strip() for raw in Movie.objects.values_list('genre', flat=True) for g in (raw or '').split('/') if g.strip()
    })
    decades = sorted({(y // 10) * 10 for y in Movie.objects.values_list('release_year', flat=True) if y}, reverse=True)

    return render(request, 'movie_list.html', {
        'movies': movies_page,
        'query': query,
        'selected_genre': genre,
        'selected_decade': decade,
        'selected_sort': sort,
        'filters': url_encoded_filters,
        'page_numbers': page_numbers,
        'show_first': show_first,
        'show_first_ellipsis': show_first_ellipsis,
        'show_last': show_last,
        'show_last_ellipsis': show_last_ellipsis,
        'chip_genres': all_genres_split[:10],
        'decades': decades,
    })

# this function shows the details about the movie 
def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    _record_movie_visit(request, movie)
    reviews = movie.reviews.all().order_by('-created_at') # helps to get all reviews for the movie

# default values
    user_review = None
    in_watchlist = False
    in_watched = False
    user_likes = {}
    user_reported = set()

# checks user related data if logged in
    if request.user.is_authenticated:
        # checks if the user has already reviewd this movie
        user_review = movie.reviews.filter(user=request.user).first()
        # checks if the user has any watchlist and watched movies
        in_watchlist = Watchlist.objects.filter(user=request.user, movie=movie).exists()
        in_watched = Watched.objects.filter(user=request.user, movie=movie).exists()
        # stores the users like and dislikes
        for lk in ReviewLike.objects.filter(user=request.user, review__movie=movie):
            user_likes[lk.review_id] = lk.value
        # stores users reported reviews
        user_reported = set(
            ReviewReport.objects.filter(reporter=request.user, review__movie=movie).values_list('review_id', flat=True)
        )
# prepares optional trailers, gallery photos, and cast data
    media_assets = movie.media_assets.all()
    gallery_media = media_assets.filter(media_type='image')
    trailer_media = []
    for media in media_assets.filter(media_type='trailer'):
        media.embed_url = _youtube_embed_url(media.url)
        media.preview_url = _youtube_preview_url(media.url)
        trailer_media.append(media)
    cast_members = movie.cast_members.all()

    recommended_movies = []
    if in_watched:
        # match ANY shared genre, not the whole "Drama/Romance/Comedy" string at once
        genre_query = Q()
        for g in movie.genre_list():
            genre_query |= Q(genre__icontains=g)

        recommended_movies = Movie.objects.filter(genre_query).exclude(id=movie.id) if genre_query else Movie.objects.none()
        recommended_movies = recommended_movies.annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating')[:5]

    review_sort = request.GET.get('review_sort', 'newest')
    reviews_data = []
    for review in reviews:
        replies = review.replies.select_related('user').order_by('created_at')
        reviews_data.append({
            'review': review,
            'likes': review.like_count(),
            'dislikes': review.dislike_count(),
            'user_vote': user_likes.get(review.id),
            'already_reported': review.id in user_reported,
            'replies': replies,
        })
    # newest is already the default order from the query above
    if review_sort == 'highest':
        reviews_data.sort(key=lambda item: item['review'].rating, reverse=True)
    elif review_sort == 'helpful':
        reviews_data.sort(key=lambda item: item['likes'], reverse=True)

# saves review data
    if request.method == 'POST':
        # does not allow multiple reviews from the same user
        if user_review:
            return redirect('movie_detail', movie_id=movie.id)
        form = ReviewForm(request.POST)
        if form.is_valid():
            # redirects to login, if the user is not logged in
            if not request.user.is_authenticated:
                return redirect('login')
            # saves reviews
            review = form.save(commit=False)
            review.user = request.user
            review.movie = movie
            review.save()
            return redirect('movie_detail', movie_id=movie.id)
    else:
        # shows empty review form
        form = ReviewForm()
# display movie details page
    return render(request, 'movie_detail.html', {
        'movie': movie,
        'reviews_data': reviews_data,
        'form': form,
        'user_review': user_review,
        'in_watchlist': in_watchlist,
        'in_watched': in_watched,
        'recommended_movies': recommended_movies,
        'gallery_media': gallery_media,
        'trailer_media': trailer_media,
        'cast_members': cast_members,
        'review_sort': review_sort,
        'rating_breakdown': movie.rating_breakdown(),
        'backdrop': movie.backdrop_image(),
    })

# marks all of the current user's notifications as read (called when the bell dropdown opens)
@login_required
@require_POST
def mark_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def clear_notifications(request):
    Notification.objects.filter(recipient=request.user).delete()
    return redirect(request.META.get('HTTP_REFERER') or 'home')


# register if not logged in
def register(request):
    # checks if form is submitted
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        errors = []
        # validate username, email, password match, password length
        if User.objects.filter(username=username).exists():
            errors.append('Username already exists')
        if User.objects.filter(email=email).exists():
            errors.append('Email already exists')
        if password1 != password2:
            errors.append('Passwords do not match')
        if len(password1) < 8:
            errors.append('Password must be at least 8 characters')
        # shows errors if validation fails
        if errors:
            return render(request, 'registration/register.html', {
                'form': SignUpForm(),
                'errors': errors
            })
        # creates a new user
        user = User.objects.create_user(username=username, email=email, password=password1)
        # login after registration
        login(request, user)
        return redirect('home')
    # shows registration form
    return render(request, 'registration/register.html', {'form': SignUpForm()})

# login user
def login_view(request):
    if request.method == 'POST':
        # gets login details
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            # login successfully
            login(request, user)
            # redirects to admin dashboard
            if user.is_staff:
                return redirect('admin_dashboard')
            return redirect('home')
        else:
            # if the user / details details doesnot exist
            return render(request, 'registration/login.html', {
                'error': 'Invalid username or password'
            })
        # shows login form
    return render(request, 'registration/login.html')

# logout 
def logout_view(request):
    logout(request)
    return redirect('home')

# displays user profile
@login_required
def user_profile(request):
    # get all reviews by current user
    my_reviews = Review.objects.filter(user=request.user).select_related('movie').order_by('-created_at')
    # calculate review statistics
    stats = my_reviews.aggregate(total_count=Count('id'), avg_rating=Avg('rating'))
    reviews_count = stats['total_count'] or 0
    average_rating = round(stats['avg_rating'], 1) if stats['avg_rating'] else 0.0
    # gets latest five reviews and active movie visits from this session
    recent_reviews = my_reviews[:5]
    recent_movie_visits = _recent_movie_visit_items(request)

# films watched this year + favourite genres, built from watched + reviewed movies
    watched_this_year = Watched.objects.filter(user=request.user, watched_at__year=date.today().year).count()
    genre_counts = {}
    genre_source_movies = Movie.objects.filter(
        Q(watched_by_users__user=request.user) | Q(reviews__user=request.user)
    ).distinct()
    for m in genre_source_movies:
        for g in m.genre_list():
            genre_counts[g] = genre_counts.get(g, 0) + 1
    top_genre_count = max(genre_counts.values()) if genre_counts else 0
    favourite_genres = [
        {'genre': g, 'count': c, 'percent': round((c / top_genre_count) * 100) if top_genre_count else 0}
        for g, c in sorted(genre_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    return render(request, 'user_profile.html', {
        'reviews': my_reviews,
        'reviews_count': reviews_count,
        'average_rating': average_rating,
        'recent_reviews': recent_reviews,
        'recent_movie_visits': recent_movie_visits,
        'watched_this_year': watched_this_year,
        'favourite_genres': favourite_genres,
    })

# shows users watchlist
@login_required
def watchlist_list(request):
    my_watchlist = Watchlist.objects.filter(user=request.user).select_related('movie').order_by('-added_at')
    return render(request, 'watchlist_movies.html', {
        'my_watchlist': my_watchlist,
    })

# shows users watched movies
@login_required
def watched_list(request):
    my_watched = Watched.objects.filter(user=request.user).select_related('movie').order_by('-watched_at')
    return render(request, 'watched_movies.html', {
        'my_watched': my_watched,
    })

# helps to change the username
@login_required
def change_username(request):
    if request.method == 'POST':
        new_username = request.POST.get('new_username', '').strip()
        errors = []
        if not new_username:
            errors.append('Username cannot be empty.')
        # validates username's length
        elif len(new_username) < 3:
            errors.append('Username must be at least 3 characters.')
        elif User.objects.filter(username=new_username).exclude(pk=request.user.pk).exists():
            errors.append('That username is already taken.')
        else:
            request.user.username = new_username
            request.user.save()
            return redirect('user_profile')

        my_reviews = Review.objects.filter(user=request.user).select_related('movie').order_by('-created_at')
        stats = my_reviews.aggregate(total_count=Count('id'), avg_rating=Avg('rating'))
        return render(request, 'user_profile.html', {
            'reviews': my_reviews,
            'reviews_count': stats['total_count'] or 0,
            'average_rating': round(stats['avg_rating'], 1) if stats['avg_rating'] else 0.0,
            'recent_reviews': my_reviews[:5],
            'recent_movie_visits': _recent_movie_visit_items(request),
            'username_errors': errors,
            'show_username_modal': True,
        })
    return redirect('user_profile')


@login_required
def change_password(request):
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        errors = []

        if not request.user.check_password(current):
            errors.append('Current password is incorrect.')
        if len(new_pw) < 8:
            errors.append('New password must be at least 8 characters.')
        if new_pw != confirm:
            errors.append('New passwords do not match.')

        if not errors:
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)
            return redirect('user_profile')

        my_reviews = Review.objects.filter(user=request.user).select_related('movie').order_by('-created_at')
        stats = my_reviews.aggregate(total_count=Count('id'), avg_rating=Avg('rating'))
        return render(request, 'user_profile.html', {
            'reviews': my_reviews,
            'reviews_count': stats['total_count'] or 0,
            'average_rating': round(stats['avg_rating'], 1) if stats['avg_rating'] else 0.0,
            'recent_reviews': my_reviews[:5],
            'recent_movie_visits': _recent_movie_visit_items(request),
            'password_errors': errors,
            'show_password_modal': True,
        })
    return redirect('user_profile')

@login_required
# helps the user to delete their own review
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    review.delete()
    return redirect('user_profile')


@login_required
def delete_reply(request, reply_id):
    reply = get_object_or_404(ReviewReply, id=reply_id, user=request.user)
    movie_id = reply.review.movie_id
    reply.delete()
    return redirect('movie_detail', movie_id=movie_id)


# helps the user to edit their own review
@login_required
def edit_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    movie = review.movie

    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            return redirect('movie_detail', movie_id=movie.id)
    else:
        form = ReviewForm(instance=review)

    return render(request, 'edit_review.html', {'form': form, 'movie': movie})

# Add or remove a movie from the user's watchlist
@login_required
def toggle_watchlist(request, movie_id):
    # Get the selected movie
    movie = get_object_or_404(Movie, id=movie_id)
    # checks if the movie is already in watchlist
    watchlist_item = Watchlist.objects.filter(user=request.user, movie=movie)
    # removes the movie already exists or deletes
    if watchlist_item.exists():
        watchlist_item.delete()
    else:
        # A movie may belong to only one progress list at a time.
        Watched.objects.filter(user=request.user, movie=movie).delete()
        Watchlist.objects.create(user=request.user, movie=movie)
    # return to the previous page if available
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    # Otherwise, go back to the movie details page
    return redirect('movie_detail', movie_id=movie.id)

# add or remove a movie from the watched list
@login_required
def toggle_watched(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    watched_item = Watched.objects.filter(user=request.user, movie=movie)

    if watched_item.exists():
        watched_item.delete()
    else:
        Watched.objects.create(user=request.user, movie=movie)
        Watchlist.objects.filter(user=request.user, movie=movie).delete()

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('movie_detail', movie_id=movie.id)

# saves the users likes to the review
@login_required
@require_POST
def like_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    data = json.loads(request.body)
    value = data.get('value')  

    if value not in ('like', 'dislike'):
        return JsonResponse({'error': 'Invalid value'}, status=400)

    existing = ReviewLike.objects.filter(review=review, user=request.user).first()

    if existing:
        if existing.value == value:
            existing.delete()
            user_vote = None
        else:
            existing.value = value
            existing.save()
            user_vote = value
    else:
        ReviewLike.objects.create(review=review, user=request.user, value=value)
        user_vote = value

    # Notify the review owner only when another user adds or changes a vote.
    # Removing an existing vote is intentionally silent.
    if user_vote and review.user_id != request.user.id:
        action_label = 'liked' if value == 'like' else 'disliked'
        notify_user(
            review.user,
            f"{request.user.username} {action_label} your review of {review.movie.title}.",
            'general',
        )

    return JsonResponse({
        'likes': review.like_count(),
        'dislikes': review.dislike_count(),
        'user_vote': user_vote,
    })

# saves the users reply to the review
@login_required
@require_POST
def reply_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    comment = request.POST.get('comment', '').strip()
    if not comment:
        return redirect('movie_detail', movie_id=review.movie.id)
    ReviewReply.objects.create(review=review, user=request.user, comment=comment)
    if review.user_id != request.user.id:
        notify_user(
            review.user,
            f"{request.user.username} commented on your review of {review.movie.title}.",
            'general',
        )
    return redirect('movie_detail', movie_id=review.movie.id)

# if the user has reported any review, it stores
@login_required
@require_POST
def report_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    reason = request.POST.get('reason', 'other')

    already = ReviewReport.objects.filter(review=review, reporter=request.user).exists()
    if not already:
        ReviewReport.objects.create(review=review, reporter=request.user, reason=reason)

    referer = request.META.get('HTTP_REFERER')
    return redirect(referer or 'movie_detail', movie_id=review.movie.id)
