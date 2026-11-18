"""Optional Airflow 3 DAG for bounded Mapillary metadata refresh."""

from datetime import UTC, datetime

from airflow.sdk import dag, task


@dag(
    schedule="@daily",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["streetdelta"],
)
def streetdelta_ingest():
    @task
    def refresh_metadata():
        import subprocess
        import sys

        # The mounted volume is shared with downstream processing and survives task retries.
        subprocess.run(
            [sys.executable, "-m", "streetdelta.mapillary", "--out", "runs/mapillary.parquet"],
            check=True,
        )

    refresh_metadata()


streetdelta_ingest()
