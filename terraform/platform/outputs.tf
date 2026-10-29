output "platform_contract" {
  description = "Non-secret handoff. Secret values and kubeconfig are excluded."
  value = {
    schema_version = "2.0.0"
    environment = "production"
    architecture_revision = "maintai-1.3.1+simulator-ui.1"
    aws = { account_id = data.aws_caller_identity.current.account_id, region = var.aws_region }
    cluster = { name = aws_eks_cluster.this.name, version = var.kubernetes_version, vpc_id = aws_vpc.this.id }
    database = { host = aws_db_instance.this.address, port = 5432, logical_databases = local.database_names, pgvector_version = var.pgvector_extension_version, master_secret_arn = aws_db_instance.this.master_user_secret[0].secret_arn }
    storage = { for key, bucket in aws_s3_bucket.data : key => bucket.id }
    kms_key_arn = aws_kms_key.data.arn
    training = { queue_name = aws_sqs_queue.dataset.name, queue_arn = aws_sqs_queue.dataset.arn, ledger_table = aws_dynamodb_table.training.name }
    roles = { for key, role in aws_iam_role.workload : key => role.arn }
    publishers = { app = aws_iam_role.publisher["app"].arn, gitops = aws_iam_role.publisher["gitops"].arn, reader = aws_iam_role.gitops_reader.arn, dataset = aws_iam_role.dataset_publisher.arn }
    images = { for key, repo in aws_ecr_repository.workload : key => repo.repository_url }
    secrets = { for key, secret in aws_secretsmanager_secret.runtime : key => secret.arn }
    ingress = { domain = data.terraform_remote_state.domain.outputs.domain_name, hosted_zone_id = data.terraform_remote_state.domain.outputs.hosted_zone_id, certificate_arn = data.terraform_remote_state.domain.outputs.validated_certificate_arn }
  }
}
output "eks_endpoint" { value = aws_eks_cluster.this.endpoint }
output "eks_ca" { value = aws_eks_cluster.this.certificate_authority[0].data }
output "eks_name" { value = aws_eks_cluster.this.name }
