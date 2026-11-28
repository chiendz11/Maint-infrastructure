resource "aws_security_group" "cache" {
  name_prefix = "${local.name}-cache-"
  description = "Private Valkey cache/streams accessible from EKS nodes only"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.this.vpc_config[0].cluster_security_group_id]
  }
}

resource "aws_elasticache_subnet_group" "this" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = local.name
  description                = "Private Valkey cache/streams for MaintAI Business tier"
  engine                     = "valkey"
  engine_version             = var.cache_engine_version
  node_type                  = var.cache_node_type
  num_cache_clusters         = var.cache_num_cache_clusters
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.cache.id]
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.data.arn
  transit_encryption_enabled = true
  auth_token                 = var.cache_auth_token
  automatic_failover_enabled = var.cache_num_cache_clusters > 1
  multi_az_enabled           = var.cache_num_cache_clusters > 1
  auto_minor_version_upgrade = false
}
