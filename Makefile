# Git metadata for Docker build args
BRANCH  := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
COMMIT  := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
TAG     := $(shell git describe --tags --exact-match 2>/dev/null || echo dev)
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
PYTHON_VERSION := $(shell cat .python-version 2>/dev/null || echo 3.12)

IMAGE_NAME := telegram-downloader

.PHONY: build run clean test unit integration

build:
	docker build \
		--build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg VCS_REF=$(COMMIT) \
		-t $(IMAGE_NAME):$(TAG) \
		-t $(IMAGE_NAME):latest \
		.

run: build
	docker compose up

clean:
	docker compose down --remove-orphans

test:
	pytest tests/unit tests/integration -v --cov=src --cov-report=term-missing

unit:
	pytest tests/unit -v --cov=src --cov-report=term-missing

integration:
	pytest tests/integration -v --cov=src --cov-report=term-missing
