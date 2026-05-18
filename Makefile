.PHONY: build up down logs shell shell-jupyter shell-temp clean rebuild

# Build the Docker image
build:
	docker compose build

# Start the application
up:
	docker compose up

# Start in detached mode
up-d:
	docker compose up -d

# Stop the application
down:
	docker compose down

# View logs
logs:
	docker compose logs -f

# Open shell in the streamlit container (requires container to be running)
shell:
	docker compose exec -it streamlit bash

# Open shell in the jupyter container (requires container to be running)
shell-jupyter:
	docker compose exec -it jupyter bash

# Open shell in temporary container (works even if container is not running)
shell-temp:
	docker compose run --rm streamlit bash

# Clean up containers and volumes
clean:
	docker compose down -v
	docker system prune -f

# Rebuild from scratch
rebuild:
	docker compose down -v
	docker compose build --no-cache
	docker compose up
