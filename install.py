"""
Run this from inside movie_proj/movie_review/ (same folder as manage.py):

    python install.py

It writes every changed file directly into the right place, then verifies.
"""
import os, sys, textwrap

BASE = os.path.dirname(os.path.abspath(__file__))
CRITIX = os.path.join(BASE, 'critix')
TMPL   = os.path.join(CRITIX, 'templates', 'admin_portal')
PROJ   = os.path.join(BASE, 'movie_review')

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(textwrap.dedent(content).lstrip('\n'))
    print(f'  wrote  {os.path.relpath(path, BASE)}')

print('\n=== Installing dynamic admin portal ===\n')

# ─────────────────────────────────────────────────────────────────────────────
# 1. movie_review/urls.py  (project-level)
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(PROJ, 'urls.py'), '''
    from django.contrib import admin
    from django.urls import path, include
    from django.conf import settings
    from django.conf.urls.static import static

    urlpatterns = [
        path('django-admin/', admin.site.urls),
        path('', include('critix.urls')),
    ]

    if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
''')

# ─────────────────────────────────────────────────────────────────────────────
# 2. critix/admin_urls.py
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(CRITIX, 'admin_urls.py'), '''
    from django.urls import path
    from . import admin_views

    urlpatterns = [
        path('dashboard/',                                    admin_views.admin_dashboard,    name='admin_dashboard'),
        path('genres/',                                       admin_views.admin_genres,        name='admin_genres'),
        path('genres/rename/',                                admin_views.admin_genre_rename,  name='admin_genre_rename'),
        path('genres/delete/',                                admin_views.admin_genre_delete,  name='admin_genre_delete'),
        path('models/<str:model_name>/add/',                  admin_views.admin_model_add,     name='admin_model_add'),
        path('models/<str:model_name>/action/',               admin_views.admin_model_action,  name='admin_model_action'),
        path('models/<str:model_name>/<str:pk>/edit/',        admin_views.admin_model_edit,    name='admin_model_edit'),
        path('models/<str:model_name>/<str:pk>/delete/',      admin_views.admin_model_delete,  name='admin_model_delete'),
        path('models/<str:model_name>/',                      admin_views.admin_model_list,    name='admin_model_list'),
        path('api/meta/<str:model_name>/',                    admin_views.admin_metadata_api,  name='admin_metadata_api'),
    ]
''')

# ─────────────────────────────────────────────────────────────────────────────
# 3. critix/admin_metadata.py  (new file)
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(CRITIX, 'admin_metadata.py'), r'''
    from django.contrib import admin as django_admin
    from django.apps import apps


    def _field_verbose(model, name):
        parts = name.split('__')
        current_model = model
        label_parts = []
        for part in parts:
            try:
                field = current_model._meta.get_field(part)
                label_parts.append(field.verbose_name.title())
                if hasattr(field, 'related_model') and field.related_model:
                    current_model = field.related_model
            except Exception:
                label_parts.append(part.replace('_', ' ').title())
        return ' '.join(label_parts)


    def _distinct_values_for_filter(model, fname):
        try:
            field = model._meta.get_field(fname)
            if field.choices:
                return [{'value': v, 'display': d} for v, d in field.choices]
        except Exception:
            pass
        try:
            qs = model.objects.order_by(fname).values_list(fname, flat=True).distinct()
            return [{'value': v, 'display': str(v)} for v in qs if v not in (None, '')]
        except Exception:
            return []


    def get_model_meta(model):
        model_admin = django_admin.site._registry.get(model)
        meta = model._meta

        raw_display = list(getattr(model_admin, 'list_display', None) or ['__str__'])
        list_display = [{'name': n, 'label': _field_verbose(model, n)} for n in raw_display]

        search_fields = list(getattr(model_admin, 'search_fields', None) or [])

        list_filter = []
        for entry in (getattr(model_admin, 'list_filter', None) or []):
            if not isinstance(entry, str):
                continue
            try:
                field = meta.get_field(entry)
                label = getattr(field, 'verbose_name', entry).title()
            except Exception:
                label = entry.replace('_', ' ').title()
            list_filter.append({
                'name': entry,
                'label': label,
                'choices': _distinct_values_for_filter(model, entry),
            })

        ordering = list(getattr(model_admin, 'ordering', None) or ['-pk'])

        action_list = []
        for entry in (getattr(model_admin, 'actions', None) or []):
            func = entry if callable(entry) else getattr(model_admin, entry, None)
            if func is None:
                continue
            action_list.append({
                'name': func.__name__,
                'label': getattr(func, 'short_description', func.__name__.replace('_', ' ').title()),
                'confirm': getattr(func, 'requires_confirmation', False),
                '_func': func,
            })

        return {
            'model_name':      meta.model_name,
            'verbose_name':    meta.verbose_name.title(),
            'verbose_name_pl': meta.verbose_name_plural.title(),
            'app_label':       meta.app_label,
            'fields':          list(meta.fields),
            'list_display':    list_display,
            'search_fields':   search_fields,
            'list_filter':     list_filter,
            'ordering':        ordering,
            'actions':         action_list,
            'is_registered':   model_admin is not None,
        }


    def get_all_meta():
        result = {}
        for model in sorted(apps.get_models(), key=lambda m: m._meta.verbose_name.lower()):
            result[model._meta.model_name] = get_model_meta(model)
        return result


    def resolve_display_value(obj, field_name):
        parts = field_name.split('__')
        value = obj
        for part in parts:
            if value is None:
                return '—'
            try:
                value = getattr(value, part, None)
                if callable(value):
                    value = value()
            except Exception:
                return '—'
        if value is None or value == '':
            return '—'
        if isinstance(value, bool):
            return '✓' if value else '✗'
        return str(value)
''')

