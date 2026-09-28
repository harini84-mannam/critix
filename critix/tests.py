import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from critix.models import Movie, MovieCast, MovieMedia
from critix.services import tmdb

TMP_MEDIA = tempfile.mkdtemp()

DETAILS = {
    "id": 111,
    "credits": {"cast": [
        {"name": "Prabhas", "character": "Venkat", "order": 0, "profile_path": "/a.jpg"},
        {"name": "Trisha", "character": "Sailaja", "order": 1, "profile_path": None},
        {"name": "Prabhas", "character": "Duplicate row", "order": 2, "profile_path": "/a.jpg"},
    ]},
    "videos": {"results": [
        {"site": "YouTube", "key": "CLIP1", "type": "Clip", "official": True, "name": "Clip"},
        {"site": "YouTube", "key": "TRL1", "type": "Trailer", "official": True, "name": "Official Trailer"},
    ]},
}
SEARCH = {"results": [{"id": 111, "title": "Varsham", "original_title": "Varsham",
                       "release_date": "2004-01-14", "original_language": "te", "popularity": 5}]}


def fake_get_json(path, **params):
    if path == "/search/movie":
        return SEARCH
    if path == "/movie/111":
        return DETAILS
    return None


@override_settings(TMDB_API_KEY="test-key", MEDIA_ROOT=TMP_MEDIA)
class TmdbSyncTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.movie = Movie.objects.create(title="Varsham", genre="Drama", description="x", release_year=2004)
        patcher = mock.patch.object(tmdb, "_get_json", side_effect=fake_get_json)
        self.get_json = patcher.start()
        self.addCleanup(patcher.stop)
        dl = mock.patch.object(tmdb, "_download_image", side_effect=lambda p, size=None: b"img" if p else None)
        dl.start()
        self.addCleanup(dl.stop)

    def test_fills_cast_and_trailer_for_existing_movie(self):
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertTrue(result)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tmdb_id, 111)
        cast = list(self.movie.cast_members.all())
        self.assertEqual([c.name for c in cast], ["Prabhas", "Trisha"])  # duplicate row dropped
        self.assertTrue(cast[0].photo)
        self.assertFalse(cast[1].photo)  # no profile image -> template's existing fallback
        trailer = self.movie.media_assets.get(media_type="trailer")
        self.assertEqual(trailer.url, "https://www.youtube.com/watch?v=TRL1")

    def test_rerun_creates_no_duplicates(self):
        tmdb.sync_movie_metadata(self.movie)
        tmdb.sync_movie_metadata(self.movie)
        self.assertEqual(MovieCast.objects.filter(movie=self.movie).count(), 2)
        self.assertEqual(MovieMedia.objects.filter(movie=self.movie, media_type="trailer").count(), 1)

    def test_movie_with_cast_and_trailer_is_left_untouched_without_api_calls(self):
        MovieCast.objects.create(movie=self.movie, name="Trisha Krishnan", role="Sailaja")
        MovieMedia.objects.create(movie=self.movie, media_type="trailer", url="https://youtu.be/mine")
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertFalse(result)
        self.get_json.assert_not_called()
        self.assertEqual(MovieCast.objects.filter(movie=self.movie).count(), 1)
        self.assertEqual(self.movie.media_assets.get().url, "https://youtu.be/mine")

    def test_existing_trailer_is_never_overwritten_but_missing_cast_is_added(self):
        MovieMedia.objects.create(movie=self.movie, media_type="trailer", url="https://youtu.be/mine", caption="Mine")
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertEqual(result.cast_added, 2)
        self.assertFalse(result.trailer_added)
        trailer = self.movie.media_assets.get(media_type="trailer")
        self.assertEqual((trailer.url, trailer.caption), ("https://youtu.be/mine", "Mine"))

    def test_no_confident_match_creates_nothing(self):
        self.movie.release_year = 1990  # TMDB hit is 2004 -> different film
        self.movie.save()
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertFalse(result)
        self.assertEqual(MovieCast.objects.count(), 0)
        self.assertIsNone(Movie.objects.get(pk=self.movie.pk).tmdb_id)

    def test_tmdb_id_already_used_by_another_movie_is_skipped(self):
        Movie.objects.create(title="Other", genre="x", description="x", release_year=2004, tmdb_id=111)
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertFalse(result)
        self.assertIn("already belongs", result.reason)
        self.assertEqual(MovieCast.objects.count(), 0)

    def test_api_failure_is_harmless(self):
        self.get_json.side_effect = lambda path, **p: None
        result = tmdb.sync_movie_metadata(self.movie)
        self.assertFalse(result)
        self.assertEqual(MovieCast.objects.count(), 0)
        self.assertEqual(MovieMedia.objects.count(), 0)

    @override_settings(TMDB_API_KEY="", TMDB_ACCESS_TOKEN="")
    def test_no_credentials_skips_quietly(self):
        self.assertFalse(tmdb.sync_movie_metadata(self.movie))
        self.get_json.assert_not_called()

    @override_settings(TMDB_API_KEY="", TMDB_ACCESS_TOKEN="bearer-token")
    def test_access_token_alone_is_enough(self):
        self.assertTrue(tmdb.sync_movie_metadata(self.movie))

    def test_pinning_tmdb_id_skips_title_search(self):
        tmdb.sync_movie_metadata(self.movie, tmdb_id=111)
        paths = [c.args[0] for c in self.get_json.call_args_list]
        self.assertNotIn("/search/movie", paths)

    @override_settings(TMDB_API_KEY="eyJhbGciOiJIUzI1NiJ9.token", TMDB_ACCESS_TOKEN="")
    def test_read_access_token_pasted_into_api_key_is_treated_as_token(self):
        self.assertEqual(tmdb._credentials(), ("", "eyJhbGciOiJIUzI1NiJ9.token"))

    def test_command_stops_with_clear_message_when_tmdb_unreachable(self):
        from django.core.management.base import CommandError
        with mock.patch("critix.management.commands.sync_movie_metadata.check_connection",
                        return_value=(False, "TMDB rejected the credentials (HTTP 401).")):
            with self.assertRaisesMessage(CommandError, "rejected the credentials"):
                call_command("sync_movie_metadata", "--all", stdout=StringIO())
        self.assertEqual(MovieCast.objects.count(), 0)

    def test_management_command_backfills_all_movies(self):
        out = StringIO()
        with mock.patch("critix.management.commands.sync_movie_metadata.check_connection",
                        return_value=(True, "OK")):
            call_command("sync_movie_metadata", "--all", stdout=out)
        self.assertEqual(self.movie.cast_members.count(), 2)
        self.assertIn("1/1", out.getvalue())


