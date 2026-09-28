from datetime import date

from django.core.management.base import BaseCommand, CommandError

from critix.models import UpcomingRelease
from critix.services.tmdb import check_connection, fetch_trailer_url, fetch_upcoming_releases


class Command(BaseCommand):
    help = (
        "Refresh the home page 'Coming Soon' row with upcoming Telugu releases from TMDB. "
        "Safe to re-run - existing rows are updated in place, and past-dated releases are removed. "
        "Run this on a schedule (e.g. a weekly cron job or Task Scheduler task) to keep it current: "
        "python manage.py sync_upcoming_releases"
    )

    def add_arguments(self, parser):
        parser.add_argument("--language", default="te", help="TMDB original-language code (default: te = Telugu)")
        parser.add_argument("--region", default=None, help="Two-letter region code (default: TMDB_WATCH_REGION setting)")
        parser.add_argument("--limit", type=int, default=12, help="Max upcoming titles to keep (default 12)")
        parser.add_argument("--with-trailers", action="store_true", help="Also fetch a trailer link per title (slower, one extra request each)")

    def handle(self, *args, **options):
        ok, message = check_connection()
        if not ok:
            raise CommandError(message)

        rows = fetch_upcoming_releases(
            original_language=options["language"],
            region=options.get("region"),
            max_results=options["limit"],
        )
        if not rows:
            self.stdout.write(self.style.WARNING("TMDB returned no upcoming titles for these filters."))
            return

        seen_ids = []
        created = updated = 0
        for row in rows:
            trailer_url = ""
            if options["with_trailers"]:
                try:
                    trailer_url = fetch_trailer_url(row["tmdb_id"])
                except Exception:
                    trailer_url = ""

            obj, was_created = UpcomingRelease.objects.update_or_create(
                tmdb_id=row["tmdb_id"],
                defaults={
                    "title": row["title"],
                    "poster_url": row["poster_url"],
                    "release_date": row["release_date"],
                    "overview": row["overview"],
                    **({"trailer_url": trailer_url} if trailer_url else {}),
                },
            )
            seen_ids.append(obj.pk)
            created += was_created
            updated += not was_created

        # drop anything that's no longer in the current upcoming window (e.g. it already released)
        removed, _ = UpcomingRelease.objects.exclude(pk__in=seen_ids).filter(release_date__lt=date.today()).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created} added, {updated} updated, {removed} past-dated releases removed."
        ))
