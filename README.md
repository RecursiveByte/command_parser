# Command Parser

A cloud-native command parser built using a fine-tuned language model, FastAPI, Docker, Kubernetes, and SeaweedFS S3-compatible object storage.

The application accepts natural-language commands and returns structured JSON containing the `intent`, `date`, `time`, and `place` fields.

## GitHub Repository

[Command Parser — GitHub Repository](https://github.com/RecursiveByte/command_parser)

## Features

- Fine-tuned Pythia-based command parsing model
- FastAPI REST API
- JSON Schema validation of model output
- Docker containerization
- Kubernetes deployment with readiness and liveness probes
- Horizontal Pod Autoscaling (HPA)
- Model artifact storage using SeaweedFS S3
- Locust-based load testing
- Model training and evaluation scripts
- Performance, cost, and reliability analysis

## Project Structure

```text
command_parser/
│
├── .github/
│   └── workflows/
│       └── task6.yml
│
├── cluster/
│   └── k3d.yaml
│
├── data/
│   ├── commands_pool.jsonl
│   ├── corrected.jsonl
│   ├── rate_card.json
│   ├── rejected.json
│   ├── rejected.jsonl
│   ├── schema.json
│   ├── train.jsonl
│   ├── train.sha256
│   ├── train_v2.jsonl
│   ├── train_v2.sha256
│   ├── train_v3.jsonl
│   ├── train_v3.sha256
│   ├── validation.jsonl
│   └── teacher_shards/
│       ├── shard-0.jsonl
│       └── shard-1.jsonl
│
├── k8s/
│   ├── deployment.yaml
│   ├── hpa.yaml
│   ├── ingress.yaml
│   └── service.yaml
│
├── network/
│   ├── nacl.json
│   ├── packets_sample.jsonl
│   └── subnets.md
│
├── prompts/
│   └── teacher_prompt.txt
│
├── report/
│   └── task7.md
│
├── results/
│   ├── hpa-test_exceptions.csv
│   ├── hpa-test_failures.csv
│   ├── hpa-test_stats.csv
│   ├── hpa-test_stats_history.csv
│   ├── loadtest_exceptions.csv
│   ├── loadtest_failures.csv
│   ├── loadtest_stats.csv
│   ├── loadtest_stats_history.csv
│   ├── recovery-test_exceptions.csv
│   ├── recovery-test_failures.csv
│   ├── recovery-test_stats.csv
│   ├── recovery-test_stats_history.csv
│   ├── rolling-update_exceptions.csv
│   ├── rolling-update_failures.csv
│   ├── rolling-update_stats.csv
│   ├── rolling-update_stats_history.csv
│   ├── task3_limits.txt
│   ├── task3_test.py
│   ├── task7_exceptions.csv
│   ├── task7_failures.csv
│   ├── task7_stats.csv
│   ├── task7_stats_history.csv
│   └── v1/
│       ├── baseline_pythia_predictions.jsonl
│       ├── baseline_pythia_validation.json
│       ├── model_comparison.json
│       ├── rollback-test_exceptions.csv
│       ├── rollback-test_failures.csv
│       ├── rollback-test_stats.csv
│       ├── rollback-test_stats_history.csv
│       ├── student_v1_predictions.jsonl
│       ├── student_v1_validation.json
│       ├── teacher_predictions.jsonl
│       └── teacher_validation.json
│
├── service/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   └── schema.json
│
├── tests/
│   └── test_score.py
│
├── tools/
│   ├── locustfile.py
│   └── nacl_sim.py
│
├── training/
│   ├── config.yaml
│   ├── evaluate.py
│   ├── loss_v1.csv
│   ├── loss_v2.csv
│   ├── prepare_data.py
│   ├── processed_train.jsonl
│   ├── score.py
│   └── train.py
│
├── worker/
│   ├── clean.py
│   ├── Dockerfile
│   ├── label.py
│   ├── regenerate_rejected.py
│   ├── requirements.txt
│   ├── seaweedfs-values.yaml
│   ├── teacher-workers.yaml
│   ├── worker-0.log
│   └── worker-1.log
│
├── .gitignore
├── AI_USE.md
├── Makefile
├── README.md
└── s3-config.json
```

## Prerequisites

Install the following tools:

- Docker
- k3d
- kubectl
- Python 3.11+
- Locust
- Git
- Make

A Kubernetes cluster and the required supporting services, including SeaweedFS and S3 credentials, must be configured before deployment.

## Build

Build the Docker image and create the k3d cluster using the project configuration.

```bash
make build
```

The application image is built as:

```text
cmd-parser:1
```

The cluster configuration is available at:

```text
cluster/k3d.yaml
```

## Deploy

Apply the Kubernetes manifests:

```bash
kubectl apply -f k8s/
```

Check the deployment:

```bash
kubectl get pods -n app
```

Check the deployment status:

```bash
kubectl rollout status deployment/command-parser -n app
```

Check the service:

```bash
kubectl get svc -n app
```

Check the HPA:

```bash
kubectl get hpa -n app
```

## Access the Application

The k3d cluster exposes the Kubernetes ingress through port `8080`.

The API endpoint is:

```text
http://localhost:8080/parse
```

The service accepts POST requests.

### Example Request

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Book a meeting tomorrow at 10 AM in Delhi\"}"
```

### Health Checks

Liveness endpoint:

```text
/healthz
```

Readiness endpoint:

```text
/readyz
```

## Testing

### API Testing

Send a request to the parser endpoint:

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Schedule a meeting tomorrow at 10 AM in Delhi\"}"
```

### Locust Load Testing

Run Locust in headless mode:

```bash
locust -f tools/locustfile.py \
  --headless \
  --users 20 \
  --spawn-rate 2 \
  --run-time 2m \
  --host http://localhost:8080 \
  --csv results/task7
```

The generated CSV files contain load-test statistics, request history, failures, and exceptions.

### Kubernetes Resource Monitoring

```bash
kubectl top pods -n app
```

### Pod Status

```bash
kubectl get pods -n app
```

### Deployment Logs

```bash
kubectl logs -n app deployment/command-parser
```

## Model Training

The model training configuration is stored in:

```text
training/config.yaml
```

Run the training script from the repository root:

```bash
python training/train.py
```

The training script uses the configured dataset, model, hyperparameters, and output directory.

Trained model artifacts are stored under:

```text
training/output/
```

Large model artifacts should not be committed directly to Git.

## Model Evaluation

Run the model evaluation script from the repository root:

```bash
python results/v1/evaluate.py
```

Evaluation outputs and model comparisons are stored in the `results/` directory.

Refer to the available validation and comparison files for exact-match accuracy, JSON validity, and component-level evaluation metrics.

## Evidence

Task evidence is maintained in the `results/` directory.

Evidence includes:

- Model evaluation results
- Model comparison metrics
- Locust load-test CSV files
- Performance measurements
- Resource utilization outputs
- Cold-start measurements
- Reliability and recovery observations

The Task 7 performance and cost analysis is documented in:

```text
task_7.md
```

## Tear Down

Delete the Kubernetes resources:

```bash
kubectl delete -f k8s/
```

Delete the k3d cluster:

```bash
k3d cluster delete kd-cloud
```

The cluster deletion removes the local Kubernetes environment.

## Technologies Used

| Technology | Purpose |
|---|---|
| Python | Application and model training |
| FastAPI | REST API |
| PyTorch | Model training and inference |
| Hugging Face Transformers | Language model |
| Docker | Containerization |
| Kubernetes | Deployment and orchestration |
| k3d | Local Kubernetes cluster |
| SeaweedFS | S3-compatible object storage |
| Locust | Load testing |
| JSON Schema | Output validation |

## Task 7 Performance Summary

| Metric | Result |
|---|---:|
| Total Requests | 284 |
| Error Rate | 0% |
| Throughput | 2.395 RPS |
| p50 Latency | 6400 ms |
| p95 Latency | 8200 ms |
| Average Cold-Start Time | 14.61 seconds |
| Estimated Cost per 1000 Requests | ₹0.864 |

The measured results and cost calculations are documented in `task_7.md`.

## Submission

This repository includes the application source code, training and
evaluation scripts, Docker and Kubernetes configurations, and
experiment results.

The final report is available at `report/report.pdf`.

The final submission is tagged as `final`.