# ─────────────────────────────────────────────────────────────────────────────
# 4. critix/admin.py
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(CRITIX, 'admin.py'), '''
    from django.contrib import admin
    from .models import (
        Movie, Review, ReviewLike, ReviewReply,
        ReviewReport, ReportAction, Notification, Watchlist, Watched,
    )

    def _mark_resolved(ma, request, qs):
        qs.update(is_resolved=True)
    _mark_resolved.short_description = "Mark selected reports as resolved"
    _mark_resolved.requires_confirmation = False

    def _mark_unresolved(ma, request, qs):
        qs.update(is_resolved=False)
    _mark_unresolved.short_description = "Mark selected reports as unresolved"
    _mark_unresolved.requires_confirmation = False

    def _activate_users(ma, request, qs):
        qs.update(is_active=True)
    _activate_users.short_description = "Activate selected users"
    _activate_users.requires_confirmation = True

    def _deactivate_users(ma, request, qs):
        qs.update(is_active=False)
    _deactivate_users.short_description = "Deactivate selected users"
    _deactivate_users.requires_confirmation = True

    def _mark_notif_read(ma, request, qs):
        qs.update(is_read=True)
    _mark_notif_read.short_description = "Mark selected notifications as read"
    _mark_notif_read.requires_confirmation = False

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
        actions       = [_mark_notif_read]

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
''')

