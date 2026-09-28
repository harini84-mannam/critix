from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movies/', views.movie_list, name='movie_list'),
    path('movie/<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', auth_views.PasswordResetView.as_view(
        template_name='registration/critix_password_reset_form.html',
        email_template_name='registration/critix_password_reset_email.txt',
        subject_template_name='registration/critix_password_reset_subject.txt',
    ), name='password_reset'),
    path('forgot-password/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/critix_password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/critix_password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/critix_password_reset_complete.html'), name='password_reset_complete'),
    path('profile/', views.user_profile, name='user_profile'),
    path('watchlist/', views.watchlist_list, name='watchlist_list'),
    path('watched/', views.watched_list, name='watched_list'),
    path('profile/change-username/', views.change_username, name='change_username'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('review/delete/<int:review_id>/', views.delete_review, name='delete_review'),
    path('reply/delete/<int:reply_id>/', views.delete_reply, name='delete_reply'),
    path('review/edit/<int:review_id>/', views.edit_review, name='edit_review'),
    path('review/<int:review_id>/like/', views.like_review, name='like_review'),
    path('review/<int:review_id>/reply/', views.reply_review, name='reply_review'),
    path('review/<int:review_id>/report/', views.report_review, name='report_review'),
    path('movie/<int:movie_id>/watchlist/', views.toggle_watchlist, name='toggle_watchlist'),
    path('movie/<int:movie_id>/watched/', views.toggle_watched, name='toggle_watched'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('notifications/clear/', views.clear_notifications, name='clear_notifications'),
    path('admin/', include('critix.admin_urls')),
]