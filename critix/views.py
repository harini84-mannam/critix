import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from .models import Movie, Review, Watchlist, Watched, ReviewLike, ReviewReply, ReviewReport
from .forms import SignUpForm, ReviewForm
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg
from django.db.models.functions import Lower
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from datetime import date
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json


def home(request):
    movies = Movie.objects.all().order_by('id')
    movie_of_day = None

    if movies.exists():
        today_key = f"movie_of_day_{date.today()}"
        movie_of_day = cache.get(today_key)
        if not movie_of_day:
            index = date.today().toordinal() % movies.count()
            movie_of_day = movies[index]
            cache.set(today_key, movie_of_day, 86400)

    top_movies = Movie.objects.annotate(
        review_count=Count('reviews')
    ).order_by('-review_count')[:4]

    return render(request, 'home.html', {
        'movie_of_day': movie_of_day,
        'top_movies': top_movies
    })


def movie_list(request):
    query = request.GET.get('q', '')
    genre = request.GET.get('genre', '')
    sort = request.GET.get('sort', '')

    movies_queryset = Movie.objects.annotate(avg_rating=Avg('reviews__rating'))

    if query:
        movies_queryset = movies_queryset.filter(title__icontains=query)
    if genre:
        movies_queryset = movies_queryset.filter(genre__icontains=genre)

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

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_encoded_filters = query_params.urlencode()

    paginator = Paginator(movies_queryset, 8)
    page_number = request.GET.get('page')

    try:
        movies_page = paginator.page(page_number)
    except PageNotAnInteger:
        movies_page = paginator.page(1)
    except EmptyPage:
        movies_page = paginator.page(paginator.num_pages)

    return render(request, 'movie_list.html', {
        'movies': movies_page,
        'query': query,
        'selected_genre': genre,
        'selected_sort': sort,
        'filters': url_encoded_filters
    })


def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    reviews = movie.reviews.all().order_by('-created_at')

    user_review = None
    in_watchlist = False
    in_watched = False
    user_likes = {}
    user_reported = set()

    if request.user.is_authenticated:
        user_review = movie.reviews.filter(user=request.user).first()
        in_watchlist = Watchlist.objects.filter(user=request.user, movie=movie).exists()
        in_watched = Watched.objects.filter(user=request.user, movie=movie).exists()
        for lk in ReviewLike.objects.filter(user=request.user, review__movie=movie):
            user_likes[lk.review_id] = lk.value
        user_reported = set(
            ReviewReport.objects.filter(reporter=request.user, review__movie=movie).values_list('review_id', flat=True)
        )

    recommended_movies = []
    if in_watched:
        recommended_movies = Movie.objects.filter(
            genre__icontains=movie.genre
        ).exclude(id=movie.id).annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating')[:5]

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

    if request.method == 'POST':
        if user_review:
            return redirect('movie_detail', movie_id=movie.id)
        form = ReviewForm(request.POST)
        if form.is_valid():
            if not request.user.is_authenticated:
                return redirect('login')
            review = form.save(commit=False)
            review.user = request.user
            review.movie = movie
            review.save()
            return redirect('movie_detail', movie_id=movie.id)
    else:
        form = ReviewForm()

    return render(request, 'movie_detail.html', {
        'movie': movie,
        'reviews_data': reviews_data,
        'form': form,
        'user_review': user_review,
        'in_watchlist': in_watchlist,
        'in_watched': in_watched,
        'recommended_movies': recommended_movies,
    })


def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        errors = []
        if User.objects.filter(username=username).exists():
            errors.append('Username already exists')
        if User.objects.filter(email=email).exists():
            errors.append('Email already exists')
        if password1 != password2:
            errors.append('Passwords do not match')
        if len(password1) < 8:
            errors.append('Password must be at least 8 characters')

        if errors:
            return render(request, 'registration/register.html', {
                'form': SignUpForm(),
                'errors': errors
            })

        user = User.objects.create_user(username=username, email=email, password=password1)
        login(request, user)
        return redirect('home')

    return render(request, 'registration/register.html', {'form': SignUpForm()})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect('admin_dashboard')
            return redirect('home')
        else:
            return render(request, 'registration/login.html', {
                'error': 'Invalid username or password'
            })
    return render(request, 'registration/login.html')


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def user_profile(request):
    my_reviews = Review.objects.filter(user=request.user).select_related('movie').order_by('-created_at')

    stats = my_reviews.aggregate(total_count=Count('id'), avg_rating=Avg('rating'))
    reviews_count = stats['total_count'] or 0
    average_rating = round(stats['avg_rating'], 1) if stats['avg_rating'] else 0.0

    recent_reviews = my_reviews[:5]

    return render(request, 'user_profile.html', {
        'reviews': my_reviews,
        'reviews_count': reviews_count,
        'average_rating': average_rating,
        'recent_reviews': recent_reviews,
    })


@login_required
def watchlist_list(request):
    my_watchlist = Watchlist.objects.filter(user=request.user).select_related('movie').order_by('-added_at')
    return render(request, 'watchlist_movies.html', {
        'my_watchlist': my_watchlist,
    })


@login_required
def watched_list(request):
    my_watched = Watched.objects.filter(user=request.user).select_related('movie').order_by('-watched_at')
    return render(request, 'watched_movies.html', {
        'my_watched': my_watched,
    })


@login_required
def change_username(request):
    if request.method == 'POST':
        new_username = request.POST.get('new_username', '').strip()
        errors = []
        if not new_username:
            errors.append('Username cannot be empty.')
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
            'password_errors': errors,
            'show_password_modal': True,
        })
    return redirect('user_profile')


def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    review.delete()
    return redirect('user_profile')


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


@login_required
def toggle_watchlist(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    watchlist_item = Watchlist.objects.filter(user=request.user, movie=movie)

    if watchlist_item.exists():
        watchlist_item.delete()
    else:
        Watchlist.objects.create(user=request.user, movie=movie)

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('movie_detail', movie_id=movie.id)


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

    return JsonResponse({
        'likes': review.like_count(),
        'dislikes': review.dislike_count(),
        'user_vote': user_vote,
    })


@login_required
@require_POST
def reply_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    comment = request.POST.get('comment', '').strip()
    if not comment:
        return redirect('movie_detail', movie_id=review.movie.id)
    ReviewReply.objects.create(review=review, user=request.user, comment=comment)
    return redirect('movie_detail', movie_id=review.movie.id)


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