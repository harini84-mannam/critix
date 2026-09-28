from django.core.management.base import BaseCommand, CommandError

from critix.models import Movie
from critix.services.tmdb import check_connection, sync_movie_metadata


class Command(BaseCommand):
    help = (
        "Fetch TMDB cast and trailer into the existing Movie / MovieCast / MovieMedia "
        "records. Existing cast and trailers are never overwritten, so it is safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("movie_id", nargs="?", type=int, help="Only sync this Movie primary key")
        parser.add_argument("--all", action="store_true", dest="sync_all", help="Sync every existing movie")
        parser.add_argument(
            "--tmdb-id", type=int, dest="tmdb_id",
            help="Pin the TMDB movie id (use with a movie_id when title matching fails)",
        )

    def handle(self, *args, **options):
        movie_id = options.get("movie_id")
        tmdb_id = options.get("tmdb_id")
        if movie_id and options.get("sync_all"):
            raise CommandError("Use either a movie_id or --all, not both.")
        if not movie_id and not options.get("sync_all"):
            raise CommandError("Provide a movie_id or use --all.")
        if tmdb_id and not movie_id:
            raise CommandError("--tmdb-id needs a single movie_id.")

        movies = Movie.objects.filter(pk=movie_id) if movie_id else Movie.objects.all().order_by("pk")
        if movie_id and not movies.exists():
            raise CommandError(f"Movie {movie_id} does not exist.")

        ok, message = check_connection()
        if not ok:
            raise CommandError(message)

        total = matched = 0
        for movie in movies.iterator():
            total += 1
            try:
                result = sync_movie_metadata(movie, tmdb_id=tmdb_id)
            except Exception as exc:  # one bad movie must not stop the whole backfill
                self.stdout.write(self.style.ERROR(f"Error:   {movie.title} ({exc})"))
                continue
            if result:
                matched += 1
                parts = [f"{result.cast_added} cast added"]
                parts.append("trailer added" if result.trailer_added else "trailer kept/none")
                self.stdout.write(self.style.SUCCESS(f"Synced:  {movie.title} - " + ", ".join(parts)))
            else:
                self.stdout.write(self.style.WARNING(f"Skipped: {movie.title} - {result.reason}"))

        self.stdout.write(self.style.SUCCESS(f"Finished: {matched}/{total} movie(s) matched on TMDB."))