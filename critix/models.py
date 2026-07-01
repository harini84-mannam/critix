from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg


class Movie(models.Model):
    title = models.CharField(max_length=200)
    genre = models.CharField(max_length=100)
    description = models.TextField()
    release_year = models.IntegerField()
    poster = models.ImageField(upload_to='posters/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def average_rating(self):
        return self.reviews.aggregate(avg=Avg('rating'))['avg'] or 0


class Review(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(
        choices=[(i, "⭐" * i) for i in range(1, 6)]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'movie'],
                name='unique_user_movie_review'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.movie.title}"

    def like_count(self):
        return self.likes.filter(value='like').count()

    def dislike_count(self):
        return self.likes.filter(value='dislike').count()


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


class ReviewReply(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} replied to {self.review}"


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
        constraints = [
            models.UniqueConstraint(fields=['review', 'reporter'], name='unique_review_report')
        ]

    def __str__(self):
        return f"{self.reporter.username} reported review #{self.review.id}"


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