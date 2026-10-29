resource "aws_security_group" "database" {
  name_prefix = "${local.name}-database-"
  description = "Private PostgreSQL accessible from EKS nodes only"
  vpc_id = aws_vpc.this.id
  ingress {
    from_port = 5432
    to_port = 5432
    protocol = "tcp"
    security_groups = [aws_eks_cluster.this.vpc_config[0].cluster_security_group_id]
  }
}
resource "aws_db_subnet_group" "this" {
  name = local.name
  subnet_ids = aws_subnet.private[*].id
}
resource "aws_db_parameter_group" "this" {
  name = "${local.name}-postgres17"
  family = "postgres17"
  parameter {
    name = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "this" {
  identifier = local.name
  engine = "postgres"
  engine_version = var.postgres_engine_version
  instance_class = var.db_instance_class
  db_name = "postgres"
  username = "maintai_admin"
  manage_master_user_password = true
  allocated_storage = 50
  max_allocated_storage = 200
  storage_type = "gp3"
  storage_encrypted = true
  kms_key_id = aws_kms_key.data.arn
  multi_az = var.db_multi_az
  db_subnet_group_name = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.database.id]
  parameter_group_name = aws_db_parameter_group.this.name
  publicly_accessible = false
  backup_retention_period = 7
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "${local.name}-final-snapshot"
  auto_minor_version_upgrade = false
  allow_major_version_upgrade = false
  apply_immediately = false
  lifecycle { prevent_destroy = true }
}
# Secret metadata only. Seed values outside Terraform to keep them out of state.
resource "aws_secretsmanager_secret" "runtime" {
  for_each = local.runtime_secrets
  name = "maintai/v13/production/${each.value}"
  kms_key_id = aws_kms_key.data.arn
  recovery_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
