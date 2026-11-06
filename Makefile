
CLUSTER_NAME := kd-cloud
SERVICE_IMAGE := cmd-parser:1
WORKER_IMAGE := command-worker:1

.PHONY: up down build deploy

up: build deploy

build:
	k3d cluster list | grep -q $(CLUSTER_NAME) || k3d cluster create --config cluster/k3d.yaml
	k3d cluster start $(CLUSTER_NAME) --wait --timeout 180s
	kubectl wait --for=condition=Ready nodes --all --timeout=180s
	docker build -t $(SERVICE_IMAGE) -f service/Dockerfile .
	docker build -t $(WORKER_IMAGE) -f worker/Dockerfile .
	k3d image import $(SERVICE_IMAGE) $(WORKER_IMAGE) -c $(CLUSTER_NAME)

deploy:
	kubectl apply --validate=false -f k8s/
	kubectl rollout status deployment/command-parser -n app --timeout=300s

down:
	k3d cluster delete $(CLUSTER_NAME)
