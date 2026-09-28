from datetime import date

from django.core.management.base import BaseCommand, CommandError

from critix.models import Movie
from critix.services.tmdb import (
    TmdbError,
    check_connection,
    discover_count,
    import_movie,
    iter_discover,
)


class Command(BaseCommand):
    help = (
        "Bulk-import Telugu films (poster, genres, trailer, cast) from TMDB into the existing "
        "Movie / MovieCast / MovieMedia models. Safe to stop (Ctrl+C) and re-run: films that are "
        "already in the database are skipped, and existing movies are never overwritten."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from-year", type=int, default=1931, help="First release year (default 1931)")
        parser.add_argument("--to-year", type=int, default=date.today().year, help="Last release year (default: this year)")
        parser.add_argument("--min-votes", type=int, default=5,
                            help="Skip films with fewer TMDB votes; filters out obscure entries (default 5, use 0 for everything)")
        parser.add_argument("--limit", type=int, default=0, help="Stop after creating this many new movies (default: no limit)")
        parser.add_argument("--cast-limit", type=int, default=10, help="Cast members to store per movie (default 10)")
        parser.add_argument("--dry-run", action="store_true", help="Only count how many films match, per year. Writes nothing.")
        parser.add_argument("--include-no-poster", action="store_true", help="Also import films that have no poster on TMDB")
        parser.add_argument("--latin-titles-only", action="store_true",
                            help="Skip films whose TMDB title is in Telugu script")

    def handle(self, *args, **opts):
        from_year, to_year = opts["from_year"], opts["to_year"]
        if from_year > to_year:
            raise CommandError("--from-year must not be greater than --to-year.")

        ok, message = check_connection()
        if not ok:
            raise CommandError(message)

        if opts["dry_run"]:
            return self._dry_run(from_year, to_year, opts["min_votes"])

        known = set(Movie.objects.exclude(tmdb_id=None).values_list("tmdb_id", flat=True))
        local_candidates = list(Movie.objects.filter(tmdb_id__isnull=True))
        counts = {"created": 0, "linked": 0, "already": 0, "skipped": 0, "failed": 0}
        current_year, stopped = None, ""

        try:
            for year, item in iter_discover(from_year, to_year, opts["min_votes"]):
                if year != current_year:
                    current_year = year
                    self.stdout.write(self.style.MIGRATE_HEADING(f"== {year} =="))
                tmdb_id = item.get("id")
                if not tmdb_id or tmdb_id in known:
                    counts["already"] += 1
                    continue
                try:
                    result = import_movie(
                        tmdb_id,
                        max_cast=opts["cast_limit"],
                        require_poster=not opts["include_no_poster"],
                        latin_titles_only=opts["latin_titles_only"],
                        local_candidates=local_candidates,
                    )
                except Exception as exc:  # one bad film must not stop the whole import
                    counts["failed"] += 1
                    self.stdout.write(self.style.ERROR(f"Error:   {item.get('title')} ({exc})"))
                    continue

                label = f"{item.get('title')} ({year})"
                if result.status in ("created", "linked"):
                    known.add(tmdb_id)
                    counts[result.status] += 1
                    trailer = "trailer" if result.trailer_added else "no new trailer"
                    verb = "Imported" if result.status == "created" else "Linked "
                    self.stdout.write(self.style.SUCCESS(f"{verb}: {label} - {result.cast_added} cast, {trailer}"))
                elif result.status == "failed":
                    counts["failed"] += 1
                    self.stdout.write(self.style.ERROR(f"Failed:  {label} - {result.reason} (re-run to retry)"))
                else:
                    counts["skipped"] += 1
                    self.stdout.write(self.style.WARNING(f"Skipped: {label} - {result.reason}"))

                if opts["limit"] and counts["created"] >= opts["limit"]:
                    stopped = f"Reached --limit {opts['limit']}."
                    break
        except TmdbError as exc:
            stopped = f"Stopped early: {exc}. Re-run the same command to resume."
        except KeyboardInterrupt:
            stopped = "Interrupted. Re-run the same command to resume."

        if stopped:
            self.stdout.write(self.style.WARNING(stopped))
        self.stdout.write(self.style.SUCCESS(
            f"Done: {counts['created']} created, {counts['linked']} linked to existing, "
            f"{counts['already']} already in database, {counts['skipped']} skipped, {counts['failed']} failed."
        ))

    def _dry_run(self, from_year, to_year, min_votes):
        total = 0
        try:
            for year in range(from_year, to_year + 1):
                count = discover_count(year, min_votes)
                total += count
                if count:
                    self.stdout.write(f"{year}: {count}")
        except TmdbError as exc:
            raise CommandError(str(exc))
        already = Movie.objects.exclude(tmdb_id=None).count()
        self.stdout.write(self.style.SUCCESS(
            f"{total} Telugu film(s) match on TMDB ({already} already imported/synced here). Nothing was written."
        ))
