from django.core.management.base import BaseCommand
from typing import Optional

from TMDB.tasks import enqueue_year_sync, enqueue_year_range


class Command(BaseCommand):
    help = "Queue TMDB movie syncs"

    def add_arguments(self, parser) -> None:  # type: ignore
        parser.add_argument("--year", type=int, help="Single year to sync")
        parser.add_argument("--start-year", type=int, help="Start year for range")
        parser.add_argument("--end-year", type=int, help="End year for range")
        parser.add_argument("--language", type=str, default="en", help="Language code")
        parser.add_argument(
            "--max-results",
            type=int,
            default=100,
            help="Maximum movies to sync (0 for unlimited)",
        )

    def handle(self, *args, **options) -> None:  # type: ignore
        year: Optional[int] = options["year"]
        start_year: Optional[int] = options["start_year"]
        end_year: Optional[int] = options["end_year"]
        language: str = options["language"]
        max_results: int = options["max_results"]

        def sync_command(max_results: Optional[int]) -> None:
            # hack to make mypy happy
            if max_results == 0:
                max_results = None

        sync_command(max_results)

        if year:
            job_id = enqueue_year_sync(
                year=year, language=language, max_results=max_results
            )
            self.stdout.write(
                self.style.SUCCESS(f"Queued sync job {job_id} for year {year}")
            )

        elif start_year and end_year:
            job_ids = enqueue_year_range(
                start_year=start_year,
                end_year=end_year,
                language=language,
                max_results=max_results,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {len(job_ids)} sync jobs for years {start_year}-{end_year}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Please specify either --year or both --start-year and --end-year"
                )
            )
