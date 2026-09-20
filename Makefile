install:
	pip install -e ".[dev]"

run:
	uvicorn nexusflow.main:app --reload

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

migration:
	alembic revision --autogenerate -m "$(msg)"

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f