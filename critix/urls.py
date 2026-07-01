from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movies/', views.movie_list, name='movie_list'),
    path('movie/<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.user_profile, name='user_profile'),
    path('watchlist/', views.watchlist_list, name='watchlist_list'),
    path('watched/', views.watched_list, name='watched_list'),
    path('profile/change-username/', views.change_username, name='change_username'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('review/delete/<int:review_id>/', views.delete_review, name='delete_review'),
    path('review/edit/<int:review_id>/', views.edit_review, name='edit_review'),
    path('review/<int:review_id>/like/', views.like_review, name='like_review'),
    path('review/<int:review_id>/reply/', views.reply_review, name='reply_review'),
    path('review/<int:review_id>/report/', views.report_review, name='report_review'),
    path('movie/<int:movie_id>/watchlist/', views.toggle_watchlist, name='toggle_watchlist'),
    path('movie/<int:movie_id>/watched/', views.toggle_watched, name='toggle_watched'),
    path('admin/', include('critix.admin_urls')),
]