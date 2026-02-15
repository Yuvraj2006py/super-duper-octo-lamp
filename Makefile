SHELL := /bin/bash

up:
	docker compose up -d --build

reload:
	docker compose up -d --force-recreate api worker beat dashboard


down:
	docker compose down


logs:
	docker compose logs -f --tail=200 api worker dashboard


migrate:
	docker compose run --rm -e PYTHONPATH=/workspace api alembic upgrade head


seed:
	docker compose run --rm -e PYTHONPATH=/workspace api python scripts/seed.py

parse_resume:
	docker compose run --rm -e PYTHONPATH=/workspace api python scripts/parse_resume.py


run_demo:
	docker compose run --rm -e PYTHONPATH=/workspace api python scripts/run_demo.py


test:
	docker compose run --rm -e PYTHONPATH=/workspace api pytest -q
