# Task 7: Performance, Cost, and Review

## 7.1 Load Testing

The command-parser application was load-tested using Locust against the deployed Kubernetes service.

### Test Configuration

| Parameter | Value |
|---|---|
| Endpoint | `POST /parse` |
| Number of Users | 20 |
| Spawn Rate | 2 users/second |
| Test Duration | 2 minutes |
| Total Requests | 284 |

### Load Test Results

| Metric | Measured Value |
|---|---:|
| Total Requests | 284 |
| Failed Requests | 0 |
| Error Rate | 0% |
| Throughput | 2.395 RPS |
| p50 Latency | 6400 ms |
| Average Latency | 6479.30 ms |
| p95 Latency | 8200 ms |
| Maximum Latency | 9011.27 ms |
| Average Response Size | 59 bytes |

The load test resulted in zero failed requests, giving an observed error rate of 0%. However, the p95 latency of 8200 ms indicates high response latency under the tested workload.

### Locust Evidence

The following evidence files are available in the `results/` directory:

- `task7_stats.csv`
- `task7_stats_history.csv`
- `task7_failures.csv`
- `task7_exceptions.csv`

---

## 7.2 CPU and Memory Utilization

Pod resource utilization was measured using:

```bash
kubectl top pods -n app
```

### Pod Resource Usage

| Pod | CPU Usage | Memory Usage |
|---|---:|---:|
| `command-parser-6dc65b8b7c-k42dn` | 3m | 368Mi |
| `command-parser-6dc65b8b7c-xc8hd` | 3m | 425Mi |

### Resource Configuration

| Resource | Request | Limit |
|---|---:|---:|
| CPU | 500m | 2 vCPU |
| Memory | 512Mi | 1Gi |

The Horizontal Pod Autoscaler (HPA) was configured with a CPU utilization target of 70%, a minimum of 1 replica, and a maximum of 2 replicas.

The captured HPA status showed CPU utilization of 0% against the 70% target, with 1 replica running.

The `kubectl top pods` and HPA values are point-in-time snapshots. They may have been captured at different times and do not represent continuous resource utilization throughout the load test.

---

## 7.3 Cold-Start Time

Cold-start time was measured by deleting the command-parser pods and recording the time required for replacement pods to become Ready.

### Cold-Start Measurements

| Trial | Time to Ready |
|---|---:|
| Trial 1 | 18.10 seconds |
| Trial 2 | 12.97 seconds |
| Trial 3 | 12.75 seconds |

### Average Cold-Start Time

The average cold-start time was calculated as follows:

$$
\begin{aligned}
\text{Average Cold-Start Time}
&= \frac{18.10 + 12.97 + 12.75}{3} \\
&= \frac{43.82}{3} \\
&= 14.61 \text{ seconds}
\end{aligned}
$$

During startup, the application downloaded 6 model files from `s3://models/v2` and successfully loaded the model.

Readiness initially returned HTTP 503 and later HTTP 200, indicating that the application became ready after model loading.

---

## 7.4 Cost Estimation

The cost estimation is based on the provided `rate_card.json`.

### Rate Card

| Resource | Rate |
|---|---:|
| CPU | ₹3.50 per vCPU-hour |
| Memory | ₹0.45 per GiB-hour |

The following estimate assumes one running replica and uses its configured CPU and memory limits for billing.

### Step 1: Calculate the Hourly Cost of One Replica

CPU limit = 2 vCPU

$$
\begin{aligned}
\text{CPU Cost}
&= 2 \times ₹3.50 \\
&= ₹7.00 \text{ per hour}
\end{aligned}
$$

Memory limit = 1 GiB

$$
\begin{aligned}
\text{Memory Cost}
&= 1 \times ₹0.45 \\
&= ₹0.45 \text{ per hour}
\end{aligned}
$$

Therefore, the hourly cost of one replica is:

$$
\begin{aligned}
\text{Hourly Cost per Replica}
&= ₹7.00 + ₹0.45 \\
&= ₹7.45 \text{ per hour}
\end{aligned}
$$

### Step 2: Calculate Requests Served per Hour

Measured throughput:

$$
\text{RPS} = 2.39502275
$$

$$
\begin{aligned}
\text{Requests per Hour}
&= 2.39502275 \times 3600 \\
&= 8622.08 \text{ requests}
\end{aligned}
$$

### Step 3: Calculate Cost per 1000 Requests

The formula is:

$$
\text{Cost per 1000 Requests}
=
\frac{\text{Hourly Cost of Running Replicas}}
{\text{Requests Served per Hour}}
\times 1000
$$

For one running replica:

$$
\begin{aligned}
\text{Cost per 1000 Requests}
&= \frac{₹7.45}{8622.08} \times 1000 \\
&\approx ₹0.864
\end{aligned}
$$

The estimated cost is **₹0.864 per 1000 requests** under the one-replica assumption. This is an estimate based on the provided rate card and measured throughput, not an actual cloud charge. If more replicas are running, the hourly cost must be recalculated using the total cost of all running replicas.

