.PHONY: up down logs shell migrate test lint lint-fix runserver

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec web python manage.py shell

migrate:
	docker-compose exec web python manage.py migrate

test:
	docker-compose exec web pytest

# Run inside Docker (matches CI exactly)
lint:
	docker-compose exec web ruff check .

# Auto-fix what ruff can fix, then report remaining issues
lint-fix:
	docker-compose exec web ruff check --fix .

# Run without Docker using uv
lint-local:
	cd backend && uv run ruff check .

lint-fix-local:
	cd backend && uv run ruff check --fix .

runserver:
	docker-compose exec web python manage.py runserver 0.0.0.0:8000
