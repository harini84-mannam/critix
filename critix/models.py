from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg

# stores movie details
class Movie(models.Model):
    title = models.CharField(max_length=200)
    genre = models.CharField(max_length=100)
    description = models.TextField()
    release_year = models.IntegerField()
    # Filled automatically by the backend TMDB enrichment service; hidden
    # from the existing generic admin form so the UI remains unchanged.
    tmdb_id = models.PositiveIntegerField(null=True, blank=True, unique=True, editable=False)
    poster = models.ImageField(upload_to='posters/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Where-to-watch providers for India, filled by the TMDB sync command.
    # Shape: {"flatrate": [{"name": "...", "logo": "https://..."}], "rent": [...], "buy": [...]}
    watch_providers = models.JSONField(blank=True, null=True, default=dict)

    # calculates the avg rating fot the movie
    def average_rating(self):
        return self.reviews.aggregate(avg=Avg('rating'))['avg'] or 0

    # counts how many reviews gave each star rating, for the rating breakdown bar chart
    def rating_breakdown(self):
        counts = {i: 0 for i in range(1, 6)}
        for rating, count in self.reviews.values_list('rating').annotate(models.Count('id')):
            counts[rating] = count
        total = sum(counts.values())
        return [
            {
                'stars': stars,
                'count': counts[stars],
                'percent': round((counts[stars] / total) * 100) if total else 0,
            }
            for stars in range(5, 0, -1)
        ]

    # the movie's genres as a clean list, since imported genres are stored as "Drama/Romance"
    def genre_list(self):
        return [g.strip() for g in (self.genre or '').split('/') if g.strip()]

    def backdrop_image(self):
        """Best available wide image for a blurred banner: a gallery still, else the poster."""
        first_gallery = self.media_assets.filter(media_type='image').exclude(image='').first()
        if first_gallery and first_gallery.image:
            return first_gallery.image
        return self.poster or None

    def __str__(self):
        return f"{self.title} ({self.release_year})"

class MovieMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ('image', 'Photo'),
        ('trailer', 'Trailer'),
    ]

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='media_assets')
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPE_CHOICES, default='image')
    image = models.ImageField(upload_to='movie_media/', blank=True, null=True)
    url = models.URLField(blank=True)
    caption = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        verbose_name = 'Movie media'
        verbose_name_plural = 'Movie media'

    def __str__(self):
        label = self.caption or self.get_media_type_display()
        return f"{self.movie.title} — {label}"


class MovieCast(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='cast_members')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150, blank=True)
    photo = models.ImageField(upload_to='movie_cast/', blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Movie cast member'
        verbose_name_plural = 'Movie cast members'

    def __str__(self):
        return f"{self.name} — {self.movie.title}"


# stores user's reviews for movies
class Review(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(
        choices=[(i, "⭐" * i) for i in range(1, 6)]
    )
    comment = models.TextField(blank=True)  # optional: a rating alone is a valid review
    contains_spoiler = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'movie'],
                name='unique_user_movie_review'
            )
        ]
# displays reviews as the user and movie title
    def __str__(self):
        return f"{self.user.username} - {self.movie.title}"
# calculates total like
    def like_count(self):
        return self.likes.filter(value='like').count()
# calculates total dislike
    def dislike_count(self):
        return self.likes.filter(value='dislike').count()

# stores users likes and dislikes for reviews
class ReviewLike(models.Model):
    LIKE_CHOICES = [('like', 'Like'), ('dislike', 'Dislike')]
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    value = models.CharField(max_length=10, choices=LIKE_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review', 'user'], name='unique_review_like')
        ]

    def __str__(self):
        return f"{self.user.username} {self.value}d {self.review}"

# stores users reply for reviews
class ReviewReply(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} replied to {self.review}"

# stores review reports submitted by users
class ReviewReport(models.Model):
    REASON_CHOICES = [
        ('spam', 'Spam'),
        ('offensive', 'Offensive / Hate Speech'),
        ('spoiler', 'Spoilers'),
        ('irrelevant', 'Not relevant'),
        ('other', 'Other'),
    ]
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        # doesnot allow the user to do multiple reports
        constraints = [
            models.UniqueConstraint(fields=['review', 'reporter'], name='unique_review_report')
        ]

    def __str__(self):
        return f"{self.reporter.username} reported review #{self.review.id}"

# saves the actions taken by the user
class ReportAction(models.Model):
    ACTION_CHOICES = [
        ('dismissed', 'Report Dismissed'),
        ('review_deleted', 'Review Deleted'),
    ]
    report = models.ForeignKey(ReviewReport, on_delete=models.CASCADE, related_name='actions')
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin_user.username} {self.action} on report #{self.report.id}"
# saves the notification of users actions
class Notification(models.Model):
    TYPE_CHOICES = [
        ('blocked', 'Account Blocked'),
        ('unblocked', 'Account Unblocked'),
        ('review_removed', 'Review Removed'),
        ('warning', 'Warning'),
        ('general', 'General'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notif_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='general')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"To {self.recipient.username}: {self.message[:40]}"


def notify_user(user, message, notif_type='general'):
    return Notification.objects.create(recipient=user, message=message, notif_type=notif_type)

# saves when the user adds the movie to the watchlist
class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='watchlist')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='watched_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_user_movie_watchlist')
        ]

    def __str__(self):
        return f"{self.user.username} - {self.movie.title}"

# saves when the user adds a movie to the watched
class Watched(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='watched')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='watched_by_users')
    watched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_user_movie_watched')
        ]
        ordering = ['-watched_at']

    def __str__(self):
        return f"{self.user.username} watched {self.movie.title}"


# upcoming Telugu releases for the "Coming Soon" row on the home page.
# Populated by `python manage.py sync_upcoming_releases` (run manually or on a schedule/cron),
# separate from the Movie table since these titles haven't released yet.
class UpcomingRelease(models.Model):
    tmdb_id = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=200)
    poster_url = models.URLField(blank=True)
    release_date = models.DateField()
    trailer_url = models.URLField(blank=True)
    overview = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['release_date']

    def __str__(self):
        return f"{self.title} ({self.release_date})"