# ─────────────────────────────────────────────────────────────────────────────
# 5. critix/admin_views.py
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(CRITIX, 'admin_views.py'), '''
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import admin as django_admin
    from django.db.models import Q
    from django.apps import apps
    from django.http import Http404, JsonResponse
    from django.urls import reverse
    from django.forms import modelform_factory
    from django.views.decorators.http import require_POST
    from .models import Movie
    from . import admin_metadata

    APP_ICONS = {
        "critix": "🎬", "auth": "🔐", "admin": "🛠️",
        "contenttypes": "🧩", "sessions": "🗄️",
    }

    def admin_required(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if not request.user.is_staff:
                return redirect("home")
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper

    def _list_url_for(model):
        return reverse("admin_model_list", kwargs={"model_name": model._meta.model_name})

    def _add_url_for(model):
        if not _editable_fields(model):
            return None
        return reverse("admin_model_add", kwargs={"model_name": model._meta.model_name})

    def get_apps_overview(request=None):
        result = []
        for app_config in apps.get_app_configs():
            app_models = []
            for model in sorted(app_config.get_models(), key=lambda m: m._meta.verbose_name.lower()):
                app_models.append({
                    "label":      model._meta.verbose_name_plural.title(),
                    "model_name": model._meta.model_name,
                    "count":      model.objects.count(),
                    "list_url":   _list_url_for(model),
                    "add_url":    _add_url_for(model),
                })
            result.append({
                "app_label": app_config.label,
                "app_name":  app_config.verbose_name,
                "app_icon":  APP_ICONS.get(app_config.label, "📦"),
                "models":    app_models,
                "is_open":   False,
            })
        if request is not None:
            for app in result:
                app["is_open"] = any(
                    m["list_url"] and request.path.startswith(m["list_url"])
                    for m in app["models"]
                )
        return result

    def _all_models():
        return sorted(apps.get_models(), key=lambda m: m._meta.verbose_name.lower())

    def _get_model_by_name(model_name):
        for m in _all_models():
            if m._meta.model_name == model_name.lower():
                return m
        raise Http404(f"No model named {model_name!r}.")

    def _editable_fields(model):
        return [
            f.name for f in model._meta.fields
            if f.editable and not f.primary_key
            and not getattr(f, "auto_now_add", False)
            and not getattr(f, "auto_now", False)
        ]

    @admin_required
    def admin_dashboard(request):
        return render(request, "admin_portal/dashboard.html", {})

    @admin_required
    def admin_metadata_api(request, model_name):
        model = _get_model_by_name(model_name)
        meta  = admin_metadata.get_model_meta(model)
        safe_actions = [
            {"name": a["name"], "label": a["label"], "confirm": a["confirm"]}
            for a in meta["actions"]
        ]
        return JsonResponse({
            "model_name":    meta["model_name"],
            "verbose_name":  meta["verbose_name"],
            "list_display":  meta["list_display"],
            "search_fields": meta["search_fields"],
            "list_filter":   [{"name": f["name"], "label": f["label"]} for f in meta["list_filter"]],
            "ordering":      meta["ordering"],
            "actions":       safe_actions,
        })

    @admin_required
    def admin_model_list(request, model_name):
        model = _get_model_by_name(model_name)
        meta  = admin_metadata.get_model_meta(model)
        qs    = model.objects.all()

        # Search
        query = request.GET.get("q", "").strip()
        if query and meta["search_fields"]:
            q_obj = Q()
            for sf in meta["search_fields"]:
                q_obj |= Q(**{f"{sf}__icontains": query})
            qs = qs.filter(q_obj)

        # Filters
        active_filters = {}
        filter_options = []
        for f in meta["list_filter"]:
            selected = request.GET.get(f["name"], "")
            if selected:
                active_filters[f["name"]] = selected
                try:
                    qs = qs.filter(**{f["name"]: selected})
                except Exception:
                    pass
            filter_options.append({**f, "selected": selected})

        # Sorting
        sort_field = request.GET.get("sort", "")
        sort_dir   = request.GET.get("dir", "asc")
        display_names = [col["name"] for col in meta["list_display"]]
        if sort_field and sort_field in display_names:
            try:
                model._meta.get_field(sort_field)
                qs = qs.order_by(f"-{sort_field}" if sort_dir == "desc" else sort_field)
            except Exception:
                qs = qs.order_by(*meta["ordering"])
        else:
            qs = qs.order_by(*meta["ordering"])

        total_count    = qs.count()
        showing_capped = total_count > 300
        qs = qs[:300]

        rows = []
        for obj in qs:
            cells = [admin_metadata.resolve_display_value(obj, col["name"]) for col in meta["list_display"]]
            rows.append({"pk": obj.pk, "cells": cells})

        actions = [{"name": a["name"], "label": a["label"], "confirm": a["confirm"]} for a in meta["actions"]]

        return render(request, "admin_portal/model_list.html", {
            "model_name":      meta["model_name"],
            "verbose_name":    meta["verbose_name"],
            "verbose_name_pl": meta["verbose_name_pl"],
            "columns":         meta["list_display"],
            "rows":            rows,
            "total_count":     total_count,
            "showing_capped":  showing_capped,
            "filter_options":  filter_options,
            "actions":         actions,
            "has_search":      bool(meta["search_fields"]),
            "can_add":         bool(_editable_fields(model)),
            "query":           query,
            "sort_field":      sort_field,
            "sort_dir":        sort_dir,
            "active_filters":  active_filters,
        })

    @admin_required
    @require_POST
    def admin_model_action(request, model_name):
        model        = _get_model_by_name(model_name)
        meta         = admin_metadata.get_model_meta(model)
        action_name  = request.POST.get("action", "")
        selected_raw = request.POST.get("selected_ids", "")
        action_entry = next((a for a in meta["actions"] if a["name"] == action_name), None)
        if not action_entry:
            return redirect("admin_model_list", model_name=model_name)
        qs = model.objects.all() if selected_raw == "all" else \
             model.objects.filter(pk__in=[p.strip() for p in selected_raw.split(",") if p.strip()])
        if qs.exists():
            result = action_entry["_func"](django_admin.site._registry.get(model), request, qs)
            if result is not None:
                return result
        return redirect("admin_model_list", model_name=model_name)

    @admin_required
    def admin_model_add(request, model_name):
        model     = _get_model_by_name(model_name)
        FormClass = modelform_factory(model, fields=_editable_fields(model))
        if request.method == "POST":
            form = FormClass(request.POST, request.FILES)
            if form.is_valid():
                form.save()
                return redirect("admin_model_list", model_name=model_name)
        else:
            form = FormClass()
        meta = admin_metadata.get_model_meta(model)
        return render(request, "admin_portal/model_form.html", {
            "form": form, "verbose_name": meta["verbose_name"],
            "model_name": model_name, "mode": "add",
        })

    @admin_required
    def admin_model_edit(request, model_name, pk):
        model     = _get_model_by_name(model_name)
        obj       = get_object_or_404(model, pk=pk)
        FormClass = modelform_factory(model, fields=_editable_fields(model))
        if request.method == "POST":
            form = FormClass(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                form.save()
                return redirect("admin_model_list", model_name=model_name)
        else:
            form = FormClass(instance=obj)
        meta = admin_metadata.get_model_meta(model)
        return render(request, "admin_portal/model_form.html", {
            "form": form, "verbose_name": meta["verbose_name"],
            "model_name": model_name, "mode": "edit", "pk": pk,
        })

    @admin_required
    @require_POST
    def admin_model_delete(request, model_name, pk):
        model = _get_model_by_name(model_name)
        get_object_or_404(model, pk=pk).delete()
        return redirect("admin_model_list", model_name=model_name)

    # ── Genres (curated; not a real model) ───────────────────────────────────

    @admin_required
    def admin_genres(request):
        genre_map = {}
        for raw in Movie.objects.values_list("genre", flat=True):
            for g in [x.strip() for x in raw.replace(",", "/").split("/") if x.strip()]:
                genre_map[g] = genre_map.get(g, 0) + 1
        return render(request, "admin_portal/genres.html", {
            "genres":  sorted(genre_map.items(), key=lambda x: -x[1]),
            "success": request.session.pop("genre_success", None),
            "error":   request.session.pop("genre_error", None),
        })

    @admin_required
    def admin_genre_rename(request):
        if request.method == "POST":
            old_name = request.POST.get("old_name", "").strip()
            new_name = request.POST.get("new_name", "").strip()
            if not new_name:
                request.session["genre_error"] = "New genre name cannot be empty."
                return redirect("admin_genres")
            updated = 0
            for movie in Movie.objects.all():
                genres = [g.strip() for g in movie.genre.replace(",", "/").split("/")]
                if old_name in genres:
                    movie.genre = " / ".join(new_name if g == old_name else g for g in genres)
                    movie.save()
                    updated += 1
            request.session["genre_success"] = f\'Renamed "{old_name}" → "{new_name}" on {updated} movie(s).\'
        return redirect("admin_genres")

    @admin_required
    def admin_genre_delete(request):
        if request.method == "POST":
            genre_name = request.POST.get("genre_name", "").strip()
            updated = 0
            for movie in Movie.objects.all():
                genres = [g.strip() for g in movie.genre.replace(",", "/").split("/")]
                if genre_name in genres:
                    genres = [g for g in genres if g != genre_name]
                    movie.genre = " / ".join(genres) if genres else "Uncategorized"
                    movie.save()
                    updated += 1
            request.session["genre_success"] = f\'Removed genre "{genre_name}" from {updated} movie(s).\'
        return redirect("admin_genres")
''')

