.PHONY: up down logs shell migrate test lint runserver

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

lint:
	docker-compose exec web ruff check .

runserver:
	docker-compose exec web python manage.py runserver 0.0.0.0:8000
