output "vpc_id" {
  value = aws_vpc.foundation.id
}

output "public_subnet_ids" {
  value = { for key, subnet in aws_subnet.public : key => subnet.id }
}

output "database_subnet_ids" {
  value = { for key, subnet in aws_subnet.database : key => subnet.id }
}

output "security_group_ids" {
  value = { for key, group in aws_security_group.boundary : key => group.id }
}

output "buckets" {
  value = { for key, bucket in aws_s3_bucket.private : key => { name = bucket.bucket, arn = bucket.arn } }
}

output "backend_repository" {
  value = { url = aws_ecr_repository.backend.repository_url, arn = aws_ecr_repository.backend.arn }
}

output "backend_log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "role_arns" {
  value = { for key, role in aws_iam_role.ecs : key => role.arn }
}

output "distribution" {
  description = "Future endpoint metadata; disabled by default and not evidence of deployment or readiness."
  value = {
    id          = aws_cloudfront_distribution.edge.id
    arn         = aws_cloudfront_distribution.edge.arn
    domain_name = aws_cloudfront_distribution.edge.domain_name
    url         = "https://${aws_cloudfront_distribution.edge.domain_name}"
  }
}

output "api_target_group_arn" {
  description = "Backend IP target group; ECS owns target registration, with zero tasks by default."
  value       = aws_lb_target_group.api.arn
}

output "database" {
  description = "Database and administrator secret metadata only; no credentials or readiness assertion."
  value = {
    identifier        = aws_db_instance.runtime.identifier
    address           = aws_db_instance.runtime.address
    port              = aws_db_instance.runtime.port
    name              = aws_db_instance.runtime.db_name
    master_secret_arn = one(aws_db_instance.runtime.master_user_secret).secret_arn
  }
}

output "application_secret_arn" {
  description = "Secret container only; its values and non-admin DB role must be provisioned separately."
  value       = aws_secretsmanager_secret.application.arn
}

output "backend_service" {
  value = {
    cluster         = aws_ecs_cluster.runtime.name
    name            = aws_ecs_service.backend.name
    task_definition = aws_ecs_task_definition.backend.arn
  }
}
