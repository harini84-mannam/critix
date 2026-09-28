from django.core.management.base import BaseCommand, CommandError

from critix.models import Movie
from critix.services.tmdb import check_connection, sync_watch_providers


class Command(BaseCommand):
    help = (
        "Fetch 'where to watch' streaming/rent/buy providers from TMDB (sourced from JustWatch) "
        "into Movie.watch_providers. Skips movies that already have providers unless --force is used."
    )

    def add_arguments(self, parser):
        parser.add_argument("movie_id", nargs="?", type=int, help="Only sync this Movie primary key")
        parser.add_argument("--all", action="store_true", dest="sync_all", help="Sync every existing movie")
        parser.add_argument("--region", default=None, help="Two-letter region code, e.g. IN, US (default: TMDB_WATCH_REGION setting)")
        parser.add_argument("--force", action="store_true", help="Re-fetch even if watch_providers is already set")

    def handle(self, *args, **options):
        movie_id = options.get("movie_id")
        if movie_id and options.get("sync_all"):
            raise CommandError("Use either a movie_id or --all, not both.")
        if not movie_id and not options.get("sync_all"):
            raise CommandError("Provide a movie_id or use --all.")

        movies = Movie.objects.filter(pk=movie_id) if movie_id else Movie.objects.all().order_by("pk")
        if movie_id and not movies.exists():
            raise CommandError(f"Movie {movie_id} does not exist.")

        ok, message = check_connection()
        if not ok:
            raise CommandError(message)

        total = updated = 0
        for movie in movies.iterator():
            total += 1
            try:
                changed = sync_watch_providers(movie, region=options.get("region"), force=options.get("force"))
            except Exception as exc:  # one bad movie must not stop the whole run
                self.stdout.write(self.style.ERROR(f"Error:   {movie.title} ({exc})"))
                continue
            if changed:
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated: {movie.title}"))
            else:
                self.stdout.write(f"Skipped: {movie.title} (no providers found or already set)")

        self.stdout.write(self.style.SUCCESS(f"\nDone. {updated}/{total} movies updated."))
