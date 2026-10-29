terraform {
  required_version = "= 1.15.6"
  backend "s3" {
    key          = "maintai-v13/platform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.61.0" }

  }
}
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "MaintAI", Environment = "production", ManagedBy = "terraform", Blueprint = "v1.3.1" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }
locals {
  name = "maintai-v13-prod"
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
  components = toset(["ingestion-api", "processing", "business-backend", "storage-consumer", "ml-service", "training", "rag-service", "frontend", "simulator-ui", "sensor", "drift-worker", "automation", "mlflow"])
  database_names = { processing = "processing_db", business = "business_db", drift = "drift_db", mlflow = "mlflow_db", knowledge = "knowledge_db" }
  runtime_secrets = toset(["processing-database", "business-database", "drift-database", "mlflow-database", "knowledge-database", "llm-provider", "ingestion-auth", "processing-api-auth", "ml-api-auth", "rag-api-auth", "model-release-publisher", "gitops-automation"])
}
