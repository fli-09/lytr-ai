.PHONY: up down logs test build restart-backend

up:
	@test -f .env || (echo "Missing .env - run: cp .env.example .env  (then add your API keys)" && exit 1)
	docker compose up -d --build
	@echo "Backend:  http://localhost:8000/health"
	@echo "Frontend: http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f

restart-backend:
	docker compose restart backend

test:
	cd backend && python -m pytest

build:
	cd frontend && npm ci && npm run build
