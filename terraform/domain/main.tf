resource "aws_route53_zone" "this" {
  count = var.existing_hosted_zone_id == null ? 1 : 0
  name = var.domain_name
}
data "aws_route53_zone" "existing" {
  count = var.existing_hosted_zone_id != null ? 1 : 0
  zone_id = var.existing_hosted_zone_id
}
locals {
  zone_id = var.existing_hosted_zone_id != null ? data.aws_route53_zone.existing[0].zone_id : aws_route53_zone.this[0].zone_id
  zone_arn = var.existing_hosted_zone_id != null ? data.aws_route53_zone.existing[0].arn : aws_route53_zone.this[0].arn
}
resource "aws_acm_certificate" "this" {
  domain_name = "*.${var.domain_name}"
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}
resource "aws_route53_record" "certificate" {
  for_each = { for dvo in aws_acm_certificate.this.domain_validation_options : dvo.domain_name => dvo }
  zone_id = local.zone_id
  name = each.value.resource_record_name
  type = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl = 60
  allow_overwrite = false
}
resource "aws_acm_certificate_validation" "this" {
  count = var.wait_for_certificate_validation ? 1 : 0
  certificate_arn = aws_acm_certificate.this.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate : record.fqdn]
}
output "nameservers" { value = var.existing_hosted_zone_id != null ? data.aws_route53_zone.existing[0].name_servers : aws_route53_zone.this[0].name_servers }
output "domain_name" { value = var.domain_name }
output "hosted_zone_id" { value = local.zone_id }
output "hosted_zone_arn" { value = local.zone_arn }
output "validated_certificate_arn" { value = var.wait_for_certificate_validation ? aws_acm_certificate_validation.this[0].certificate_arn : null }