---

## 7.5 Service Level Objective (SLO)

### SLO Definition

The selected Service Level Objective is:

**At least 99% of requests must succeed during one load-test run.**

| Parameter | Value |
|---|---|
| SLO Target | 99% successful requests |
| Measurement Window | One Locust load-test run |
| Total Requests | 284 |
| Failed Requests | 0 |
| Observed Success Rate | 100% |

### Error Budget Calculation

The error budget is the maximum allowable number of failed requests while maintaining the 99% success target.

$$
\begin{aligned}
\text{Error Budget}
&= (1 - 0.99) \times 284 \\
&= 0.01 \times 284 \\
&= 2.84 \text{ requests}
\end{aligned}
$$

### Error Budget Used

$$
\begin{aligned}
\text{Error Budget Used}
&= \text{Observed Failed Requests} \\
&= 0 \text{ requests}
\end{aligned}
$$

The service achieved a 100% observed success rate during the load test and consumed none of the error budget.

Since requests are whole numbers, up to 2 failed requests would still meet the 99% target for this test. Three failed requests would breach the target.

---

## 7.6 Model Quality Evaluation

The models were evaluated using 100 validation examples each.

### Model Comparison

| Model | Exact-Match Accuracy | Valid JSON Rate | Intent Accuracy | Date Accuracy | Time Accuracy | Place Accuracy | Correct Predictions |
|---|---:|---:|---:|---:|---:|---:|---:|
| Teacher | 26% | 100% | 77% | 72% | 66% | 63% | 26/100 |
| `baseline_pythia` | 0% | 0% | 0% | 0% | 0% | 0% | 0/100 |
| `student_v1` | 42% | 100% | 78% | 79% | 84% | 83% | 42/100 |

The student model achieved 42% exact-match accuracy, improving over the teacher model's 26%.

The student model also achieved higher component accuracies for intent, date, time, and place.

However, 58 out of 100 student predictions were not exact matches, indicating that additional model improvement is required.

The baseline model produced no valid JSON in this evaluation.

### Model Quality Evidence

- `results/v1/model_comparison.json`
- `results/v1/teacher_validation.json`
- `results/v1/student_v1_validation.json`
- `results/v1/baseline_python_validation.json`

---

## 7.7 Review

| Component or Concern | Evidence (Measured Value) | Limitation Found | Improvement Proposed |
|---|---|---|---|
| Data and Storage | 6 model files downloaded from `s3://models/v2`; model loading completed successfully. | Model download duration, file sizes, and storage latency were not measured. | Record model artifact sizes, download time, and checksums. Version model artifacts and verify integrity before loading. |
| Model Quality | `student_v1` achieved 42% exact-match accuracy, 100% valid JSON rate, 78% intent accuracy, 79% date accuracy, 84% time accuracy, and 83% place accuracy on 100 examples. | 58 out of 100 predictions were not exact matches. The validation dataset contains only 100 examples. | Improve training data coverage, analyze prediction errors, and evaluate using a larger held-out dataset. |
| Latency and Throughput | p50 latency = 6400 ms, p95 latency = 8200 ms, throughput = 2.395 RPS, and error rate = 0%. | The p95 latency of 8200 ms is high for an interactive application. | Optimize model inference and preprocessing, profile bottlenecks, and repeat load tests at different traffic levels. |
| Resource Utilization | Pod CPU usage = 3m each; memory usage = 368Mi and 425Mi. CPU limit = 2 vCPU and memory limit = 1Gi per pod. | Resource usage was captured as a snapshot and not continuously monitored during the load test. | Collect time-series CPU and memory metrics and verify HPA scaling under sustained load. |
| Reliability and Recovery | 0 failed requests out of 284. Average cold-start time = 14.61 seconds across 3 trials. Model loading succeeded after downloading 6 files. | Only 3 cold-start trials and one short load test were performed. | Perform more recovery and rolling-update tests, measure recovery time, and test model-storage failures. |
| Security and Cost | Estimated cost = ₹7.45 per replica-hour and ₹0.864 per 1000 requests under the one-replica assumption. | Cost is based on a hypothetical rate card. Quantified security-test results were not collected as part of these measurements. | Collect evidence for access control, secret management, network exposure, and image scanning. Refine cost estimates using sustained throughput and replica scaling. |

---

## 7.8 Task 7 Conclusion

The command-parser service was load-tested using Locust with 20 concurrent users for 2 minutes.

The application handled 284 requests with an error rate of 0%. The measured throughput was 2.395 requests per second, with a p50 latency of 6400 ms and a p95 latency of 8200 ms.

The average cold-start time was 14.61 seconds across three trials. Based on the provided rate card and the one-replica assumption, the estimated cost was ₹0.864 per 1000 requests.

The student model achieved 42% exact-match accuracy and a 100% valid JSON rate on the validation dataset. Further improvements are required in model accuracy, response latency, and continuous resource monitoring.