# ─────────────────────────────────────────────────────────────────────────────
# 6. critix/context_processors.py
# ─────────────────────────────────────────────────────────────────────────────
w(os.path.join(CRITIX, 'context_processors.py'), '''
    from .models import Watchlist, Movie

    def global_navbar_data(request):
        count = 0
        if request.user.is_authenticated:
            count = Watchlist.objects.filter(user=request.user).count()
        raw_genres = Movie.objects.values_list("genre", flat=True).distinct()
        unique_genres = set()
        for raw_g in raw_genres:
            if raw_g:
                unique_genres.update(g.strip() for g in raw_g.split("/"))
        return {"navbar_watchlist_count": count, "all_genres": sorted(unique_genres)}

    def admin_sidebar_models(request):
        if not request.path.startswith("/admin/"):
            return {}
        from .admin_views import get_apps_overview
        return {"apps_overview": get_apps_overview(request)}
''')

# ─────────────────────────────────────────────────────────────────────────────
# 7. Templates
# ─────────────────────────────────────────────────────────────────────────────

w(os.path.join(TMPL, 'dashboard.html'), '''
    {% extends "admin_portal/base.html" %}
    {% block page_title %}Dashboard{% endblock %}
    {% block breadcrumb %}Home / Dashboard{% endblock %}
    {% block content %}
    <style>
    .app-card{background:#16213e;border:1px solid #253351;border-radius:12px;margin-bottom:24px;overflow:hidden}
    .app-card-header{padding:16px 20px;border-bottom:1px solid #253351;font-size:1.1rem;font-weight:700;display:flex;align-items:center;gap:10px}
    .app-model-row{display:flex;justify-content:space-between;align-items:center;padding:13px 20px;border-bottom:1px solid #253351;gap:16px;transition:background .15s}
    .app-model-row:last-child{border-bottom:none}
    .app-model-row:hover{background:rgba(233,69,96,.04)}
    .app-model-link{color:#5b8dee;text-decoration:none;font-size:.95rem;font-weight:500;display:flex;align-items:center;gap:10px}
    .app-model-link:hover{text-decoration:underline}
    .app-model-count{background:#253351;color:#aab4c8;font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:10px;min-width:22px;text-align:center}
    .app-model-actions{display:flex;gap:8px;flex-shrink:0}
    </style>
    {% for app in apps_overview %}
    <div class="app-card">
      <div class="app-card-header"><span>{{ app.app_icon }}</span>{{ app.app_name }}</div>
      {% for m in app.models %}
      <div class="app-model-row">
        <a href="{{ m.list_url }}" class="app-model-link">{{ m.label }}<span class="app-model-count">{{ m.count }}</span></a>
        <div class="app-model-actions">
          {% if m.add_url %}<a href="{{ m.add_url }}" class="btn btn-primary btn-sm">➕ Add</a>{% endif %}
          <a href="{{ m.list_url }}" class="btn btn-secondary btn-sm">📋 View</a>
        </div>
      </div>
      {% empty %}<div style="padding:16px 20px;color:#8892a4;font-size:.9rem">No models found.</div>
      {% endfor %}
    </div>
    {% endfor %}
    {% endblock %}
''')

