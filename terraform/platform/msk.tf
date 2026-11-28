resource "aws_security_group" "msk" {
  name_prefix = "${local.name}-msk-"
  description = "Private Amazon MSK SASL/SCRAM TLS accessible from EKS nodes only"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port       = 9096
    to_port         = 9096
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.this.vpc_config[0].cluster_security_group_id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_msk_configuration" "this" {
  name              = "${local.name}-msk-config"
  kafka_versions    = [var.msk_kafka_version]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=12
  PROPERTIES
}

resource "aws_msk_cluster" "this" {
  cluster_name           = local.name
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = 4

  broker_node_group_info {
    instance_type   = var.msk_instance_type
    client_subnets  = aws_subnet.private[*].id
    security_groups = [aws_security_group.msk.id]
    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = aws_kms_key.data.arn
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  client_authentication {
    sasl {
      scram = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Secret metadata only (AmazonMSK_* prefix required for MSK SCRAM); seed credentials outside Terraform.
resource "aws_secretsmanager_secret" "msk_scram" {
  for_each                = toset(["processing", "business", "ingestion"])
  name                    = "AmazonMSK_${local.name}_${each.value}"
  kms_key_id              = aws_kms_key.data.arn
  recovery_window_in_days = 30
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_msk_scram_secret_association" "this" {
  cluster_arn     = aws_msk_cluster.this.arn
  secret_arn_list = [for secret in aws_secretsmanager_secret.msk_scram : secret.arn]
}
