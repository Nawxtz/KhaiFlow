.RECIPEPREFIX = >

.PHONY: help ci secret-scan i18n-lint migration-check lint typecheck test build dev deploy-check

help:
> @echo "Targets: ci, lint, typecheck, test, build, secret-scan, i18n-lint, migration-check, dev, deploy-check"

ci: secret-scan i18n-lint migration-check lint typecheck test build

secret-scan:
> @bash scripts/check_no_secrets.sh

i18n-lint:
> @bash scripts/i18n_lint.sh

migration-check:
> @bash scripts/migration_check.sh

lint:
> @if [ -d backend ]; then cd backend && ruff check .; else echo "backend/ missing; skipping lint"; fi
> @if [ -d portal ]; then cd portal && npm run lint --if-present; else echo "portal/ missing; skipping lint"; fi

typecheck:
> @if [ -d backend ]; then cd backend && mypy app; else echo "backend/ missing; skipping typecheck"; fi
> @if [ -d portal ]; then cd portal && npm run typecheck --if-present; else echo "portal/ missing; skipping typecheck"; fi

test:
> @if [ -d backend ]; then cd backend && pytest; else echo "backend/ missing; skipping tests"; fi
> @if [ -d portal ]; then cd portal && npm test --if-present; else echo "portal/ missing; skipping tests"; fi

build:
> @if [ -d portal ]; then cd portal && npm run build --if-present; else echo "portal/ missing; skipping build"; fi

dev:
> docker compose up --build

deploy-check:
> @echo "Checking deploy readiness..."
> @test -f backend/.env || (echo "ERROR: backend/.env missing" && exit 1)
> @test -f portal/.env.local || (echo "ERROR: portal/.env.local missing" && exit 1)
> @echo "All checks passed. Ready to deploy."

