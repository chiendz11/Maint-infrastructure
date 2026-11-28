# Edge MQTTS (TCP 8883) perimeter for EMQX NLB Service in EKS.
resource "aws_security_group" "emqx_nlb" {
  name_prefix = "${local.name}-emqx-nlb-"
  description = "Restrict inbound MQTTS 8883 traffic to reviewed edge/simulator CIDRs"
  vpc_id      = aws_vpc.this.id

  dynamic "ingress" {
    for_each = length(var.mqtt_ingress_cidrs) > 0 ? [var.mqtt_ingress_cidrs] : []
    content {
      from_port   = 8883
      to_port     = 8883
      protocol    = "tcp"
      cidr_blocks = ingress.value
    }
  }

  egress {
    from_port   = 8883
    to_port     = 8883
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}
