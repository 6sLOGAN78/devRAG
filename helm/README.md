# Helm Charts (`/helm`)

Production Kubernetes deployment charts for **DevRAG**. 
These charts configure the system to deploy the Go API Gateway (replicas scaled on CPU metrics) independently from the Python ML Engine (scaled on GPU metrics or long-polling I/O limits).

*Note: Infrastructure dependencies (MySQL, MinIO, Redis, Infinity) should typically be managed externally (e.g., AWS RDS/S3) in a production environment, but basic StatefulSets are provided for full standalone deployment.*
