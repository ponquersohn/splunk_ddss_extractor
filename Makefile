.PHONY: help env venv install test clean docker

# Variables
PROJECT_NAME := splunk-ddss-extractor
DOCKER_TAG ?= latest
PYTHON := python3
VENV := venv

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

env: ## Show environment and available commands
	@echo "$(GREEN)Splunk DDSS Extractor - Python Library$(NC)"
	@echo ""
	@echo "$(GREEN)Variables:$(NC)"
	@echo "  PROJECT_NAME    = $(PROJECT_NAME)"
	@echo "  DOCKER_TAG      = $(DOCKER_TAG)"
	@echo "  PYTHON          = $(PYTHON)"
	@echo "  VENV            = $(VENV)"
	@echo ""
	@echo "$(GREEN)Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-30s$(NC) %s\n", $$1, $$2}'

help: env ## Alias for env command

init: venv ## Initialize Python virtual environment
	@echo "$(GREEN)✓ Initialization complete$(NC)"

venv: ## Create Python virtual environment
	@echo "$(YELLOW)Creating Python virtual environment...$(NC)"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@echo "$(GREEN)✓ Virtual environment created at ./$(VENV)$(NC)"
	@echo "$(YELLOW)Run 'source $(VENV)/bin/activate' to activate$(NC)"

install: venv ## Install Python dependencies
	@echo "$(YELLOW)Installing Python dependencies...$(NC)"
	@. $(VENV)/bin/activate && pip install --upgrade pip
	@. $(VENV)/bin/activate && pip install -r requirements.txt
	@. $(VENV)/bin/activate && pip install -e .
	@. $(VENV)/bin/activate && pip install pyarrow  # For Parquet support
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

test: ## Run tests
	@echo "$(YELLOW)Running tests...$(NC)"
	@. $(VENV)/bin/activate && PYTHONPATH=$(shell pwd)/src pytest tests/ -v
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-coverage: ## Run tests with coverage report
	@echo "$(YELLOW)Running tests with coverage...$(NC)"
	@. $(VENV)/bin/activate && PYTHONPATH=$(shell pwd)/src pytest tests/ -v --cov=splunk_ddss_extractor --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage report complete$(NC)"

clean: ## Clean temporary files and caches
	@echo "$(YELLOW)Cleaning temporary files...$(NC)"
	@rm -rf __pycache__ .pytest_cache .coverage
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf build/ dist/ *.egg-info
	@echo "$(GREEN)✓ Cleaned$(NC)"

clean-all: clean ## Clean everything including venv
	@echo "$(YELLOW)Cleaning venv...$(NC)"
	@rm -rf $(VENV)
	@echo "$(GREEN)✓ All cleaned$(NC)"

docker: ## Build Docker image for local testing
	@echo "$(YELLOW)Building Docker image...$(NC)"
	@docker build -t $(PROJECT_NAME):$(DOCKER_TAG) -f docker/Dockerfile .
	@echo "$(GREEN)✓ Docker image built: $(PROJECT_NAME):$(DOCKER_TAG)$(NC)"

docker-run: docker ## Run Docker container locally for testing
	@echo "$(YELLOW)Running container locally...$(NC)"
	@docker run --rm -it \
		-e LOG_LEVEL=DEBUG \
		$(PROJECT_NAME):$(DOCKER_TAG)

dev-setup: init install ## Complete development setup
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo ""
	@echo "$(GREEN)Quick start:$(NC)"
	@echo "  1. Activate venv: source $(VENV)/bin/activate"
	@echo "  2. Run tests: make test"
	@echo "  3. Build Docker: make docker"

check: test ## Run all checks (tests)
	@echo "$(GREEN)✓ All checks passed$(NC)"

version: ## Show version information
	@echo "$(GREEN)Splunk DDSS Extractor$(NC)"
	@echo "  Python:    $$($(PYTHON) --version)"
	@echo "  Docker:    $$(docker --version)"

# Default target
.DEFAULT_GOAL := env
