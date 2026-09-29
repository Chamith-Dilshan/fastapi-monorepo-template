.PHONY: install dev dev-backend dev-frontend build build-backend build-frontend lint test

# Install dependencies for both projects
install:
	cd frontend && pnpm install
	cd backend && uv sync

# Development mode
dev: dev-backend dev-frontend

dev-backend:
	cd backend && uv run fastapi dev app/main.py

dev-frontend:
	cd frontend && npm run dev

# Build
build: build-backend build-frontend

build-backend:
	cd backend && uv build

build-frontend:
	cd frontend && npm run build

# Linting & Testing
lint:
	cd backend && uv run ruff check . && uv run mypy .
	cd frontend && npm run lint

test:
	cd backend && uv run pytest
	cd frontend && npm run test

# Clean up
clean:
	rm -rf frontend/node_modules frontend/.next backend/.venv
	find . -type d -name __pycache__ -exec rm -rf {} +
