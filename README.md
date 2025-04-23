# Media Index Backend
The media_index project is a backend service for collecting and analyzing linguistic data from various media sources, with an initial focus on TMDB movies and OpenSubtitles integration. The project is in early development and aims to expand its capabilities to include more media types and enhance linguistic analysis.

### Main Function Points
- Integrates with TMDB (The Movie Database) to collect and process movie data
- Plans to add integration with OpenSubtitles for subtitle data
- Provides linguistic analysis of the collected data
- Allows for running background jobs to sync and process media data

### Technology Stack
- Python
- Django, Django-Ninja and Pydantic
- Redis and Django-rq (for background tasks)
- Docker (for containerization)

## Quick Start

```bash
# Setup environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest
```

## Project Structure

```
media_index/
├── TMDB/                   # TMDB integration
|-- language_analysis/      # Linguistic processing
|-- subtitles/
└── tests/                  # Test suite
```

## Current Features

### Running Tests

```bash
# All tests
python -m pytest

# With logging
python -m pytest -v
```

### Contributing

1. Ensure tests pass
2. Add tests for new features
3. Follow existing code style (black, mypy)
4. Update documentation

## Notes

- Still in early development
- API endpoints subject to change


## Running/triggering background jobs

Set API key:
```bash
export TMDB_API_KEY="your_api_key_here"
```

## Run Worker

```bash
python manage.py rqworker tmdb_sync
```

## Queue Jobs

### Command Line

Single year:
```bash
# English movies from 2023
# Test run (100 movies max)
python manage.py sync_tmdb --year 2023

# Custom limit
python manage.py sync_tmdb --year 2023 --max-results 50

# No limit
python manage.py sync_tmdb --year 2023 --max-results 0

```
Year range:
```bash
# English movies: 2023, 2022, 2021, 2020
python manage.py sync_tmdb --start-year 2020 --end-year 2023

# Custom limit (still newest to oldest)
python manage.py sync_tmdb --start-year 2020 --end-year 2023 --max-results 50
```

# Testing
Integration tests require TMDB_API_KEY set in the background to work.


## Next Steps

- Complete TMDB integration
- Add OpenSubtitles crawler
- Expand linguistic analysis
- Add more media types
