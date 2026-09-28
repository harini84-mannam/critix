from django.contrib import admin as django_admin
from django.apps import apps


def _bulk_delete(modeladmin, request, queryset):
    queryset.delete()

_bulk_delete.short_description = "Delete selected records"
_bulk_delete.requires_confirmation = True

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


def _get_choices_for_field(model, fname):
    try:
        field = model._meta.get_field(fname)
        return list(field.choices or [])
    except Exception:
        return []


def _distinct_values_for_filter(model_admin, model, fname):
    
    choices = _get_choices_for_field(model, fname)
    if choices:
        return [{'value': v, 'display': d} for v, d in choices]
    try:
        qs = model.objects.order_by(fname).values_list(fname, flat=True).distinct()
        return [{'value': v, 'display': str(v)} for v in qs if v not in (None, '')]
    except Exception:
        return []

def get_model_meta(model):
   
    model_admin = django_admin.site._registry.get(model)
    meta = model._meta

    if model_admin and getattr(model_admin, 'list_display', None):
        raw_display = list(model_admin.list_display)
    else:
        raw_display = [f.name for f in meta.fields if not f.primary_key][:4] or ['__str__']
    list_display = []
    for name in raw_display:
        label = _field_verbose(model, name)
        list_display.append({'name': name, 'label': label})
    search_fields = list(getattr(model_admin, 'search_fields', None) or [])
    raw_filter = list(getattr(model_admin, 'list_filter', None) or [])
    list_filter = []
    for entry in raw_filter:
        if not isinstance(entry, str):
            continue
        try:
            field = meta.get_field(entry)
            label = getattr(field, 'verbose_name', entry).title()
        except Exception:
            label = entry.replace('_', ' ').title()
        choices = _distinct_values_for_filter(model_admin, model, entry)
        list_filter.append({'name': entry, 'label': label, 'choices': choices})

    ordering = list(getattr(model_admin, 'ordering', None) or ['-pk'])
    action_list = []
    seen_actions = set()

    def _add_action(func):
        if func is None or func.__name__ in seen_actions:
            return
        seen_actions.add(func.__name__)
        action_list.append({
            'name':    func.__name__,
            'label':   getattr(func, 'short_description', func.__name__.replace('_', ' ').title()),
            'confirm': getattr(func, 'requires_confirmation', False),
            '_func':   func,
        })

    for entry in (getattr(model_admin, 'actions', None) or []):
        if callable(entry):
            _add_action(entry)
        elif isinstance(entry, str) and hasattr(model_admin, entry):
            _add_action(getattr(model_admin, entry))

    _add_action(_bulk_delete)

    return {
        'model_name':     meta.model_name,
        'verbose_name':   meta.verbose_name.title(),
        'verbose_name_pl': meta.verbose_name_plural.title(),
        'app_label':      meta.app_label,
        'fields':         list(meta.fields),
        'list_display':   list_display,
        'search_fields':  search_fields,
        'list_filter':    list_filter,
        'ordering':       ordering,
        'actions':        action_list,
        'is_registered':  model_admin is not None,
    }


def get_all_meta():
    result = {}
    for model in sorted(apps.get_models(), key=lambda m: m._meta.verbose_name.lower()):
        key = model._meta.model_name
        result[key] = get_model_meta(model)
    return result


def resolve_display_value(obj, field_name):
   
    if field_name == '__str__':
        try:
            return str(obj)
        except Exception:
            return '—'

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