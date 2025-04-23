build:
	docker compose -f docker-compose.yml up --build -d --remove-orphans

up:
	docker compose -f docker-compose.yml up -d  --remove-orphans	

up-scale-worker:
	docker compose -f docker-compose.yml up -d --remove-orphans --scale rq_worker=2 

down:
	docker compose -f docker-compose.yml down

exec:
	docker compose -f docker-compose.yml	exec -it web /bin/bash

# To check if the env variables has been loaded correctly!
config:
	docker compose -f docker-compose.yml config 

show-logs:
	docker compose -f docker-compose.yml logs

show-logs-api:
	docker compose -f docker-compose.yml logs web

migrations:
	docker compose -f docker-compose.yml run --rm web python manage.py makemigrations

migrate:
	docker compose -f docker-compose.yml run --rm web python manage.py migrate

collectstatic:
	docker compose -f docker-compose.yml run --rm web python manage.py collectstatic --no-input --clear

superuser:
	docker compose -f docker-compose.yml run --rm web python manage.py createsuperuser

down-v:
	docker compose -f docker-compose.yml down -v

volume:
	docker volume inspect local_postgres_data

media-db:
	docker compose -f docker-compose.yml exec postgres psql --username=mediaindexuser --dbname=media-index-db

flake8:
	docker compose -f docker-compose.yml exec web flake8 .

black-check:
	docker compose -f docker-compose.yml exec web black --check --exclude=migrations .

black-diff:
	docker compose -f docker-compose.yml exec web black --diff --exclude=migrations .

black:
	docker compose -f docker-compose.yml exec web black --exclude=migrations .

isort-check:
	docker compose -f docker-compose.yml exec web isort . --check-only --skip venv --skip migrations

isort-diff:
	docker compose -f docker-compose.yml exec web isort . --diff --skip venv --skip migrations

isort:
	docker compose -f docker-compose.yml exec web isort . --skip venv --skip migrations

cov:
	docker compose -f docker-compose.yml exec web pytest -p no:warnings --cov=. -v

cov-html:
	docker compose -f docker-compose.yml exec web pytest -p no:warnings --cov=. --cov-report html
test-run:
	docker compose -f docker-compose.yml run --rm web python manage.py sync_tmdb --year 2023

custom-limit:
	docker compose -f docker-compose.local.yml run --rm web python manage.py sync_tmdb --year 2023 --max-results 50

no-limit:
	docker compose -f docker-compose.local.yml run --rm web python manage.py sync_tmdb --year 2023 --max-results 0


# English movies: 2023, 2022, 2021, 2020
 test-run-range:
	docker compose -f docker-compose.local.yml run --rm web python manage.py sync_tmdb --start-year 2020 --end-year 2023

custom-limit-II:
	docker compose -f docker-compose.local.yml run --rm web python manage.py sync_tmdb --start-year 2020 --end-year 2023 --max-results 50

tmdb-sync:
	docker compose -f docker-compose.local.yml run --rm web python manage.py rqworker tmdb_sync


test-lang:
	docker compose -f docker-compose.yml exec web pytest tests/language_analysis


test-subtitles:
	docker compose -f docker-compose.yml exec web pytest tests/subtitles