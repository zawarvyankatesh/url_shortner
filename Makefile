IMAGE ?= url-shortener:local

.PHONY: install dev test run redis docker-build docker-run

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	pytest -q

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

redis:
	docker run --rm -p 6379:6379 --name url-shortener-redis redis:7-alpine

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env $(IMAGE)