IMPORT_DETAILS = {
    "id": 222,
    "title": "Nuvvostanante Nenoddantana",
    "release_date": "2005-05-13",
    "overview": "A story about a family.",
    "poster_path": "/poster.jpg",
    "original_language": "te",
    "genres": [{"id": 18, "name": "Drama"}, {"id": 10749, "name": "Romance"}, {"id": 35, "name": "Comedy"},
               {"id": 28, "name": "Action"}],
    "credits": {"cast": [
        {"name": "Siddharth", "character": "Siddhu", "order": 0, "profile_path": "/s.jpg"},
        {"name": "Trisha", "character": "Sirisha", "order": 1, "profile_path": None},
    ]},
    "videos": {"results": [{"site": "YouTube", "key": "IMP1", "type": "Trailer", "official": True, "name": "Trailer"}]},
}


@override_settings(TMDB_API_KEY="test-key", MEDIA_ROOT=TMP_MEDIA)
class TmdbImportTests(TestCase):
    def setUp(self):
        self.details = dict(IMPORT_DETAILS)
        patcher = mock.patch.object(tmdb, "_get_json", side_effect=lambda path, **p: self.details if path == "/movie/222" else None)
        self.get_json = patcher.start()
        self.addCleanup(patcher.stop)
        dl = mock.patch.object(tmdb, "_download_image", side_effect=lambda p, size=None: b"img" if p else None)
        self.download = dl.start()
        self.addCleanup(dl.stop)

    def test_creates_movie_with_poster_genre_cast_and_trailer(self):
        result = tmdb.import_movie(222)
        self.assertEqual(result.status, "created")
        movie = Movie.objects.get(tmdb_id=222)
        self.assertEqual((movie.title, movie.release_year), ("Nuvvostanante Nenoddantana", 2005))
        self.assertEqual(movie.genre, "Drama/Romance/Comedy")  # site's slash format, max 3
        self.assertTrue(movie.poster)
        self.assertEqual(movie.cast_members.count(), 2)
        self.assertEqual(movie.media_assets.get(media_type="trailer").url, "https://www.youtube.com/watch?v=IMP1")

    def test_second_import_is_skipped_without_duplicates(self):
        tmdb.import_movie(222)
        result = tmdb.import_movie(222)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(MovieCast.objects.count(), 2)

    def test_existing_movie_without_tmdb_id_is_linked_not_duplicated(self):
        mine = Movie.objects.create(title="Nuvvostanante Nenoddantana", genre="Drama", description="x", release_year=2005)
        MovieMedia.objects.create(movie=mine, media_type="trailer", url="https://youtu.be/mine")
        candidates = [mine]
        result = tmdb.import_movie(222, local_candidates=candidates)
        self.assertEqual(result.status, "linked")
        self.assertEqual(Movie.objects.count(), 1)
        mine.refresh_from_db()
        self.assertEqual(mine.tmdb_id, 222)
        self.assertEqual(mine.cast_members.count(), 2)
        self.assertEqual(mine.media_assets.get().url, "https://youtu.be/mine")  # curated trailer kept
        self.assertEqual(candidates, [])

    def test_no_poster_is_skipped_unless_allowed(self):
        self.details = {**IMPORT_DETAILS, "poster_path": None}
        self.assertEqual(tmdb.import_movie(222).status, "skipped")
        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(tmdb.import_movie(222, require_poster=False).status, "created")
        self.assertFalse(Movie.objects.get(tmdb_id=222).poster)

    def test_poster_download_failure_creates_nothing_and_can_be_retried(self):
        self.download.side_effect = lambda p, size=None: None
        result = tmdb.import_movie(222)
        self.assertEqual(result.status, "failed")
        self.assertEqual(Movie.objects.count(), 0)

    def test_missing_release_date_and_api_failure(self):
        self.details = {**IMPORT_DETAILS, "release_date": ""}
        self.assertEqual(tmdb.import_movie(222).status, "skipped")
        self.details = None
        self.assertEqual(tmdb.import_movie(222).status, "failed")
        self.assertEqual(Movie.objects.count(), 0)

    def test_latin_titles_only(self):
        self.details = {**IMPORT_DETAILS, "title": "\u0c30\u0c02\u0c17\u0c38\u0c4d\u0c25\u0c32\u0c02"}
        self.assertEqual(tmdb.import_movie(222, latin_titles_only=True).status, "skipped")

    def test_import_command_skips_known_and_respects_limit(self):
        items = [(2005, {"id": 222, "title": "A"}), (2005, {"id": 999, "title": "B"})]
        Movie.objects.create(title="Known", genre="x", description="x", release_year=2001, tmdb_id=999)
        out = StringIO()
        with mock.patch("critix.management.commands.import_telugu_movies.check_connection", return_value=(True, "OK")), \
             mock.patch("critix.management.commands.import_telugu_movies.iter_discover", return_value=iter(items)):
            call_command("import_telugu_movies", "--from-year", "2005", "--to-year", "2005", stdout=out)
        self.assertTrue(Movie.objects.filter(tmdb_id=222).exists())
        self.assertEqual(Movie.objects.count(), 2)  # 999 was already there, not re-imported
        self.assertIn("1 created", out.getvalue())
        self.assertIn("1 already", out.getvalue())

    def test_dry_run_writes_nothing(self):
        out = StringIO()
        with mock.patch("critix.management.commands.import_telugu_movies.check_connection", return_value=(True, "OK")), \
             mock.patch("critix.management.commands.import_telugu_movies.discover_count", return_value=7):
            call_command("import_telugu_movies", "--from-year", "2005", "--to-year", "2006", "--dry-run", stdout=out)
        self.assertEqual(Movie.objects.count(), 0)
        self.assertIn("14 Telugu film(s)", out.getvalue())


class MovieOfTheDayTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        from datetime import timedelta
        from django.utils import timezone
        for i in range(6):
            Movie.objects.create(title=f"Old {i}", genre="Drama", description="x", release_year=2000 + i, poster="posters/x.jpg")
        Movie.objects.update(created_at=timezone.now() - timedelta(days=2))

    def test_same_movie_all_day_even_after_imports_and_restart(self):
        from django.core.cache import cache
        from critix import views
        first = views._movie_of_the_day_id()
        for i in range(30):  # e.g. a bulk import later the same day
            Movie.objects.create(title=f"New {i}", genre="Drama", description="x", release_year=2020, poster="posters/y.jpg")
        cache.clear()  # simulates a server restart (in-memory cache is lost)
        self.assertEqual(views._movie_of_the_day_id(), first)

    def test_deleted_pick_is_replaced(self):
        from critix import views
        first = views._movie_of_the_day_id()
        Movie.objects.filter(pk=first).delete()
        second = views._movie_of_the_day_id()
        self.assertNotEqual(first, second)
        self.assertTrue(Movie.objects.filter(pk=second).exists())

    def test_no_movies_gives_none(self):
        from critix import views
        Movie.objects.all().delete()
        self.assertIsNone(views._movie_of_the_day_id())


class RatingOnlyReviewTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user("harini", "h@example.com", "pass12345")
        self.movie = Movie.objects.create(title="Varsham", genre="Drama", description="x", release_year=2004)

    def test_form_accepts_rating_without_comment(self):
        from critix.forms import ReviewForm
        for comment in ("", "   "):
            form = ReviewForm(data={"rating": 4, "comment": comment})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["comment"], "")

    def test_rating_still_required(self):
        from critix.forms import ReviewForm
        self.assertFalse(ReviewForm(data={"rating": "", "comment": "great"}).is_valid())

    def test_rating_only_review_is_saved_and_shown_compactly(self):
        from django.urls import reverse
        from critix.models import Review
        self.client.force_login(self.user)
        url = reverse("movie_detail", args=[self.movie.id])
        self.client.post(url, {"rating": 5, "comment": ""})
        review = Review.objects.get(user=self.user, movie=self.movie)
        self.assertEqual((review.rating, review.comment), (5, ""))
        page = self.client.get(url)
        self.assertContains(page, "Rating only")
        self.assertContains(page, "Your rating is saved")
        self.assertContains(page, "Add a written review")  # edit button wording

    def test_written_review_still_shows_full_card(self):
        from django.urls import reverse
        self.client.force_login(self.user)
        url = reverse("movie_detail", args=[self.movie.id])
        self.client.post(url, {"rating": 4, "comment": "Loved the songs"})
        page = self.client.get(url)
        self.assertContains(page, "Loved the songs")
        self.assertNotContains(page, "Rating only")
        self.assertContains(page, "Your review is published")