w(os.path.join(TMPL, 'model_list.html'), '''
    {% extends "admin_portal/base.html" %}
    {% block page_title %}{{ verbose_name_pl }}{% endblock %}
    {% block breadcrumb %}Admin / {{ verbose_name_pl }}{% endblock %}
    {% block content %}

    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;gap:12px;flex-wrap:wrap">
      <div>
        <h2 style="font-size:1.4rem;margin-bottom:4px">{{ verbose_name_pl }}</h2>
        <span style="font-size:.85rem;color:#8892a4">
          {% if showing_capped %}Showing 300 of {{ total_count }} records{% else %}{{ total_count }} record{{ total_count|pluralize }}{% endif %}
        </span>
      </div>
      {% if can_add %}
      <a href="{% url "admin_model_add" model_name %}" class="btn btn-primary">➕ Add {{ verbose_name }}</a>
      {% endif %}
    </div>

    {% if has_search or filter_options %}
    <form method="GET" id="filterForm" style="background:#16213e;border:1px solid #253351;border-radius:10px;padding:16px 20px;margin-bottom:20px;display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end">
      {% if has_search %}
      <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:200px">
        <label style="font-size:.75rem;color:#8892a4;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Search</label>
        <input type="text" name="q" value="{{ query }}" placeholder="Search {{ verbose_name_pl|lower }}…" class="form-input">
      </div>
      {% endif %}
      {% for f in filter_options %}
      <div style="display:flex;flex-direction:column;gap:4px;min-width:160px">
        <label style="font-size:.75rem;color:#8892a4;font-weight:600;text-transform:uppercase;letter-spacing:.5px">{{ f.label }}</label>
        <select name="{{ f.name }}" onchange="this.form.submit()" class="form-input" style="padding:10px 12px">
          <option value="">All {{ f.label }}</option>
          {% for choice in f.choices %}
          <option value="{{ choice.value }}" {% if f.selected == choice.value|stringformat:"s" %}selected{% endif %}>{{ choice.display }}</option>
          {% endfor %}
        </select>
      </div>
      {% endfor %}
      <div style="display:flex;gap:8px;align-self:flex-end">
        <button type="submit" class="btn btn-secondary">Apply</button>
        {% if query or active_filters %}
        <a href="{% url "admin_model_list" model_name %}" class="btn btn-sm" style="background:#253351;color:#d0d7e3;padding:10px 14px">✕ Clear</a>
        {% endif %}
      </div>
      {% if sort_field %}<input type="hidden" name="sort" value="{{ sort_field }}">{% endif %}
      {% if sort_dir %}<input type="hidden" name="dir" value="{{ sort_dir }}">{% endif %}
    </form>
    {% endif %}

    {% if actions %}
    <form method="POST" action="{% url "admin_model_action" model_name %}" id="actionForm" style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      {% csrf_token %}
      <input type="hidden" name="selected_ids" id="selectedIdsInput" value="">
      <select name="action" class="form-input" style="width:auto;min-width:260px;padding:8px 12px">
        <option value="">── Select an action ──</option>
        {% for action in actions %}
        <option value="{{ action.name }}" data-confirm="{{ action.confirm|yesno:"true,false" }}">{{ action.label }}</option>
        {% endfor %}
      </select>
      <button type="button" onclick="submitAction()" class="btn btn-secondary">▶ Go</button>
      <span id="selectionCount" style="color:#8892a4;font-size:.85rem;display:none">0 selected</span>
    </form>
    {% endif %}

    {% if showing_capped %}
    <div style="background:rgba(255,193,7,.1);border:1px solid rgba(255,193,7,.3);color:#ffc107;padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:.875rem">
      ⚠️ Showing the 300 most recent rows of {{ total_count }} total.
    </div>
    {% endif %}

    <div class="table-container" style="overflow-x:auto">
      <table style="min-width:600px">
        <thead><tr>
          {% if actions %}<th style="width:40px;text-align:center"><input type="checkbox" id="selectAll" style="accent-color:#e94560;cursor:pointer" onchange="toggleAll(this)"></th>{% endif %}
          {% for col in columns %}
          <th>
            <a href="?{% if query %}q={{ query }}&{% endif %}{% for f in filter_options %}{% if f.selected %}{{ f.name }}={{ f.selected }}&{% endif %}{% endfor %}sort={{ col.name }}&dir={% if sort_field == col.name and sort_dir == "asc" %}desc{% else %}asc{% endif %}" style="color:inherit;text-decoration:none;display:flex;align-items:center;gap:6px">
              {{ col.label }}
              {% if sort_field == col.name %}{% if sort_dir == "asc" %}↑{% else %}↓{% endif %}{% else %}<span style="color:#4a556a">⇅</span>{% endif %}
            </a>
          </th>
          {% endfor %}
          <th style="text-align:right">Actions</th>
        </tr></thead>
        <tbody>
          {% for row in rows %}
          <tr class="data-row">
            {% if actions %}<td style="text-align:center"><input type="checkbox" class="row-check" value="{{ row.pk }}" style="accent-color:#e94560;cursor:pointer" onchange="updateSelection()"></td>{% endif %}
            {% for cell in row.cells %}
            <td>{% if cell == "✓" %}<span style="color:#22c55e">✓</span>{% elif cell == "✗" %}<span style="color:#ef4444">✗</span>{% else %}<span title="{{ cell }}">{% if cell|length > 80 %}{{ cell|slice:":80" }}…{% else %}{{ cell }}{% endif %}</span>{% endif %}</td>
            {% endfor %}
            <td style="text-align:right;white-space:nowrap">
              <a href="{% url "admin_model_edit" model_name row.pk %}" class="btn btn-secondary btn-sm">✏️ Edit</a>
              <form method="POST" action="{% url "admin_model_delete" model_name row.pk %}" style="display:inline" onsubmit="return confirm(\'Delete this {{ verbose_name }}?\')">
                {% csrf_token %}<button type="submit" class="btn btn-danger btn-sm" style="margin-left:6px">🗑 Delete</button>
              </form>
            </td>
          </tr>
          {% empty %}
          <tr><td colspan="{{ columns|length|add:2 }}" style="text-align:center;padding:48px 16px;color:#8892a4">
            {% if query or active_filters %}No {{ verbose_name_pl|lower }} match your search / filters.<br>
            <a href="{% url "admin_model_list" model_name %}" style="color:#5b8dee;text-decoration:none;margin-top:8px;display:inline-block">Clear filters →</a>
            {% else %}No {{ verbose_name_pl|lower }} yet.{% if can_add %}<br>
            <a href="{% url "admin_model_add" model_name %}" style="color:#5b8dee;text-decoration:none;margin-top:8px;display:inline-block">Add the first one →</a>{% endif %}{% endif %}
          </td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    {% if actions %}
    <script>
    function toggleAll(m){document.querySelectorAll(".row-check").forEach(c=>c.checked=m.checked);updateSelection()}
    function updateSelection(){
      const checked=document.querySelectorAll(".row-check:checked");
      const el=document.getElementById("selectionCount");
      el.style.display=checked.length?"inline":"none";
      el.textContent=checked.length+" selected";
      const total=document.querySelectorAll(".row-check").length;
      const master=document.getElementById("selectAll");
      master.indeterminate=checked.length>0&&checked.length<total;
      master.checked=checked.length===total&&total>0;
    }
    function submitAction(){
      const sel=document.querySelector("select[name=action]");
      if(!sel.value){alert("Please select an action first.");return}
      const selected=Array.from(document.querySelectorAll(".row-check:checked")).map(c=>c.value);
      if(!selected.length){alert("Please select at least one row.");return}
      if(sel.selectedOptions[0].dataset.confirm==="true"&&!confirm("Apply \\""+sel.selectedOptions[0].text+"\\" to "+selected.length+" item(s)?"))return;
      document.getElementById("selectedIdsInput").value=selected.join(",");
      document.getElementById("actionForm").submit();
    }
    </script>
    {% endif %}
    {% endblock %}
''')

