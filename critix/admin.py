from django.contrib import admin
from django.contrib.auth.models import User, Group, Permission
from .models import (
    Movie, Review, ReviewLike, ReviewReply,
    ReviewReport, ReportAction, Notification, Watchlist, Watched,
)

def _bulk_delete(modeladmin, request, queryset):
    queryset.delete()

_bulk_delete.short_description = "Delete selected records"
_bulk_delete.requires_confirmation = True


def _mark_resolved(modeladmin, request, queryset):
    queryset.update(is_resolved=True)

_mark_resolved.short_description = "Mark selected reports as resolved"
_mark_resolved.requires_confirmation = False


def _mark_unresolved(modeladmin, request, queryset):
    queryset.update(is_resolved=False)

_mark_unresolved.short_description = "Mark selected reports as unresolved"
_mark_unresolved.requires_confirmation = False


def _activate_users(modeladmin, request, queryset):
    queryset.update(is_active=True)

_activate_users.short_description = "Activate selected users"
_activate_users.requires_confirmation = True


def _deactivate_users(modeladmin, request, queryset):
    queryset.update(is_active=False)

_deactivate_users.short_description = "Deactivate selected users"
_deactivate_users.requires_confirmation = True


def _make_staff(modeladmin, request, queryset):
    queryset.update(is_staff=True)

_make_staff.short_description = "Grant staff (admin) access"
_make_staff.requires_confirmation = True


def _revoke_staff(modeladmin, request, queryset):
    queryset.update(is_staff=False)

_revoke_staff.short_description = "Revoke staff (admin) access"
_revoke_staff.requires_confirmation = True


def _mark_notifications_read(modeladmin, request, queryset):
    queryset.update(is_read=True)

_mark_notifications_read.short_description = "Mark selected notifications as read"
_mark_notifications_read.requires_confirmation = False

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display  = ['title', 'genre', 'release_year', 'created_at']
    search_fields = ['title', 'genre', 'description']
    list_filter   = ['genre', 'release_year']
    ordering      = ['-created_at']
    actions       = []


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ['movie', 'user', 'rating', 'created_at']
    search_fields = ['comment', 'user__username', 'movie__title']
    list_filter   = ['rating']
    ordering      = ['-created_at']
    actions       = []

@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display  = ['review', 'reporter', 'reason', 'is_resolved', 'created_at']
    search_fields = ['reporter__username', 'review__comment']
    list_filter   = ['reason', 'is_resolved']
    ordering      = ['-created_at']
    actions       = [_mark_resolved, _mark_unresolved]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['recipient', 'notif_type', 'is_read', 'created_at']
    search_fields = ['message', 'recipient__username']
    list_filter   = ['notif_type', 'is_read']
    ordering      = ['-created_at']
    actions       = [_mark_notifications_read]

@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display  = ['user', 'movie', 'added_at']
    search_fields = ['user__username', 'movie__title']
    list_filter   = []
    ordering      = ['-added_at']
    actions       = []


@admin.register(Watched)
class WatchedAdmin(admin.ModelAdmin):
    list_display  = ['user', 'movie', 'watched_at']
    search_fields = ['user__username', 'movie__title']
    list_filter   = []
    ordering      = ['-watched_at']
    actions       = []

@admin.register(ReviewLike)
class ReviewLikeAdmin(admin.ModelAdmin):
    list_display  = ['review', 'user', 'value']
    search_fields = ['user__username']
    list_filter   = ['value']
    ordering      = ['id']
    actions       = []


@admin.register(ReviewReply)
class ReviewReplyAdmin(admin.ModelAdmin):
    list_display  = ['review', 'user', 'created_at']
    search_fields = ['comment', 'user__username']
    list_filter   = []
    ordering      = ['-created_at']
    actions       = []


@admin.register(ReportAction)
class ReportActionAdmin(admin.ModelAdmin):
    list_display  = ['report', 'admin_user', 'action', 'created_at']
    search_fields = ['admin_user__username']
    list_filter   = ['action']
    ordering      = ['-created_at']
    actions       = []

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display  = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    list_filter   = ['is_staff', 'is_active', 'is_superuser']
    ordering      = ['-date_joined']
    actions       = [_activate_users, _deactivate_users, _make_staff, _revoke_staff]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display  = ['name']
    search_fields = ['name']
    list_filter   = []
    ordering      = ['name']
    actions       = []


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display  = ['name', 'codename', 'content_type']
    search_fields = ['name', 'codename']
    list_filter   = []
    ordering      = ['content_type', 'codename']
    actions       = []