locals {
  platform_metadata = {
    schema_version        = "2.0.0"
    environment           = "production"
    architecture_revision = "maintai-1.4.0+pure-gitops"
    aws                   = { account_id = data.aws_caller_identity.current.account_id, region = var.aws_region }
    cluster               = { name = aws_eks_cluster.this.name, version = var.kubernetes_version, vpc_id = aws_vpc.this.id }
    database              = { host = aws_db_instance.this.address, port = 5432, logical_databases = local.database_names, pgvector_version = var.pgvector_extension_version, master_secret_arn = aws_db_instance.this.master_user_secret[0].secret_arn }
    cache                 = { primary_endpoint = aws_elasticache_replication_group.this.primary_endpoint_address, reader_endpoint = aws_elasticache_replication_group.this.reader_endpoint_address, port = aws_elasticache_replication_group.this.port, transit_encryption_enabled = true, secret_arn = aws_secretsmanager_secret.runtime["business-redis"].arn }
    storage               = { for key, bucket in aws_s3_bucket.data : key => bucket.id }
    kms_key_arn           = aws_kms_key.data.arn
    training              = { queue_name = aws_sqs_queue.dataset.name, queue_arn = aws_sqs_queue.dataset.arn, ledger_table = aws_dynamodb_table.training.name }
    roles                 = { for key, role in aws_iam_role.workload : key => role.arn }
    publishers            = { app = aws_iam_role.publisher["app"].arn, reader = aws_iam_role.gitops_reader.arn, dataset = aws_iam_role.dataset_publisher.arn }
    images                = { for key, repo in aws_ecr_repository.workload : key => repo.repository_url }
    secrets               = { for key, secret in aws_secretsmanager_secret.runtime : key => secret.arn }
    msk                   = { cluster_arn = aws_msk_cluster.this.arn, bootstrap_brokers_sasl_scram = aws_msk_cluster.this.bootstrap_brokers_sasl_scram, scram_secrets = { for key, secret in aws_secretsmanager_secret.msk_scram : key => secret.arn } }
    cognito               = { user_pool_id = aws_cognito_user_pool.this.id, issuer_url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}", domain_url = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com", token_url = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token", ui_clients = { for key, client in aws_cognito_user_pool_client.ui : key => client.id }, m2m_clients = { for key, client in aws_cognito_user_pool_client.m2m : key => client.id } }
    ingress               = { domain = data.terraform_remote_state.domain.outputs.domain_name, hosted_zone_id = data.terraform_remote_state.domain.outputs.hosted_zone_id, certificate_arn = data.terraform_remote_state.domain.outputs.validated_certificate_arn }
  }
}

# Non-secret AWS SSM Parameter Store handoff (replaces cross-repo dispatch webhooks).
resource "aws_ssm_parameter" "platform_metadata" {
  name        = "/maintai/v13/production/platform-metadata"
  description = "Non-secret MaintAI production platform endpoints, ARNs, and ECR/Pod Identity metadata."
  type        = "String"
  tier        = "Advanced"
  value       = jsonencode(local.platform_metadata)
}

output "platform_metadata" {
  description = "Non-secret platform metadata published to AWS SSM Parameter Store."
  value       = local.platform_metadata
}

output "platform_contract" {
  description = "Compatibility alias for non-secret platform metadata."
  value       = local.platform_metadata
}

output "image_updater_role_arn" {
  description = "Pod Identity role ARN for argocd:argocd-image-updater-controller to read private ECR repositories."
  value       = aws_iam_role.workload["image-updater"].arn
}

output "eks_endpoint" { value = aws_eks_cluster.this.endpoint }
output "eks_ca" { value = aws_eks_cluster.this.certificate_authority[0].data }
output "eks_name" { value = aws_eks_cluster.this.name }