w(os.path.join(TMPL, 'model_form.html'), '''
    {% extends "admin_portal/base.html" %}
    {% block page_title %}{% if mode == "edit" %}Edit{% else %}Add{% endif %} {{ verbose_name }}{% endblock %}
    {% block breadcrumb %}Admin / <a href="{% url "admin_model_list" model_name %}" style="color:#5b8dee;text-decoration:none">{{ verbose_name }}</a> / {% if mode == "edit" %}Edit{% else %}Add{% endif %}{% endblock %}
    {% block content %}
    <div class="generic-form-wrap" style="max-width:720px">
      <h2 style="font-size:1.4rem;margin-bottom:24px">{% if mode == "edit" %}✏️ Edit {{ verbose_name }}{% else %}➕ Add New {{ verbose_name }}{% endif %}</h2>
      {% if form.non_field_errors %}
      <div style="background:rgba(255,107,107,.1);border:1px solid rgba(255,107,107,.3);color:#ff8080;padding:16px;border-radius:8px;margin-bottom:24px">
        <div style="font-weight:600;margin-bottom:8px">❌ Please fix these errors:</div>
        {% for e in form.non_field_errors %}<div>• {{ e }}</div>{% endfor %}
      </div>
      {% endif %}
      <form method="POST" enctype="multipart/form-data" style="background:#16213e;padding:28px;border-radius:12px;border:1px solid #253351">
        {% csrf_token %}
        {% for field in form %}
        <div class="form-group">
          <label class="form-label" for="{{ field.id_for_label }}">{{ field.label }}{% if field.field.required %} <span style="color:#e94560">*</span>{% endif %}</label>
          {{ field }}
          {% if field.help_text %}<small style="color:#8892a4;font-size:.8rem;display:block;margin-top:6px">{{ field.help_text }}</small>{% endif %}
          {% for e in field.errors %}<div style="color:#ff8080;font-size:.85rem;margin-top:6px">⚠ {{ e }}</div>{% endfor %}
        </div>
        {% endfor %}
        <div style="display:flex;gap:12px;margin-top:32px;padding-top:20px;border-top:1px solid #253351">
          <button type="submit" class="btn btn-primary" style="flex:1;padding:13px">{% if mode == "edit" %}💾 Save Changes{% else %}➕ Add {{ verbose_name }}{% endif %}</button>
          <a href="{% url "admin_model_list" model_name %}" class="btn btn-secondary" style="flex:.4;padding:13px;text-align:center">Cancel</a>
        </div>
      </form>
    </div>
    <style>
    .generic-form-wrap input[type=text],.generic-form-wrap input[type=number],.generic-form-wrap input[type=email],.generic-form-wrap input[type=url],.generic-form-wrap input[type=password],.generic-form-wrap input[type=date],.generic-form-wrap input[type=datetime-local],.generic-form-wrap input[type=file],.generic-form-wrap select,.generic-form-wrap textarea{width:100%;padding:10px 12px;background:#0f3460;border:1px solid #253351;border-radius:6px;color:#fff;font-size:.9rem;outline:none;transition:border-color .2s;font-family:inherit}
    .generic-form-wrap input:focus,.generic-form-wrap select:focus,.generic-form-wrap textarea:focus{border-color:#e94560}
    .generic-form-wrap select option{background:#16213e;color:#fff}
    .generic-form-wrap textarea{min-height:110px;resize:vertical}
    .generic-form-wrap input[type=checkbox]{width:auto;accent-color:#e94560;margin-right:8px}
    .generic-form-wrap input[type=file]{color:#8892a4;cursor:pointer}
    .generic-form-wrap input[type=file]::file-selector-button{background:#5b8dee;color:#fff;border:none;padding:8px 16px;border-radius:6px;font-weight:600;font-size:.85rem;margin-right:12px;cursor:pointer}
    </style>
    {% endblock %}
''')

# ─────────────────────────────────────────────────────────────────────────────
# Verify
# ─────────────────────────────────────────────────────────────────────────────
print('\n=== Verifying no old URL names remain ===\n')
old_names = ['admin_movies', 'admin_reviews', 'admin_users', 'admin_reports',
             'admin_notifications', 'admin_model_detail', 'admin_models_list',
             'CUSTOM_ADMIN_PAGES']
all_ok = True
check_files = [
    os.path.join(CRITIX, 'admin_views.py'),
    os.path.join(CRITIX, 'admin_urls.py'),
    os.path.join(CRITIX, 'context_processors.py'),
    os.path.join(TMPL, 'dashboard.html'),
    os.path.join(TMPL, 'model_list.html'),
    os.path.join(TMPL, 'model_form.html'),
]
for filepath in check_files:
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    hits = [name for name in old_names if name in content]
    if hits:
        print(f'  ⚠  {os.path.relpath(filepath, BASE)} still contains: {hits}')
        all_ok = False

if all_ok:
    print('  ✓  All clean — no old URL names found.')

print('\n=== Done. Restart your dev server. ===\n')