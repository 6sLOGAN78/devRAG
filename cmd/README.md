# DevRAG Go Application Entrypoints (`/cmd`)

This directory contains the main Go executable files for **DevRAG**. 

## `cmd/server/ragflow_server.go`

This is the primary entrypoint for the Go API Gateway. It boots the Gin-Gonic server, establishes connections to the database (MySQL) and cache (Redis), and starts the background Task Syncer for coordinating jobs with the Python ML Engine.

### Usage

To build and run the Go server:

```bash
go build -o server cmd/server/ragflow_server.go
./server -c conf/service_conf.yaml
```
